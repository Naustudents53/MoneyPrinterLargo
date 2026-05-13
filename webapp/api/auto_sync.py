"""
Background auto-sync scheduler.

Periodically refreshes YouTube channel stats (subscribers, views, likes,
comments) without the user having to click "Sync YT" by hand. Three tiers
run independently so we can sync cheap data often and expensive data rarely:

    light   — subscriber count per channel.         Default: every 60 min.
    recent  — stats for the N most-recent videos.   Default: every 30 min.
    full    — equivalent to the manual Sync YT btn. Default: every 12 h (OFF).

Why three tiers? yt-dlp scrapes the public YouTube site (no API key needed),
so we don't have a quota — but YouTube *will* rate-limit / captcha an IP
that hammers it. Recent videos move (views, likes) much faster than the
overall channel state, and subscribers barely move between hours. Tiering
keeps us under YouTube's invisible threshold while still feeling "live".

Backoff: on consecutive failures we multiply the interval by 2^k (capped
at 16x) so a YouTube hiccup doesn't turn into a tight retry loop. A success
resets the counter.

The light + recent tiers do their work in-process (asyncio + yt-dlp inside
threads) for low overhead. The full tier shells out to the same subprocess
the manual button uses, because it has more bells and whistles (--prune,
--add, dedupe) that we don't want to duplicate here.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional


# Defaults — overridden by config.json["auto_sync"] when present.
DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "light_enabled": True,
    "light_interval_minutes": 60,
    "recent_enabled": True,
    "recent_interval_minutes": 30,
    "recent_video_count": 10,
    "full_enabled": False,
    "full_interval_minutes": 720,
}

# Hard floors so the user can't set themselves an instant IP ban from the UI.
MIN_INTERVAL_MINUTES = {
    "light": 15,
    "recent": 10,
    "full": 180,  # 3h — full scan is expensive
}

# Per-tier failure backoff exponent cap (2^4 = 16x interval).
MAX_BACKOFF_POW = 4


def _format_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class AutoSyncScheduler:
    """One long-lived instance per FastAPI process. Owns three asyncio
    tasks (one per tier) and a small in-memory state dict that gets
    persisted to disk so the UI can show "last run / next run" across
    backend restarts."""

    def __init__(self, root_dir: Path, config_loader: Callable[[], dict]):
        self.root_dir = root_dir
        self.state_path = root_dir / ".mp" / "auto_sync_state.json"
        self.config_loader = config_loader
        self._tasks: dict[str, asyncio.Task] = {}
        self._wakeups: dict[str, asyncio.Event] = {}
        self._state_lock = threading.Lock()
        self._state: dict[str, dict[str, Any]] = self._load_state()
        # Ring buffer of recent log lines per tier for the UI.
        self._logs: dict[str, list[str]] = {"light": [], "recent": [], "full": []}
        self._stopping = False

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> dict[str, dict[str, Any]]:
        try:
            if self.state_path.is_file():
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def _save_state(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with self._state_lock, open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._log("light", f"WARN: could not persist state: {e}")

    def _set_tier_state(self, tier: str, **fields: Any) -> None:
        with self._state_lock:
            cur = self._state.get(tier, {})
            cur.update(fields)
            self._state[tier] = cur
        self._save_state()

    def get_state(self) -> dict[str, Any]:
        """Snapshot used by the /api/auto-sync/status endpoint."""
        with self._state_lock:
            state = json.loads(json.dumps(self._state))  # deep copy
        cfg = self._config()
        return {
            "config": cfg,
            "tiers": state,
            "logs": {k: list(v) for k, v in self._logs.items()},
            "running": not self._stopping,
        }

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def _config(self) -> dict[str, Any]:
        try:
            cfg = self.config_loader() or {}
        except Exception:
            cfg = {}
        merged = dict(DEFAULT_CONFIG)
        sub = cfg.get("auto_sync") or {}
        if isinstance(sub, dict):
            merged.update({k: v for k, v in sub.items() if v is not None})
        # Clamp intervals to the safety floors.
        for tier, floor in MIN_INTERVAL_MINUTES.items():
            key = f"{tier}_interval_minutes"
            try:
                if int(merged.get(key, 0)) < floor:
                    merged[key] = floor
            except (TypeError, ValueError):
                merged[key] = floor
        return merged

    def _tier_enabled(self, cfg: dict[str, Any], tier: str) -> bool:
        if not cfg.get("enabled", True):
            return False
        return bool(cfg.get(f"{tier}_enabled", DEFAULT_CONFIG[f"{tier}_enabled"]))

    def _interval_seconds(self, cfg: dict[str, Any], tier: str) -> int:
        mins = int(cfg.get(f"{tier}_interval_minutes", DEFAULT_CONFIG[f"{tier}_interval_minutes"]))
        return max(60, mins * 60)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, tier: str, msg: str) -> None:
        line = f"[{_format_ts(datetime.now())}] {msg}"
        buf = self._logs.setdefault(tier, [])
        buf.append(line)
        # Cap each ring buffer at 100 lines so a long-running server doesn't
        # leak memory through the auto-sync logs.
        if len(buf) > 100:
            del buf[: len(buf) - 100]
        # Mirror to stdout so it shows up in uvicorn logs.
        print(f"[auto-sync:{tier}] {msg}", flush=True)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._stopping = False
        loop = asyncio.get_event_loop()
        for tier, runner in (
            ("light", self._run_light),
            ("recent", self._run_recent),
            ("full", self._run_full),
        ):
            if tier in self._tasks and not self._tasks[tier].done():
                continue
            self._wakeups[tier] = asyncio.Event()
            self._tasks[tier] = loop.create_task(self._tier_loop(tier, runner))
        self._log("light", "scheduler started")

    async def stop(self) -> None:
        self._stopping = True
        # Wake every tier so they observe the stop flag and exit promptly.
        for ev in self._wakeups.values():
            ev.set()
        for t in self._tasks.values():
            t.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def trigger_now(self, tier: str) -> None:
        """Force the given tier to run on its next iteration without waiting
        for the configured interval. Used by the 'Run now' UI action."""
        if tier in self._wakeups:
            self._wakeups[tier].set()

    # ------------------------------------------------------------------
    # Main tier loop
    # ------------------------------------------------------------------

    def _first_iteration_wait(self, tier: str, interval_seconds: int, backoff_mul: int) -> float:
        """Decide how long to wait before the FIRST run after process startup.

        Three cases:
          (a) Never ran before → small stagger so we populate initial data
              quickly without making the user wait a full interval.
          (b) Last successful run was longer ago than the (backoff-adjusted)
              interval → backend was offline during a scheduled cycle. Run
              ASAP after a brief stagger so the user gets fresh data when
              they reopen the app.
          (c) Last run was recent → resume the original cycle by waiting
              only the *remaining* time, not a fresh full interval. Without
              this, restarting the backend would silently push every tier
              back by one interval each time.
        """
        # Per-tier short stagger so the three tiers never fire on the exact
        # same wall-clock second after boot — that would serialize on the
        # cache lock and spike yt-dlp traffic for no reason.
        catch_up_stagger = {"light": 10, "recent": 30, "full": 60}.get(tier, 20)

        last_run_str = self._state.get(tier, {}).get("last_run_at")
        if not last_run_str:
            self._log(tier, "startup: no previous run recorded — firing shortly")
            return catch_up_stagger

        try:
            last_run = datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return catch_up_stagger

        elapsed = (datetime.now() - last_run).total_seconds()
        target_interval = interval_seconds * backoff_mul

        if elapsed >= target_interval:
            missed = int(elapsed // interval_seconds)
            self._log(
                tier,
                f"catch-up: last run was {int(elapsed/60)} min ago "
                f"(~{missed} missed cycle{'s' if missed != 1 else ''}) — firing shortly",
            )
            return catch_up_stagger

        remaining = max(1.0, target_interval - elapsed)
        self._log(
            tier,
            f"resuming: last run {int(elapsed/60)} min ago, "
            f"next in {int(remaining/60)} min",
        )
        return remaining

    async def _tier_loop(self, tier: str, runner: Callable[[dict], "asyncio.Future"]) -> None:
        first_iteration = True

        while not self._stopping:
            cfg = self._config()
            if not self._tier_enabled(cfg, tier):
                self._set_tier_state(tier, last_status="disabled")
                # Re-check periodically — the user may flip the toggle in
                # Settings without restarting the backend.
                await self._wait(60)
                # A disabled stretch shouldn't count as "first iteration" — if
                # they re-enable us, we want to honor the catch-up logic too.
                continue

            interval = self._interval_seconds(cfg, tier)
            failures = int(self._state.get(tier, {}).get("consecutive_failures", 0))
            backoff_mul = 2 ** min(failures, MAX_BACKOFF_POW)

            # First pass after startup: decide based on last_run_at, NOT a
            # fresh interval. This is what makes "close laptop for 8h, reopen
            # and see fresh data within seconds" work.
            if first_iteration:
                wait_for = self._first_iteration_wait(tier, interval, backoff_mul)
                first_iteration = False
            else:
                wait_for = interval * backoff_mul

            # Compute the next-run target (may be sooner via wakeup).
            next_at = datetime.now() + timedelta(seconds=wait_for)
            self._set_tier_state(tier, next_run_at=_format_ts(next_at))

            await self._wait(wait_for, wake=self._wakeups[tier])
            if self._stopping:
                break

            # Re-check enabled flag — user may have disabled mid-wait.
            cfg = self._config()
            if not self._tier_enabled(cfg, tier):
                continue

            self._set_tier_state(
                tier,
                last_status="running",
                last_run_started_at=_format_ts(datetime.now()),
            )
            self._log(tier, f"starting (backoff_mul={backoff_mul}x)")
            try:
                result = await runner(cfg)
                msg = self._summarize_result(tier, result)
                self._set_tier_state(
                    tier,
                    last_status="ok",
                    last_run_at=_format_ts(datetime.now()),
                    last_message=msg,
                    consecutive_failures=0,
                )
                self._log(tier, f"OK — {msg}")
            except Exception as e:
                failures += 1
                msg = str(e)[:200]
                self._set_tier_state(
                    tier,
                    last_status="error",
                    last_run_at=_format_ts(datetime.now()),
                    last_message=msg,
                    consecutive_failures=failures,
                )
                self._log(tier, f"ERROR — {msg}")

    async def _wait(self, seconds: float, wake: Optional[asyncio.Event] = None) -> None:
        if wake is None:
            try:
                await asyncio.sleep(seconds)
            except asyncio.CancelledError:
                raise
            return
        # Race the sleep against a wakeup signal so 'Run now' fires the tier
        # immediately instead of waiting out the rest of the interval.
        try:
            await asyncio.wait_for(wake.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
        wake.clear()

    @staticmethod
    def _summarize_result(tier: str, result: Any) -> str:
        if not isinstance(result, dict):
            return "done"
        if tier == "light":
            return f"{result.get('updated', 0)} canales actualizados, {result.get('failed', 0)} fallidos"
        if tier == "recent":
            return f"{result.get('refreshed', 0)} videos refrescados, {result.get('channels', 0)} canales"
        if tier == "full":
            return f"rc={result.get('rc', '?')}"
        return "done"

    # ------------------------------------------------------------------
    # Tier implementations
    # ------------------------------------------------------------------

    def _import_sync_helpers(self):
        """Lazy import so a missing yt-dlp doesn't prevent the API from
        starting. The helpers live in scripts/sync_youtube_cache.py — we
        add scripts/ to sys.path the first time we need them."""
        scripts_dir = str(self.root_dir / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import sync_youtube_cache as sync_mod  # type: ignore
        return sync_mod

    async def _run_light(self, _cfg: dict) -> dict:
        """Refresh subscriber count only — one yt-dlp call per channel."""
        sync_mod = self._import_sync_helpers()
        from cache import json_write_lock, get_youtube_cache_path  # type: ignore

        cache_path = get_youtube_cache_path()
        # Read OUTSIDE the write lock — a stale snapshot is fine since we
        # only care about which channels exist + their handles right now.
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {"accounts": []}

        # Channel → fresh subscriber count (None when fetch fails).
        fresh: dict[str, Optional[int]] = {}
        for acc in data.get("accounts", []):
            handle = sync_mod.normalize_handle(acc.get("youtube_handle", ""))
            if not handle:
                continue
            try:
                count = await asyncio.to_thread(sync_mod.fetch_channel_subscriber_count, handle)
            except Exception as e:
                self._log("light", f"  {acc.get('nickname','?')}: error {str(e)[:60]}")
                fresh[acc["id"]] = None
                continue
            fresh[acc["id"]] = count
            self._log("light", f"  {acc.get('nickname','?')}: {count if count is not None else '(n/d)'}")
            # Brief gentle pause so YouTube doesn't see three requests in one tick.
            await asyncio.sleep(0.5)

        # Write back under the cache lock so concurrent video-pipeline writes
        # (add_video, _update_last_video_url) don't lose data.
        with json_write_lock(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                latest = json.load(f) or {"accounts": []}
            updated = 0
            failed = 0
            for acc in latest.get("accounts", []):
                if acc.get("id") not in fresh:
                    continue
                count = fresh[acc["id"]]
                if count is None:
                    failed += 1
                    continue
                acc["subscriber_count"] = count
                acc["stats_synced_at"] = _format_ts(datetime.now())
                updated += 1
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(latest, f, indent=4, ensure_ascii=False)
        return {"updated": updated, "failed": failed}

    async def _run_recent(self, cfg: dict) -> dict:
        """Refresh stats for the N most-recent videos of each channel."""
        sync_mod = self._import_sync_helpers()
        # Force-clear the in-process video meta cache so auto-sync sees
        # fresh values every cycle, not the first-time values stuck in
        # memory from a previous run.
        try:
            sync_mod._VIDEO_META_CACHE.clear()
        except Exception:
            pass

        from cache import json_write_lock, get_youtube_cache_path  # type: ignore

        n_videos = max(1, min(50, int(cfg.get("recent_video_count", 10))))
        cache_path = get_youtube_cache_path()
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {"accounts": []}

        # video_id → fresh stats. Keyed by id (not URL) so dedupe is trivial.
        fresh_stats: dict[str, dict[str, int]] = {}
        channels_touched = 0
        for acc in data.get("accounts", []):
            videos = acc.get("videos", []) or []
            if not videos:
                continue
            # Most-recent first by date string (ISO-ish, so lex sort = chrono).
            recent = sorted(videos, key=lambda v: v.get("date", ""), reverse=True)[:n_videos]
            channels_touched += 1
            for v in recent:
                vid = sync_mod.extract_video_id(v.get("url", "") or "")
                if not vid or vid in fresh_stats:
                    continue
                try:
                    meta = await asyncio.to_thread(sync_mod.fetch_video_meta, vid)
                except Exception as e:
                    self._log("recent", f"  {vid}: error {str(e)[:60]}")
                    continue
                fresh_stats[vid] = {
                    "view_count": int(meta.get("view_count") or 0),
                    "like_count": int(meta.get("like_count") or 0),
                    "comment_count": int(meta.get("comment_count") or 0),
                }
                # Stagger to ~3 videos/sec — YouTube tolerates this comfortably.
                await asyncio.sleep(0.3)

        with json_write_lock(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                latest = json.load(f) or {"accounts": []}
            refreshed = 0
            now_ts = _format_ts(datetime.now())
            for acc in latest.get("accounts", []):
                for v in acc.get("videos", []) or []:
                    vid = sync_mod.extract_video_id(v.get("url", "") or "")
                    if not vid or vid not in fresh_stats:
                        continue
                    s = fresh_stats[vid]
                    v["view_count"] = s["view_count"]
                    v["like_count"] = s["like_count"]
                    v["comment_count"] = s["comment_count"]
                    v["stats_synced_at"] = now_ts
                    refreshed += 1
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(latest, f, indent=4, ensure_ascii=False)

        return {"refreshed": refreshed, "channels": channels_touched}

    async def _run_full(self, _cfg: dict) -> dict:
        """Re-use the existing subprocess-based full sync. We don't replicate
        its prune/add/dedupe logic here on purpose — one source of truth."""
        script = self.root_dir / "scripts" / "sync_youtube_cache.py"
        if not script.is_file():
            raise RuntimeError(f"sync script missing at {script}")
        cmd = [sys.executable, str(script), "--apply", "--refresh-meta"]
        # Run in a thread because subprocess.run blocks. We don't need the
        # streamed output for autosync (the SSE endpoint is for the manual
        # button); just rc + a short tail of stdout for the UI log.
        def _run() -> tuple[int, str]:
            proc = subprocess.run(
                cmd,
                cwd=str(self.root_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60 * 30,  # 30 min hard cap
            )
            tail = "\n".join((proc.stdout or "").splitlines()[-10:])
            return proc.returncode, tail
        rc, tail = await asyncio.to_thread(_run)
        for line in tail.splitlines():
            self._log("full", f"  {line}")
        if rc != 0:
            raise RuntimeError(f"full sync exited with rc={rc}")
        return {"rc": rc}

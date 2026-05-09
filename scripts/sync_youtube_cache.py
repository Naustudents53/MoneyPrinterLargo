"""
Sync the local video cache (.mp/youtube.json) against the actual list of
videos on a YouTube channel — using yt-dlp (no API key required).

For each channel that has `youtube_handle` set in the cache:
  1. Fetch the long-form videos list from `<handle>/videos` (yt-dlp tab).
  2. Fetch the shorts list from `<handle>/shorts`.
  3. Build {video_id: {title, is_short}} for every published video.
  4. Walk the cache entries:
       - If the entry has a video URL → match by video_id and set is_short.
       - If the entry has no URL (placeholder, manual upload, studio link)
         → match by title (lowercased, whitespace-collapsed) against the
         scraped list. If found, fill in url + is_short.
       - If --prune is set, drop entries that don't match anything on the
         actual channel.
  5. Add any videos that exist on the channel but are missing from the
     cache (so the history page reflects reality).

Usage:
    python scripts/sync_youtube_cache.py                        # dry-run all channels
    python scripts/sync_youtube_cache.py --apply                # write changes
    python scripts/sync_youtube_cache.py --apply --prune        # also delete orphans
    python scripts/sync_youtube_cache.py --apply --prune --add  # also add YT-only videos
    python scripts/sync_youtube_cache.py --channel-id <uuid>    # restrict
    python scripts/sync_youtube_cache.py --handle @andrecronicas --channel-id <uuid>
                                                                # one-shot override
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from typing import Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_PATH = os.path.join(ROOT_DIR, ".mp", "youtube.json")


def normalize_title(t: str) -> str:
    """Lowercase, strip accents/punct, collapse whitespace.
    Used to fuzzy-match cache titles against scraped channel titles."""
    if not t:
        return ""
    s = unicodedata.normalize("NFD", t)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_handle(handle: str) -> str:
    """Accept '@name', 'youtube.com/@name', or full URL. Return '@name'."""
    if not handle:
        return ""
    h = handle.strip().rstrip("/")
    m = re.search(r"@([A-Za-z0-9._-]+)", h)
    if m:
        return "@" + m.group(1)
    if h.startswith("UC") and len(h) >= 22:  # raw channel ID
        return h
    return h


def fetch_tab(channel_url: str) -> list[dict]:
    """yt-dlp flat-extract a channel tab. Returns [{id, title, url, ...}]."""
    import yt_dlp
    opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
    except Exception as e:
        print(f"   yt-dlp failed for {channel_url}: {e}", flush=True)
        return []
    if not info:
        return []
    entries = info.get("entries") or []
    out: list[dict] = []
    for e in entries:
        if not e:
            continue
        vid = e.get("id") or ""
        title = e.get("title") or ""
        if not vid:
            continue
        out.append({
            "id": vid,
            "title": title,
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return out


_VIDEO_META_CACHE: dict[str, dict] = {}


def fetch_dislikes(video_id: str) -> int:
    """Estimate dislikes via the Return YouTube Dislike public API. YouTube
    itself stopped exposing dislikes in Dec 2021 — RYD is the de-facto source
    used by extensions/dashboards. Returns -1 when unavailable so callers can
    distinguish "no data" from "zero dislikes"."""
    try:
        import urllib.request
        import urllib.error
        url = f"https://returnyoutubedislikeapi.com/votes?videoId={video_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "MoneyPrinterLargo/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        d = payload.get("dislikes")
        return int(d) if d is not None else -1
    except Exception:
        return -1


def fetch_video_meta(video_id: str) -> dict:
    """Fetch upload_date + description + engagement counts for a single video.
    Cached per process. Returns {date, description, view_count, like_count,
    comment_count, dislike_count}. Missing numeric fields default to -1 so the
    UI can render "—" instead of confusing zeros."""
    if video_id in _VIDEO_META_CACHE:
        return _VIDEO_META_CACHE[video_id]
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "ignoreerrors": True}
    out = {
        "date": "",
        "description": "",
        "view_count": -1,
        "like_count": -1,
        "comment_count": -1,
        "dislike_count": -1,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}",
                                    download=False)
        if info:
            ts = info.get("timestamp")
            if ts:
                # Use local time (NOT utcfromtimestamp) so the date string is
                # consistent with the rest of the codebase (`datetime.now()`
                # in YouTube.py / Twitter.py). The frontend parses bare
                # "YYYY-MM-DD HH:MM:SS" strings as local time; mixing UTC
                # values made fresh syncs land in the future and stick at
                # the top of the list as "hace unos segundos" forever.
                out["date"] = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
            else:
                ud = info.get("upload_date") or ""
                if len(ud) == 8:
                    out["date"] = f"{ud[0:4]}-{ud[4:6]}-{ud[6:8]} 00:00:00"
            out["description"] = (info.get("description") or "").strip()
            for src, dst in (("view_count", "view_count"),
                             ("like_count", "like_count"),
                             ("comment_count", "comment_count")):
                v = info.get(src)
                if isinstance(v, int):
                    out[dst] = v
    except Exception as e:
        print(f"      (meta fetch failed for {video_id}: {str(e)[:80]})", flush=True)
    out["dislike_count"] = fetch_dislikes(video_id)
    _VIDEO_META_CACHE[video_id] = out
    return out


def fetch_channel(handle: str) -> tuple[dict[str, dict], dict[str, dict]]:
    """Return (longs_by_id, shorts_by_id). Each entry is {id, title, url, is_short}."""
    base = handle if handle.startswith(("http://", "https://")) else f"https://www.youtube.com/{handle}"
    base = base.rstrip("/")

    print(f"   -> longs:  {base}/videos", flush=True)
    longs = fetch_tab(f"{base}/videos")
    print(f"     got {len(longs)}", flush=True)
    print(f"   -> shorts: {base}/shorts", flush=True)
    shorts = fetch_tab(f"{base}/shorts")
    print(f"     got {len(shorts)}", flush=True)

    longs_by_id = {v["id"]: {**v, "is_short": False} for v in longs}
    shorts_by_id = {v["id"]: {**v, "is_short": True} for v in shorts}
    # Defensive: a short shouldn't ever appear in /videos too, but if it does
    # the /shorts tab wins (it's more specific).
    for sid in shorts_by_id:
        longs_by_id.pop(sid, None)
    return longs_by_id, shorts_by_id


def extract_video_id(url: str) -> str:
    """Extract video id from a watch / shorts / youtu.be URL."""
    if not url:
        return ""
    m = re.search(r"(?:v=|/shorts/|youtu\.be/|/embed/|/v/)([A-Za-z0-9_-]{6,16})", url)
    return m.group(1) if m else ""


def load_cache() -> dict:
    if not os.path.exists(CACHE_PATH):
        return {"accounts": []}
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        return json.load(f) or {"accounts": []}


def save_cache(data: dict) -> None:
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def sync_channel(acc: dict, handle: str, args, all_published: dict[str, dict],
                 by_norm_title: dict[str, dict]) -> tuple[int, int, int, int]:
    """Returns (reclassified, pruned, added, meta_refreshed)."""
    videos = acc.get("videos", []) or []
    matched_ids: set[str] = set()
    kept: list[dict] = []
    reclassified = 0
    pruned = 0
    meta_refreshed = 0

    def needs_meta(v: dict) -> bool:
        if not v.get("description") or not (v.get("description") or "").strip():
            return True
        d = v.get("date") or ""
        # Force refresh of dates the script (or the original generation) made
        # up — they're current local time of the run, not the YT upload time.
        return False

    # Pre-count videos that will need a (slow) yt-dlp meta call so the live
    # progress line below can show "meta N/T" — without this counter the UI
    # froze for several minutes per channel with no output.
    will_refresh = sum(
        1 for v in videos
        if extract_video_id(v.get("url", "") or "") in all_published
        and (args.refresh_meta or needs_meta(v) or args.refresh_dates)
    )
    if will_refresh:
        print(f"   meta-refresh queue: {will_refresh} video(s) "
              f"(~{will_refresh * (args.sleep + 1.5):.0f}s estimated)",
              flush=True)
    refresh_done = 0

    for v in videos:
        vid = extract_video_id(v.get("url", "") or "")
        match: Optional[dict] = None

        if vid and vid in all_published:
            match = all_published[vid]
        else:
            tnorm = normalize_title(v.get("title", ""))
            if tnorm and tnorm in by_norm_title:
                match = by_norm_title[tnorm]
                v["url"] = match["url"]
                print(f"   + filled URL via title match: {match['id']} -> {v.get('title','')[:60]!r}",
                      flush=True)

        if match is None:
            if args.prune:
                print(f"   - PRUNE (not on YT): {v.get('title','')[:70]!r}", flush=True)
                pruned += 1
                continue
            kept.append(v)
            continue

        matched_ids.add(match["id"])
        new_kind = bool(match["is_short"])
        if v.get("is_short") != new_kind:
            v["is_short"] = new_kind
            reclassified += 1
            tag = "SHORT" if new_kind else "LONG "
            print(f"   ~ {tag} {match['id']}  -> {v.get('title','')[:60]!r}", flush=True)
        else:
            v["is_short"] = new_kind

        # Pull real upload date + description from YouTube. Always refresh
        # date (cache dates are local generation time, not actual YT upload).
        # Refresh description only if missing — we don't want to overwrite
        # custom edits the user made.
        if args.refresh_meta or needs_meta(v) or args.refresh_dates:
            refresh_done += 1
            short_title = (v.get("title") or "").strip()[:55]
            print(f"   meta {refresh_done:>3}/{will_refresh:<3} {match['id']}  -> {short_title!r}",
                  flush=True)
            meta = fetch_video_meta(match["id"])
            if meta["date"] and (args.refresh_dates or args.refresh_meta or not v.get("date")):
                v["date"] = meta["date"]
            if meta["description"] and (args.refresh_meta or not (v.get("description") or "").strip()):
                v["description"] = meta["description"]
            # Engagement counters: always overwrite with the freshest values
            # (they are point-in-time, never user-edited).
            for k in ("view_count", "like_count", "comment_count", "dislike_count"):
                if meta.get(k, -1) >= 0:
                    v[k] = meta[k]
            if meta["date"] or meta["description"]:
                meta_refreshed += 1
            time.sleep(args.sleep)

        kept.append(v)

    # Add YT-only videos missing from cache, with full metadata.
    added = 0
    if args.add:
        for vid, info in all_published.items():
            if vid in matched_ids:
                continue
            meta = fetch_video_meta(vid)
            time.sleep(args.sleep)
            kept.append({
                "title": info["title"],
                "description": meta["description"] or "",
                "subject": info["title"],
                "url": info["url"],
                "date": meta["date"] or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "is_short": bool(info["is_short"]),
                "thumbnail_path": "",
                "view_count": meta.get("view_count", -1),
                "like_count": meta.get("like_count", -1),
                "comment_count": meta.get("comment_count", -1),
                "dislike_count": meta.get("dislike_count", -1),
            })
            added += 1
            tag = "SHORT" if info["is_short"] else "LONG "
            print(f"   + ADD  {tag} {vid} ({meta['date'] or '?'}) -> {info['title'][:55]!r}",
                  flush=True)

    # Deduplicate by video id. Multiple cache rows can map to the same YT
    # video when the user retried an upload or the legacy cache held both a
    # placeholder row + a real row. We keep the most "complete" entry (one
    # with a description). Ties broken by latest date.
    deduped: dict[str, dict] = {}
    no_id_kept: list[dict] = []
    dup_count = 0
    for v in kept:
        vid = extract_video_id(v.get("url", "") or "")
        if not vid:
            no_id_kept.append(v)
            continue
        if vid in deduped:
            dup_count += 1
            existing = deduped[vid]
            score_new = (1 if (v.get("description") or "").strip() else 0,
                         v.get("date") or "")
            score_old = (1 if (existing.get("description") or "").strip() else 0,
                         existing.get("date") or "")
            if score_new > score_old:
                deduped[vid] = v
        else:
            deduped[vid] = v
    if dup_count:
        print(f"   ~ deduped {dup_count} duplicate entries", flush=True)
    pruned += dup_count

    # Sort by date desc (most recent first) so the table shows real upload
    # order regardless of how the cache was assembled over time.
    final = list(deduped.values()) + no_id_kept
    final.sort(key=lambda x: x.get("date") or "", reverse=True)
    acc["videos"] = final
    return reclassified, pruned, added, meta_refreshed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--prune", action="store_true",
                    help="Delete cache entries that don't exist on the channel.")
    ap.add_argument("--add", action="store_true",
                    help="Add channel videos that are missing from the cache.")
    ap.add_argument("--refresh-meta", action="store_true",
                    help="Re-fetch description AND upload date from YouTube for every "
                         "matched video, overwriting whatever is in the cache.")
    ap.add_argument("--refresh-dates", action="store_true",
                    help="Re-fetch only the upload date (cheaper than --refresh-meta).")
    ap.add_argument("--channel-id", default="", help="Restrict to one channel UUID.")
    ap.add_argument("--handle", default="",
                    help="Override the handle (only valid with --channel-id).")
    ap.add_argument("--sleep", type=float, default=0.3,
                    help="Seconds between per-video metadata fetches.")
    args = ap.parse_args()

    if args.handle and not args.channel_id:
        print("--handle requires --channel-id", file=sys.stderr)
        return 1

    data = load_cache()
    total_r, total_p, total_a, total_m = 0, 0, 0, 0

    for acc in data.get("accounts", []):
        if args.channel_id and acc.get("id") != args.channel_id:
            continue
        handle = normalize_handle(args.handle or acc.get("youtube_handle", ""))
        nick = acc.get("nickname", acc.get("id", "?"))
        print(f"\n=== {nick} ===", flush=True)
        if not handle:
            print(f"   (skip — no youtube_handle configured for this channel; "
                  f"set it in webapp or pass --handle @yourchannel)", flush=True)
            continue
        print(f"   handle: {handle}", flush=True)

        longs_by_id, shorts_by_id = fetch_channel(handle)
        all_pub = {**longs_by_id, **shorts_by_id}
        if not all_pub:
            print("   (no videos returned by yt-dlp — wrong handle or rate-limited)",
                  flush=True)
            continue

        by_norm_title: dict[str, dict] = {}
        for v in all_pub.values():
            by_norm_title.setdefault(normalize_title(v["title"]), v)

        r, p, a, m = sync_channel(acc, handle, args, all_pub, by_norm_title)
        total_r += r
        total_p += p
        total_a += a
        total_m += m
        print(f"   -> reclassif: {r}, pruned: {p}, added: {a}, meta: {m}", flush=True)

    print(f"\n--- summary ---", flush=True)
    print(f"  reclassified: {total_r}", flush=True)
    print(f"  pruned:       {total_p}", flush=True)
    print(f"  added:        {total_a}", flush=True)
    print(f"  meta refresh: {total_m}", flush=True)
    if args.apply and (total_r or total_p or total_a or total_m):
        save_cache(data)
        print(f"  wrote: {CACHE_PATH}", flush=True)
    elif total_r or total_p or total_a or total_m:
        print("  (dry-run -- pass --apply to persist)", flush=True)
    else:
        print("  nothing to do", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

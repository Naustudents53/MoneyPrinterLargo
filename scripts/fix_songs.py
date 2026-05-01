"""Fix the 3 problem slots from the universe songs batch.

Force-re-download:
  - blazing_stars.mp3:      replace 1-hour mix with a single ~5min track
  - world_of_automatons.mp3: replace duplicate of Voltaic with a different track
  - trouble_on_mercury.mp3:  retry with broader candidates (originals 403'd)
"""

from __future__ import annotations

import re
import shutil
import sys
import urllib3
from pathlib import Path

import yt_dlp

urllib3.disable_warnings()

ROOT = Path(__file__).resolve().parent.parent
SONGS = ROOT / "Songs"

# Slot -> ordered list of candidate Kevin MacLeod tracks. We pick the first
# whose result is a) on a Kevin MacLeod-related channel, b) has a single-track
# title (no "1 HOUR" / "10 HOUR" / "loop"), and c) downloads successfully.
RETRIES: list[tuple[str, list[str]]] = [
    ("blazing_stars.mp3",       ["Killers", "Hot Pursuit", "Curse of the Scarab", "Anguish"]),
    ("world_of_automatons.mp3", ["Industrial Revolution", "Wallpaper", "Eyes Gone Wrong", "Crypto"]),
    ("trouble_on_mercury.mp3",  ["Hot Pursuit", "Curse of the Scarab", "Mysterioso March", "Crypto"]),
]


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def title_matches(found_title: str, target_title: str) -> bool:
    f = normalize(found_title)
    t = normalize(target_title)
    if t in f:
        return True
    words = [w for w in target_title.lower().split() if len(w) > 3]
    return bool(words) and all(normalize(w) in f for w in words)


def is_long_mix(title: str) -> bool:
    t = title.lower()
    return any(s in t for s in [" hour", "1 hour", "2 hour", "10 hour", "loop", " mix ", "extended"])


def safe_print(*args) -> None:
    msg = " ".join(str(a) for a in args)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def fetch(slot: str, candidates: list[str]) -> bool:
    out_path = SONGS / slot
    for title in candidates:
        for query in [
            f'"Kevin MacLeod" "{title}" Incompetech',
            f'Kevin MacLeod {title} incompetech.com',
        ]:
            safe_print(f"\n[SEARCH] {slot} via: {query}")
            try:
                with yt_dlp.YoutubeDL({
                    "default_search": "ytsearch10",
                    "quiet": True, "no_warnings": True,
                    "extract_flat": "in_playlist",
                    "nocheckcertificate": True,
                }) as ydl:
                    info = ydl.extract_info(query, download=False)
            except Exception as e:
                safe_print(f"  search error: {e}")
                continue

            entries = info.get("entries") or []
            chosen = None
            for entry in entries:
                t = entry.get("title", "") or ""
                ch = (entry.get("uploader") or entry.get("channel") or "").lower()
                if is_long_mix(t):
                    safe_print(f"  skip (long mix): {t!r}")
                    continue
                ch_ok = ("kevin" in ch and "macleod" in ch) or "incompetech" in ch
                if title_matches(t, title) and ch_ok:
                    chosen = entry
                    safe_print(f"  pick: {t!r} (channel={ch!r})")
                    break
            if not chosen:
                # Loosen channel constraint, still skip mixes
                for entry in entries:
                    t = entry.get("title", "") or ""
                    if is_long_mix(t):
                        continue
                    if title_matches(t, title) and "macleod" in t.lower():
                        chosen = entry
                        safe_print(f"  loose pick: {t!r}")
                        break
            if not chosen:
                continue

            url = chosen.get("url") or chosen.get("webpage_url") or chosen.get("id")
            if url and not url.startswith("http"):
                url = f"https://www.youtube.com/watch?v={url}"

            tmp = str(SONGS / f"__retry_{slot.replace('.mp3', '')}.%(ext)s")
            try:
                with yt_dlp.YoutubeDL({
                    "format": "bestaudio/best",
                    "outtmpl": tmp,
                    "postprocessors": [
                        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                    ],
                    "noplaylist": True,
                    "nocheckcertificate": True,
                    "quiet": True, "no_warnings": True,
                }) as ydl:
                    ydl.download([url])
            except Exception as e:
                safe_print(f"  download error: {e}")
                continue

            produced = list(SONGS.glob(f"__retry_{slot.replace('.mp3', '')}.*"))
            mp3 = next((p for p in produced if p.suffix.lower() == ".mp3"), None)
            for p in produced:
                if p != mp3 and p.exists():
                    try: p.unlink()
                    except Exception: pass
            if mp3 is None:
                continue

            # Reject if too large (likely a long mix)
            size_mb = mp3.stat().st_size / (1024 * 1024)
            if size_mb > 25:
                safe_print(f"  reject (too large {size_mb:.1f} MB)")
                mp3.unlink()
                continue

            if out_path.exists():
                out_path.unlink()
            shutil.move(str(mp3), str(out_path))
            safe_print(f"[OK]   {slot} <- {chosen.get('title')!r} ({size_mb:.1f} MB)")
            return True

    safe_print(f"[FAIL] {slot}")
    return False


def main() -> int:
    failures = 0
    for slot, cands in RETRIES:
        if not fetch(slot, cands):
            failures += 1
    safe_print(f"\nfailures: {failures}")
    return failures


if __name__ == "__main__":
    sys.exit(main())

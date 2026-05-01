"""Download universe / cosmos themed CC-BY tracks (Kevin MacLeod) into Songs/.

The project's `SONG_KEYWORDS` map in src/utils.py expects 12 specific filenames.
Some of those names match real Kevin MacLeod tracks; others appear to be a
private curation. We resolve each slot to the best available CC-BY space/sci-fi
track we can find on his official YouTube channel, and save it under the slot
filename so the keyword router in utils.py picks it up correctly.

Console output is ASCII-safe (no emojis) to avoid Windows cp1252 issues.
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
SONGS.mkdir(exist_ok=True)

# Slot filename (expected by SONG_KEYWORDS) -> list of candidate Kevin MacLeod
# tracks (in priority order). Tries the first; falls back to next on no match.
SLOTS: list[tuple[str, list[str]]] = [
    ("infinity_cosmos.mp3",       ["Infinite Perspective", "Floating Cities", "Sovereign Quarter"]),
    ("vastness_space.mp3",        ["Space Jazz", "Tranquility", "Perspectives"]),
    ("light_years_space.mp3",     ["Tranquility", "Perspectives", "Eternal Hope"]),
    ("red_lights_adhafera.mp3",   ["Mysterioso March", "The Voyage", "Static Motion"]),
    ("scifi_game.mp3",            ["Cyborg Ninja", "Voltaic", "Static Motion"]),
    ("transcending_science.mp3",  ["Dreams Become Real", "Severe Tire Damage", "Voltaic"]),
    ("trouble_on_mercury.mp3",    ["Trouble on Mercury", "Tenebrous Brothers Carnival - Intermission", "Cylinder Five"]),
    ("feedback_dreams.mp3",       ["Feedback Loops", "Dreams Become Real", "Killers"]),
    ("cold_moon.mp3",             ["Cold Funk", "Healing", "Constance"]),
    ("blazing_stars.mp3",         ["Galactic Damages", "Voltaic", "Severe Tire Damage"]),
    ("the_darkness_below.mp3",    ["Long Note Three", "The Descent", "Dark Mystery"]),
    ("world_of_automatons.mp3",   ["Voltaic", "Cyborg Ninja", "Industrial Revolution"]),
]


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def title_matches(found_title: str, target_title: str) -> bool:
    f = normalize(found_title)
    t = normalize(target_title)
    if t in f:
        return True
    words = [w for w in target_title.lower().split() if len(w) > 3]
    if not words:
        return False
    return all(normalize(w) in f for w in words)


def safe_print(*args) -> None:
    msg = " ".join(str(a) for a in args)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def search_and_download(slot: str, candidates: list[str]) -> bool:
    out_path = SONGS / slot
    if out_path.exists() and out_path.stat().st_size > 100_000:
        safe_print(f"[SKIP] {slot} exists ({out_path.stat().st_size} bytes)")
        return True

    for title in candidates:
        for query in [
            f'"Kevin MacLeod" "{title}" Incompetech',
            f'Kevin MacLeod {title} Incompetech',
        ]:
            safe_print(f"\n[SEARCH] {slot} via: {query}")
            try:
                with yt_dlp.YoutubeDL({
                    "default_search": "ytsearch5",
                    "quiet": True,
                    "no_warnings": True,
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
                safe_print(f"  candidate: {t!r} (channel={ch!r})")
                if title_matches(t, title) and ("kevin" in ch or "macleod" in ch or "incompetech" in ch or "incompetech" in t.lower()):
                    chosen = entry
                    break
            if not chosen:
                # Loosen: allow any channel if title strongly matches
                for entry in entries:
                    t = entry.get("title", "") or ""
                    if title_matches(t, title):
                        chosen = entry
                        safe_print(f"  (loose match accepted: {t!r})")
                        break
            if not chosen:
                continue

            url = chosen.get("url") or chosen.get("webpage_url") or chosen.get("id")
            if url and not url.startswith("http"):
                url = f"https://www.youtube.com/watch?v={url}"

            tmp_template = str(SONGS / f"__tmp_{slot.replace('.mp3', '')}.%(ext)s")
            try:
                with yt_dlp.YoutubeDL({
                    "format": "bestaudio/best",
                    "outtmpl": tmp_template,
                    "postprocessors": [
                        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                    ],
                    "noplaylist": True,
                    "nocheckcertificate": True,
                    "quiet": True,
                    "no_warnings": True,
                }) as ydl:
                    ydl.download([url])
            except Exception as e:
                safe_print(f"  download error: {e}")
                continue

            produced = list(SONGS.glob(f"__tmp_{slot.replace('.mp3', '')}.*"))
            mp3 = next((p for p in produced if p.suffix.lower() == ".mp3"), None)
            for p in produced:
                if p != mp3 and p.exists():
                    try: p.unlink()
                    except Exception: pass
            if mp3 is None:
                safe_print(f"  no mp3 produced")
                continue
            if out_path.exists():
                out_path.unlink()
            shutil.move(str(mp3), str(out_path))
            safe_print(f"[OK]   {slot} <- {chosen.get('title')!r} ({out_path.stat().st_size:,} bytes)")
            return True

    safe_print(f"[FAIL] {slot}: no candidate found")
    return False


def main() -> int:
    results: list[tuple[str, bool]] = []
    for slot, candidates in SLOTS:
        ok = search_and_download(slot, candidates)
        results.append((slot, ok))

    safe_print("\n=== SUMMARY ===")
    for slot, ok in results:
        safe_print(f"  [{('OK  ' if ok else 'FAIL')}] {slot}")
    failed = [s for s, ok in results if not ok]
    return 0 if not failed else len(failed)


if __name__ == "__main__":
    sys.exit(main())

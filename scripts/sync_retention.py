"""Sync REAL audience-retention data from YouTube Studio into the cache.

Usage (from the project root):

    python scripts/sync_retention.py                      # all channels
    python scripts/sync_retention.py --channel-id <uuid>  # one channel
    python scripts/sync_retention.py --max-videos 5

Requires the per-account Firefox profile to be logged into YouTube Studio
(the same requirement as uploading). Each channel opens its own browser,
scrapes Analytics → Engagement for the most recent videos, stores
`avg_percentage_viewed` / `retention_curve` / `retention_biggest_drop` on the
video records, and closes the browser. The LearningCoach picks the new data
up automatically on its next reflection.
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel-id", default="", help="Restrict to one channel UUID.")
    ap.add_argument("--max-videos", type=int, default=10,
                    help="Most-recent videos to sync per channel (default 10).")
    args = ap.parse_args()

    from cache import get_accounts
    from classes.YouTube import YouTube

    accounts = get_accounts("youtube")
    if args.channel_id:
        accounts = [a for a in accounts if a.get("id") == args.channel_id]
    if not accounts:
        print("No matching YouTube accounts in the cache.", file=sys.stderr)
        return 1

    exit_code = 0
    for acc in accounts:
        nick = acc.get("nickname", acc.get("id", "?"))
        print(f"\n=== {nick} ===", flush=True)
        youtube = None
        try:
            youtube = YouTube(
                acc["id"],
                acc["nickname"],
                acc.get("firefox_profile", ""),
                acc.get("niche", ""),
                acc.get("language", ""),
            )
            summary = youtube.sync_retention_curves(max_videos=args.max_videos)
            print(
                f"   fetched={summary['fetched']} stored={summary['stored']} "
                f"failed={summary['failed']}",
                flush=True,
            )
            if summary["stored"] == 0 and summary["failed"] > 0:
                exit_code = 2
        except Exception as exc:
            print(f"   ERROR: {str(exc)[:200]}", file=sys.stderr)
            exit_code = 2
        finally:
            try:
                if youtube is not None and youtube.browser is not None:
                    youtube.browser.quit()
            except Exception:
                pass

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

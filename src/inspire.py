"""Generate videos from YouTube Studio "Inspiration" ideas.

Scrapes the Inspiration playground for the given YouTube account
(https://studio.youtube.com/channel/<CHANNEL_ID>/content/inspiration/playground)
using the account's pre-authenticated Firefox profile, then feeds each
idea into the existing YouTube pipeline as a `custom_topic`.

Usage:
    python src/inspire.py <account_uuid_or_nickname> [--count N] [--upload]
                          [--channel-id UCxxxx] [--dry-run]

Run from the project root, like the rest of the entry points.
"""

import sys
import time
import argparse
import shutil
import tempfile
from typing import List, Optional

from status import info, success, warning, error
from cache import get_accounts
from config import (
    get_verbose,
    get_headless,
    get_llm_provider,
    get_pollinations_text_model,
)
from llm_provider import select_model, set_llm_provider
from classes.Tts import TTS
from classes.YouTube import YouTube

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


PLAYGROUND_URL = (
    "https://studio.youtube.com/channel/{channel_id}/content/inspiration/playground"
)
STUDIO_HOME = "https://studio.youtube.com/"


def _resolve_account(identifier: str) -> dict:
    """Find a YouTube account by UUID or nickname (case-insensitive)."""
    accounts = get_accounts("youtube") or []
    ident = (identifier or "").strip().lower()
    for acc in accounts:
        if acc.get("id", "").lower() == ident:
            return acc
    for acc in accounts:
        if acc.get("nickname", "").strip().lower() == ident:
            return acc
    raise SystemExit(
        f"No YouTube account found with id/nickname '{identifier}'. "
        f"Known nicknames: {[a.get('nickname') for a in accounts]}"
    )


def _make_driver(profile_path: str) -> "webdriver.Firefox":
    """Spin up Firefox using a copy of the account's logged-in profile.

    Mirrors the pattern in `YouTube.__init__` so we never lock the user's
    real profile while the inspiration scraper is running.
    """
    options = Options()
    if get_headless():
        options.add_argument("--headless")

    tmp_root = tempfile.mkdtemp(prefix="mpv2_inspire_")
    tmp_profile = f"{tmp_root}/profile"
    shutil.copytree(
        profile_path,
        tmp_profile,
        ignore=shutil.ignore_patterns(
            "lock", ".parentlock", "parent.lock",
            "cache2", "startupCache", "shader-cache",
            "thumbnails", "storage", "crashes",
        ),
    )
    options.add_argument("-profile")
    options.add_argument(tmp_profile)

    return webdriver.Firefox(options=options)


def _detect_channel_id(driver) -> Optional[str]:
    """Read the channel UC... id from whatever Studio URL we land on."""
    driver.get(STUDIO_HOME)
    WebDriverWait(driver, 30).until(
        lambda d: "/channel/UC" in d.current_url or "studio.youtube.com" in d.current_url
    )
    # Studio redirects to /channel/UCxxxx/... once the cookie loads.
    for _ in range(20):
        url = driver.current_url
        if "/channel/UC" in url:
            tail = url.split("/channel/", 1)[1]
            return tail.split("/", 1)[0]
        time.sleep(1)
    return None


# JS that walks the playground DOM and pulls the visible idea title from
# every inspiration card. YouTube Studio rewrites the markup often, so we
# stay generous: any element whose tag/class contains "inspiration" and
# that has a heading-ish descendant counts as a card.
_HARVEST_JS = r"""
const out = new Set();
const root = document.querySelector('ytcp-inspiration-tab-renderer')
          || document.querySelector('ytcp-content-inspiration')
          || document.body;
const cards = root.querySelectorAll(
  'ytcp-inspiration-card, ytcp-video-inspiration-card, ' +
  'ytcp-content-inspiration-card, [class*="inspiration-card"], ' +
  '[class*="InspirationCard"], ytcp-content-card'
);
const pickText = (el) => {
  const h = el.querySelector(
    '#title, .title, [class*="title"], yt-formatted-string, h1, h2, h3'
  );
  const t = (h ? h.textContent : el.textContent || '').trim();
  return t.replace(/\s+/g, ' ');
};
cards.forEach(c => {
  const t = pickText(c);
  if (t && t.length > 8 && t.length < 240) out.add(t);
});
return Array.from(out);
"""


def fetch_inspiration_ideas(driver, channel_id: str, max_wait: int = 45) -> List[str]:
    """Open the Inspiration playground and return the list of idea titles."""
    driver.get(PLAYGROUND_URL.format(channel_id=channel_id))

    end = time.time() + max_wait
    ideas: List[str] = []
    while time.time() < end:
        try:
            ideas = driver.execute_script(_HARVEST_JS) or []
        except Exception:
            ideas = []
        if ideas:
            break
        time.sleep(2)

    return ideas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("account", help="YouTube account UUID or nickname")
    parser.add_argument("--count", type=int, default=1,
                        help="How many ideas to turn into videos (default: 1)")
    parser.add_argument("--upload", action="store_true",
                        help="Upload each generated video to YouTube")
    parser.add_argument("--channel-id",
                        help="Skip auto-detection and use this UC... id")
    parser.add_argument("--dry-run", action="store_true",
                        help="Just print the inspiration ideas; don't render")
    parser.add_argument("--model",
                        help="Ollama model name (overrides interactive choice)")
    parser.add_argument("--topic", action="append", default=[],
                        help="Skip scraping and use this literal topic. "
                             "Pass multiple times for several videos.")
    args = parser.parse_args()

    set_llm_provider(get_llm_provider())
    if args.model:
        select_model(args.model)
    elif get_llm_provider() == "pollinations":
        select_model(get_pollinations_text_model() or "openai")
    else:
        error("No Ollama model specified. Pass --model <name>.")
        sys.exit(1)

    acc = _resolve_account(args.account)
    verbose = get_verbose()
    if verbose:
        info(f" => Using account '{acc.get('nickname')}' ({acc.get('id')})")

    if args.topic:
        ideas = list(args.topic)
        if verbose:
            info(f" => Using {len(ideas)} topic(s) from CLI, skipping scrape.")
    else:
        driver = _make_driver(acc["firefox_profile"])
        try:
            channel_id = args.channel_id or _detect_channel_id(driver)
            if not channel_id:
                error("Could not detect channel id from Studio. Pass --channel-id.")
                sys.exit(1)
            if verbose:
                info(f" => Loading Inspiration for channel {channel_id}")

            ideas = fetch_inspiration_ideas(driver, channel_id)
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    if not ideas:
        error("No inspiration ideas found. Is the playground available for "
              "this channel? Try opening it manually first.")
        sys.exit(1)

    info(f" => Found {len(ideas)} inspiration ideas:")
    for i, idea in enumerate(ideas, 1):
        info(f"    {i}. {idea}")

    if args.dry_run:
        return

    picks = ideas[: max(1, args.count)]
    tts = TTS()

    for idx, topic in enumerate(picks, 1):
        info(f" => [{idx}/{len(picks)}] Generating video for: {topic}")
        youtube = YouTube(
            acc["id"],
            acc["nickname"],
            acc["firefox_profile"],
            acc["niche"],
            acc["language"],
            image_style=acc.get("image_style", ""),
            short_voice=acc.get("short_voice", ""),
            long_voice=acc.get("long_voice", ""),
            hook_profile=acc.get("hook_profile", ""),
            voice_drama=acc.get("voice_drama", False),
        )

        video_path = youtube.generate_video(tts, custom_topic=topic)
        if not video_path:
            warning(f"Pipeline aborted for idea: {topic}")
            continue

        if args.upload:
            youtube.upload_video()
            success(f"Uploaded video for: {topic}")
        else:
            success(f"Rendered video at: {video_path}")


if __name__ == "__main__":
    main()

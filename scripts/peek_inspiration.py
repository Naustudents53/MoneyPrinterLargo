"""
One-off helper: open a YouTube Studio URL using the configured Firefox
profile, wait for the SPA to render, then dump a screenshot + page text so
the assistant can read what's on the inspiration playground.

Run from project root:
    python scripts/peek_inspiration.py "<url>"
"""
import json
import os
import shutil
import sys
import tempfile
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))

from cache import get_temp_cache_path

from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service
from webdriver_manager.firefox import GeckoDriverManager


def main(url: str) -> None:
    cfg = json.load(open(os.path.join(ROOT_DIR, "config.json")))
    src_profile = cfg["firefox_profile"]
    if not os.path.isdir(src_profile):
        raise SystemExit(f"firefox_profile not found: {src_profile}")

    out_dir = get_temp_cache_path()
    os.makedirs(out_dir, exist_ok=True)
    shot_path = os.path.join(out_dir, "inspiration.png")
    text_path = os.path.join(out_dir, "inspiration.txt")
    html_path = os.path.join(out_dir, "inspiration.html")

    tmp = tempfile.mkdtemp(prefix="mpv2_peek_")
    profile = os.path.join(tmp, "profile")
    print(f"[+] Copying Firefox profile -> {profile}")
    shutil.copytree(
        src_profile, profile,
        ignore=shutil.ignore_patterns(
            "lock", ".parentlock", "parent.lock",
            "cache2", "startupCache", "shader-cache",
            "thumbnails", "storage", "crashes",
        ),
        dirs_exist_ok=False,
    )
    for bad in ["sessionstore.jsonlz4", "sessionstore-backups"]:
        p = os.path.join(profile, bad)
        if os.path.isfile(p):
            os.remove(p)
        elif os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)

    opts = FirefoxOptions()
    opts.add_argument("-profile")
    opts.add_argument(profile)
    opts.add_argument("--width=1600")
    opts.add_argument("--height=2000")
    # NOT headless: YouTube Studio sometimes detects headless and blanks.

    print("[+] Launching Firefox...")
    service = Service(GeckoDriverManager().install())
    driver = webdriver.Firefox(service=service, options=opts)
    try:
        driver.set_window_size(1600, 2000)
        print(f"[+] Navigating: {url}")
        driver.get(url)

        # SPA hydration. Poll the body text length until it stabilizes.
        last = -1
        for i in range(30):
            time.sleep(2)
            try:
                length = driver.execute_script("return (document.body && document.body.innerText) ? document.body.innerText.length : 0")
            except Exception:
                length = 0
            if length is None:
                length = 0
            print(f"  [poll {i}] body.innerText length = {length}")
            if length > 200 and length == last:
                break
            last = length

        # Try to scroll the inspiration card area into view, in case content
        # is virtualized.
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        print(f"[+] Saving screenshot -> {shot_path}")
        driver.save_screenshot(shot_path)

        text = driver.execute_script("return document.body.innerText") or ""
        print(f"[+] Saving body text ({len(text)} chars) -> {text_path}")
        open(text_path, "w", encoding="utf-8").write(text)

        html = driver.page_source or ""
        print(f"[+] Saving page source ({len(html)} chars) -> {html_path}")
        open(html_path, "w", encoding="utf-8").write(html)

    finally:
        try:
            driver.quit()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
    print("[done]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python scripts/peek_inspiration.py <url>")
    main(sys.argv[1])

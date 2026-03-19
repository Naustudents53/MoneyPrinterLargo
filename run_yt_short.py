"""
Run the full YouTube Shorts pipeline: generate video + upload.
Uses the existing cached account "Mind Glitch".
"""
import sys
import os
import json
import traceback

# Log all output to file
import io

class TeeWriter:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()
    def flush(self):
        for s in self.streams:
            s.flush()

_logfile = open("run_yt_short.log", "w", encoding="utf-8")
sys.stdout = TeeWriter(sys.__stdout__, _logfile)
sys.stderr = TeeWriter(sys.__stderr__, _logfile)

sys.path.insert(0, "src")

# Fix Pillow 10+ compat
from PIL import Image as _PILImage
if not hasattr(_PILImage, "ANTIALIAS"):
    _PILImage.ANTIALIAS = _PILImage.LANCZOS

# Setup ffmpeg
import shutil
if not shutil.which("ffmpeg"):
    search = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.isdir(search):
        for root, dirs, files in os.walk(search):
            if "ffmpeg.exe" in files:
                os.environ["PATH"] = root + os.pathsep + os.environ.get("PATH", "")
                break

from config import ROOT_DIR, assert_folder_structure
from llm_provider import set_llm_provider, select_model
from utils import rem_temp_files, fetch_songs
from classes.Tts import TTS
from classes.YouTube import YouTube
from cache import get_accounts

# Setup
assert_folder_structure()
rem_temp_files()
fetch_songs()
set_llm_provider("pollinations")
select_model("openai")

try:
    # Get the cached YouTube account
    accounts = get_accounts("youtube")
    if not accounts:
        print("ERROR: No YouTube accounts found in cache!")
        sys.exit(1)

    account = accounts[0]
    print(f"Using account: {account['nickname']} ({account['id']})")
    print(f"Niche: {account['niche']}, Language: {account['language']}")
    print(f"Firefox profile: {account['firefox_profile']}")

    # Create YouTube instance and run
    print("\n=== Creating YouTube instance ===")
    yt = YouTube(
        account["id"],
        account["nickname"],
        account["firefox_profile"],
        account["niche"],
        account["language"],
    )

    print("\n=== Generating video ===")
    tts = TTS()
    video_path = yt.generate_video(tts)
    print(f"\nVideo generated at: {video_path}")
    print(f"Size: {os.path.getsize(video_path) // 1024}KB")

    print("\n=== Uploading to YouTube ===")
    try:
        result = yt.upload_video()
        print(f"Upload result: {result}")
        if hasattr(yt, 'uploaded_video_url'):
            print(f"Video URL: {yt.uploaded_video_url}")
    except Exception as e:
        print(f"Upload failed with error: {e}")
        traceback.print_exc()

    print("\nDone!")
except Exception as e:
    print(f"\n\nFATAL ERROR: {e}")
    traceback.print_exc()

_logfile.close()

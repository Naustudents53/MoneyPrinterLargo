"""
Test: Upload an existing video to YouTube via Selenium.
This tests ONLY the upload flow, no video generation.
"""
import sys, os, time, json, traceback

sys.path.insert(0, "src")

from PIL import Image as _PILImage
if not hasattr(_PILImage, "ANTIALIAS"):
    _PILImage.ANTIALIAS = _PILImage.LANCZOS

from config import get_verbose, get_headless
from status import info, success, warning, error

# Load account from cache
with open(".mp/youtube.json", "r") as f:
    data = json.load(f)

account = data["accounts"][0]
print(f"Account: {account['nickname']}")
print(f"Profile: {account['firefox_profile']}")
print(f"Niche:   {account['niche']}")

video_path = os.path.abspath("generated_short.mp4")
print(f"Video:   {video_path}")
print(f"Size:    {os.path.getsize(video_path) // 1024}KB")

if not os.path.exists(video_path):
    print("ERROR: No video found!")
    sys.exit(1)

# Create YouTube instance
print("\n[1] Initializing YouTube class (opens Firefox)...")
from classes.YouTube import YouTube

yt = YouTube(
    account_uuid=account["id"],
    account_nickname=account["nickname"],
    fp_profile_path=account["firefox_profile"],
    niche=account["niche"],
    language=account.get("language", "Spanish"),
)

# Set video path and metadata manually
yt.video_path = video_path
yt.metadata = {
    "title": "Agujeros negros: datos que no sabias #ciencia #shorts",
    "description": "Descubre datos increibles sobre los agujeros negros. La ciencia detras del misterio del universo.",
}

print(f"[2] Title: {yt.metadata['title']}")
print(f"[3] Description: {yt.metadata['description']}")

# Upload
print("\n[4] Starting upload to YouTube...")
print("    (Firefox should open and navigate to YouTube Studio)")
print("    (Watch the browser to see the automation in action)")
print()

result = yt.upload_video()

if result:
    print(f"\n=== UPLOAD SUCCESSFUL! ===")
    print(f"URL: {yt.uploaded_video_url}")
else:
    print(f"\n=== UPLOAD FAILED ===")
    print("Check the error messages above for details.")

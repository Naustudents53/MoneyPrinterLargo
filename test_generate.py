"""
Full end-to-end test: Generate a YouTube Short using 100% free opensource tools.
"""
import sys
import os
import re
import json
import time
import random
import shutil
import requests
import urllib.parse

sys.path.insert(0, "src")

# Fix Pillow 10+ compatibility with MoviePy (ANTIALIAS was removed, now LANCZOS)
from PIL import Image as _PILImage
if not hasattr(_PILImage, "ANTIALIAS"):
    _PILImage.ANTIALIAS = _PILImage.LANCZOS

# Setup ffmpeg in PATH
if not shutil.which("ffmpeg"):
    search = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.isdir(search):
        for root, dirs, files in os.walk(search):
            if "ffmpeg.exe" in files:
                os.environ["PATH"] = root + os.pathsep + os.environ.get("PATH", "")
                break

from config import ROOT_DIR, get_fonts_dir, get_font, get_imagemagick_path
from llm_provider import set_llm_provider, select_model, generate_text
from classes.Tts import TTS
from uuid import uuid4

# Setup
os.makedirs(".mp", exist_ok=True)
set_llm_provider("pollinations")
select_model("openai")

print("========================================")
print("  MoneyPrinterV2 - Video Generation")
print("  Using 100% FREE opensource tools")
print("========================================")

# Step 1: Topic
print("\n[1/7] Generating topic...")
topic = generate_text(
    "Please generate a specific video idea about artificial intelligence. "
    "Make it exactly one sentence. Only return the topic, nothing else."
)
print(f"  Topic: {topic}")

# Step 2: Script
print("\n[2/7] Generating script...")
script = generate_text(
    f"Generate a script for a video in 4 sentences about: {topic}. "
    "Get straight to the point. No markdown. No special characters. "
    "Only return the raw script text."
)
script = re.sub(r"[*#]", "", script)
print(f"  Script: {script[:200]}...")

# Step 3: Metadata
print("\n[3/7] Generating metadata...")
title = generate_text(
    f"Generate a YouTube Video Title for: {topic}. "
    "Include hashtags. Under 100 chars. Only return the title."
)
description = generate_text(
    f"Generate a YouTube Video Description for: {script}. "
    "Only return the description."
)
print(f"  Title: {title}")
print(f"  Description: {description[:100]}...")

# Step 4: Image prompts
print("\n[4/7] Generating image prompts...")
prompts_raw = generate_text(
    f"Generate 3 Image Prompts for AI Image Generation about: {topic}. "
    'Return ONLY a JSON array of strings. Example: ["prompt 1", "prompt 2", "prompt 3"]. '
    "Make prompts detailed and emotional."
)
prompts_raw = prompts_raw.replace("```json", "").replace("```", "")
try:
    image_prompts = json.loads(prompts_raw)
except Exception:
    match = re.search(r"\[.*\]", prompts_raw, re.DOTALL)
    if match:
        image_prompts = json.loads(match.group())
    else:
        image_prompts = [
            "futuristic AI robot thinking deeply",
            "neural network glowing blue connections",
            "human and AI collaboration future",
        ]

print(f"  Prompts: {len(image_prompts)} generated")
for i, p in enumerate(image_prompts):
    print(f"    {i+1}. {p[:80]}")

# Step 5: Generate images
print("\n[5/7] Generating images via Pollinations.ai...")
images = []
for i, prompt in enumerate(image_prompts):
    # Keep prompts short to avoid URL issues
    short_prompt = prompt[:150]
    encoded = urllib.parse.quote(short_prompt)
    seed = int(time.time()) + i
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1080&height=1920&nologo=true&seed={seed}"
    )
    print(f"  Image {i+1}/{len(image_prompts)}: requesting...", end=" ", flush=True)

    success = False
    for attempt in range(5):
        try:
            if attempt > 0:
                wait = 15 + (10 * attempt)
                print(f"retry in {wait}s...", end=" ", flush=True)
                time.sleep(wait)
            resp = requests.get(url, timeout=300)
            if resp.status_code == 200 and len(resp.content) > 5000:
                img_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
                with open(img_path, "wb") as f:
                    f.write(resp.content)
                images.append(img_path)
                print(f"OK ({len(resp.content)//1024}KB)")
                success = True
                break
            elif resp.status_code == 429:
                print("rate-limited...", end=" ", flush=True)
            else:
                print(f"status {resp.status_code}...", end=" ", flush=True)
        except requests.exceptions.Timeout:
            print("timeout...", end=" ", flush=True)
        except Exception as e:
            print(f"error: {e}...", end=" ", flush=True)

    if not success:
        # Fallback: generate a gradient image with text
        from PIL import Image, ImageDraw, ImageFont

        colors = [(25, 25, 112), (75, 0, 130), (0, 100, 100)]
        img = Image.new("RGB", (1080, 1920), color=colors[i % len(colors)])
        draw = ImageDraw.Draw(img)
        # Add gradient effect
        for y_pos in range(1920):
            r = int(colors[i % len(colors)][0] * (1 - y_pos / 1920) + 20)
            g = int(colors[i % len(colors)][1] * (1 - y_pos / 1920) + 10)
            b = int(colors[i % len(colors)][2] * (1 - y_pos / 1920) + 40)
            draw.line([(0, y_pos), (1080, y_pos)], fill=(r, g, b))

        try:
            font = ImageFont.truetype(os.path.join(get_fonts_dir(), get_font()), 52)
        except Exception:
            font = ImageFont.load_default()

        words = prompt.split()
        y = 750
        line = ""
        for w in words:
            test = f"{line} {w}".strip()
            if len(test) > 25:
                bbox = draw.textbbox((0, 0), line, font=font)
                draw.text(((1080 - (bbox[2] - bbox[0])) // 2, y), line, fill="white", font=font)
                y += 70
                line = w
            else:
                line = test
        if line:
            bbox = draw.textbbox((0, 0), line, font=font)
            draw.text(((1080 - (bbox[2] - bbox[0])) // 2, y), line, fill="white", font=font)
        img_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
        img.save(img_path)
        images.append(img_path)
        print("fallback image created")

    # Delay between requests to avoid rate limiting
    if i < len(image_prompts) - 1:
        time.sleep(10)

# Step 6: TTS
print("\n[6/7] Generating voice-over via Edge-TTS...")
tts = TTS()
audio_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".wav")
clean_script = re.sub(r"[^\w\s.?!,]", "", script)
tts.synthesize(clean_script, audio_path)
print(f"  Audio: {os.path.getsize(audio_path)//1024}KB")

# Step 7: Combine video
print("\n[7/7] Combining into final video...")
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    CompositeAudioClip,
    concatenate_videoclips,
    afx,
)
from moviepy.video.fx.all import crop
from moviepy.config import change_settings

change_settings({"IMAGEMAGICK_BINARY": get_imagemagick_path()})

tts_clip = AudioFileClip(audio_path)
max_duration = tts_clip.duration
req_dur = max_duration / len(images)

print(f"  Duration: {max_duration:.1f}s, {len(images)} images, {req_dur:.1f}s each")

clips = []
tot_dur = 0
while tot_dur < max_duration:
    for image_path in images:
        clip = ImageClip(image_path)
        clip.duration = req_dur
        clip = clip.set_fps(30)
        if round((clip.w / clip.h), 4) < 0.5625:
            clip = crop(
                clip,
                width=clip.w,
                height=round(clip.w / 0.5625),
                x_center=clip.w / 2,
                y_center=clip.h / 2,
            )
        else:
            clip = crop(
                clip,
                width=round(0.5625 * clip.h),
                height=clip.h,
                x_center=clip.w / 2,
                y_center=clip.h / 2,
            )
        clip = clip.resize((1080, 1920))
        clips.append(clip)
        tot_dur += clip.duration

final_clip = concatenate_videoclips(clips)
final_clip = final_clip.set_fps(30)

# Add background music
songs_dir = os.path.join(ROOT_DIR, "Songs")
songs = [f for f in os.listdir(songs_dir) if f.endswith((".mp3", ".wav"))]
if songs:
    song_path = os.path.join(songs_dir, random.choice(songs))
    song_clip = AudioFileClip(song_path).set_fps(44100)
    song_clip = song_clip.fx(afx.volumex, 0.1)
    comp_audio = CompositeAudioClip([tts_clip.set_fps(44100), song_clip])
    final_clip = final_clip.set_audio(comp_audio)
else:
    final_clip = final_clip.set_audio(tts_clip)

final_clip = final_clip.set_duration(tts_clip.duration)

output_path = os.path.join(ROOT_DIR, "generated_short.mp4")
print("  Encoding video...")
final_clip.write_videofile(output_path, threads=2, logger="bar")

file_size = os.path.getsize(output_path)
print(f"\n========================================")
print(f"  VIDEO GENERATED SUCCESSFULLY!")
print(f"  File: {output_path}")
print(f"  Size: {file_size // 1024}KB ({file_size // (1024*1024)}MB)")
print(f"  Duration: {max_duration:.1f} seconds")
print(f"  Resolution: 1080x1920 (YouTube Shorts)")
print(f"========================================")
print(f"\n  Title: {title}")
print(f"\n  Tools used (all FREE):")
print(f"    - LLM: Pollinations.ai")
print(f"    - Images: Pollinations.ai")
print(f"    - Voice: Edge-TTS (Microsoft)")
print(f"    - Video: MoviePy + FFmpeg")

"""
Standalone thumbnail generator: Leonardo AI background + Pillow text overlay.

Usage:
    python scripts/make_thumbnail.py --topic "El colapso de civilizaciones" --text "EL PATRON OCULTO"

Output is saved to the project root so it survives `rem_temp_files()`.
"""
import argparse
import io
import json
import os
import re
import sys
import time
from uuid import uuid4

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THUMB_W, THUMB_H = 1280, 720


def get_leonardo_api_key() -> str:
    cfg = os.path.join(ROOT_DIR, "config.json")
    with open(cfg, "r", encoding="utf-8") as f:
        return json.load(f).get("leonardo_api_key", "").strip()


def call_leonardo(prompt: str, api_key: str) -> bytes:
    print(f"[Leonardo] Generating: {prompt[:80]}...", flush=True)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "prompt": prompt[:1000],
        "modelId": "b24e16ff-06e3-43eb-8d33-4416c2d75876",  # Leonardo Lightning XL
        "width": 1024,
        "height": 576,
        "num_images": 1,
    }
    resp = requests.post(
        "https://cloud.leonardo.ai/api/rest/v1/generations",
        headers=headers, json=payload, timeout=30,
    )
    resp.raise_for_status()
    gen_id = resp.json().get("sdGenerationJob", {}).get("generationId", "")
    if not gen_id:
        raise RuntimeError("Leonardo: no generation ID returned")

    for _ in range(36):  # up to 3 min
        time.sleep(5)
        s = requests.get(
            f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}",
            headers=headers, timeout=15,
        )
        s.raise_for_status()
        gen = s.json().get("generations_by_pk", {})
        status = gen.get("status", "")
        if status == "COMPLETE":
            images = gen.get("generated_images", [])
            if not images:
                raise RuntimeError("Leonardo: no images in result")
            img_url = images[0].get("url", "")
            r = requests.get(img_url, timeout=60)
            r.raise_for_status()
            print("[Leonardo] OK", flush=True)
            return r.content
        if status == "FAILED":
            raise RuntimeError("Leonardo: generation failed")
    raise RuntimeError("Leonardo: timed out waiting for generation")


def compose(bg_bytes: bytes, overlay: str, out_path: str) -> str:
    bg = Image.open(io.BytesIO(bg_bytes)).convert("RGB").resize(
        (THUMB_W, THUMB_H), Image.LANCZOS
    )

    # Bottom-left vignette via numpy.
    veil_start_y = int(THUMB_H * 0.45)
    veil_end_x = int(THUMB_W * 0.70)
    ys = np.arange(THUMB_H).reshape(-1, 1).astype(np.float32)
    xs = np.arange(THUMB_W).reshape(1, -1).astype(np.float32)
    v = np.clip((ys - veil_start_y) / max(1, THUMB_H - veil_start_y), 0.0, 1.0)
    h = np.clip(1.0 - (xs / max(1, veil_end_x)), 0.0, 1.0)
    alpha = (210.0 * v * h).astype(np.uint8)
    veil_arr = np.zeros((THUMB_H, THUMB_W, 4), dtype=np.uint8)
    veil_arr[..., 3] = alpha
    veil = Image.fromarray(veil_arr, "RGBA")
    bg = Image.alpha_composite(bg.convert("RGBA"), veil).convert("RGB")

    # Find a good font.
    font_path = None
    for cand in (r"C:\Windows\Fonts\impact.ttf", r"C:\Windows\Fonts\arialbd.ttf"):
        if os.path.isfile(cand):
            font_path = cand
            break

    overlay = overlay.upper()
    margin_left = 60
    margin_right = THUMB_W - int(THUMB_W * 0.42)
    max_w = margin_right - margin_left

    def wrap(text: str, fnt) -> list:
        wrapped, current = [], []
        d = ImageDraw.Draw(bg)
        for w in text.split():
            trial = " ".join(current + [w])
            if d.textbbox((0, 0), trial, font=fnt)[2] <= max_w:
                current.append(w)
            else:
                if current:
                    wrapped.append(" ".join(current))
                current = [w]
        if current:
            wrapped.append(" ".join(current))
        return wrapped

    font_size = 130
    font = None
    lines = [overlay]
    while font_size >= 50:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
        lines = wrap(overlay, font)
        if len(lines) <= 3:
            break
        font_size -= 8

    draw = ImageDraw.Draw(bg)
    line_h = int(font_size * 1.05)
    total_h = line_h * len(lines)
    y = THUMB_H - total_h - 50
    for line in lines:
        draw.text(
            (margin_left, y), line, font=font,
            fill=(255, 255, 255),
            stroke_width=10, stroke_fill=(0, 0, 0),
        )
        y += line_h

    bg.save(out_path, "PNG")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True, help="Topic of the video (drives the visual prompt).")
    ap.add_argument("--text", required=True, help="Overlay text (will be uppercased).")
    ap.add_argument("--visual", default="", help="Optional explicit visual prompt (English).")
    ap.add_argument("--out", default="", help="Output PNG path. Defaults to project root.")
    args = ap.parse_args()

    if not args.visual:
        # Build a strong topic-anchored visual prompt.
        args.visual = (
            f"Massive ancient Roman ruins at dusk, crumbling colosseum and broken marble columns "
            f"covered in moss, dramatic stormy sky with golden sunset rays piercing dark clouds, "
            f"fallen statues, abandoned forum, empty amphitheater, sense of grandeur lost, "
            f"atmospheric haze, cinematic wide shot, photorealistic, ultra-detailed, 8K, "
            f"no text, no letters, no logos, no watermark"
        )

    out_path = args.out or os.path.join(
        ROOT_DIR, f"thumb_{re.sub(r'[^a-z0-9]+', '_', args.text.lower())[:40]}_{uuid4().hex[:6]}.png"
    )

    api_key = get_leonardo_api_key()
    if not api_key:
        print("ERROR: leonardo_api_key not set in config.json", file=sys.stderr)
        sys.exit(1)

    bg_bytes = call_leonardo(args.visual, api_key)
    final = compose(bg_bytes, args.text, out_path)
    print(f"\nSaved thumbnail: {final}")


if __name__ == "__main__":
    main()

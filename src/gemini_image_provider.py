import base64
from io import BytesIO

import requests
from PIL import Image

from config import (
    get_nanobanana2_api_base_url,
    get_nanobanana2_api_key,
    get_nanobanana2_aspect_ratio,
    get_nanobanana2_model,
)


def _aspect_ratio_for_size(width: int, height: int) -> str:
    if width > height:
        return "16:9"
    if height > width:
        return "9:16"
    return get_nanobanana2_aspect_ratio()


def _normalize_image_bytes(image_bytes: bytes, width: int, height: int) -> bytes:
    if not image_bytes or len(image_bytes) < 1000:
        raise RuntimeError("Nano Banana returned an empty image")
    with Image.open(BytesIO(image_bytes)) as img:
        img.load()
        if img.width < 256 or img.height < 256:
            raise RuntimeError(f"Nano Banana image is too small: {img.width}x{img.height}")
        img = img.convert("RGB")
        if img.size != (width, height):
            img = img.resize((width, height), Image.LANCZOS)
        out = BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()


def _extract_inline_image(data: dict) -> bytes:
    for candidate in data.get("candidates", []) or []:
        parts = ((candidate.get("content") or {}).get("parts") or [])
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data")
            if not isinstance(inline, dict):
                continue
            payload = inline.get("data")
            if payload:
                return base64.b64decode(payload)
    raise RuntimeError(f"Nano Banana returned no inline image: {str(data)[:500]}")


def generate_image_bytes_with_gemini(prompt: str, *, width: int, height: int) -> bytes:
    """Generate a PNG via Gemini native image generation, aka Nano Banana."""
    api_key = get_nanobanana2_api_key()
    if not api_key:
        raise RuntimeError("Nano Banana/Gemini API key not configured")

    model = get_nanobanana2_model()
    base_url = get_nanobanana2_api_base_url().rstrip("/")
    url = f"{base_url}/models/{model}:generateContent?key={api_key}"
    aspect_ratio = _aspect_ratio_for_size(width, height)
    payload = {
        "contents": [{
            "parts": [{
                "text": (
                    "Create exactly one production-ready YouTube visual. "
                    "No text, no captions, no logos, no watermark. "
                    f"Composition: {aspect_ratio}. Prompt: {prompt[:2500]}"
                )
            }]
        }],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {
                "aspectRatio": aspect_ratio,
            },
        },
    }

    response = requests.post(url, json=payload, timeout=180)
    if response.status_code >= 400:
        raise RuntimeError(f"Nano Banana HTTP {response.status_code}: {response.text[:500]}")
    return _normalize_image_bytes(_extract_inline_image(response.json()), width, height)

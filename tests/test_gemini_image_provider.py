import base64
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import gemini_image_provider


class _Response:
    status_code = 200
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_generate_image_bytes_with_gemini_reads_inline_png(monkeypatch):
    img = Image.new("RGB", (512, 512), "navy")
    out = BytesIO()
    img.save(out, format="PNG")
    payload = base64.b64encode(out.getvalue()).decode("ascii")
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response({
            "candidates": [{
                "content": {
                    "parts": [{
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": payload,
                        }
                    }]
                }
            }]
        })

    monkeypatch.setattr(gemini_image_provider, "get_nanobanana2_api_key", lambda: "key")
    monkeypatch.setattr(gemini_image_provider, "get_nanobanana2_model", lambda: "gemini-image-test")
    monkeypatch.setattr(gemini_image_provider, "get_nanobanana2_api_base_url", lambda: "https://example.test/v1beta")
    monkeypatch.setattr(gemini_image_provider.requests, "post", fake_post)

    data = gemini_image_provider.generate_image_bytes_with_gemini(
        "Jupiter impact scar",
        width=1080,
        height=1920,
    )

    assert data.startswith(b"\x89PNG")
    assert captured["url"] == "https://example.test/v1beta/models/gemini-image-test:generateContent?key=key"
    assert captured["json"]["generationConfig"]["responseModalities"] == ["IMAGE"]
    assert captured["json"]["generationConfig"]["imageConfig"]["aspectRatio"] == "9:16"
    assert "Jupiter impact scar" in captured["json"]["contents"][0]["parts"][0]["text"]

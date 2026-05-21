import os
import subprocess
from io import BytesIO
from uuid import uuid4

from PIL import Image

from config import (
    ROOT_DIR,
    get_codex_cli_command,
    get_codex_cli_image_sandbox,
    get_codex_cli_image_timeout_seconds,
    get_codex_cli_model,
    get_openai_reasoning_effort,
)
from cache import get_temp_cache_path


def _build_codex_image_prompt(prompt: str, output_path: str, width: int, height: int) -> str:
    orientation = "vertical 9:16" if height > width else "landscape 16:9"
    return f"""Generate exactly one production-ready image for MoneyPrinter Largo.

Save the final image file here:
{output_path}

Canvas:
- {width}x{height}px
- PNG format
- {orientation}
- Native 4K/UHD detail when the requested canvas is 4K-sized; do not create a low-resolution draft and upscale it.

Visual prompt:
{prompt}

Hard requirements:
- Create the image file at the exact path above.
- Use your available OpenAI image-generation capability for the visual when available, preferably Image 2.
- Do not write explanatory text into the image unless the prompt explicitly asks for text.
- Do not create or modify any project files except the requested output image.
- Final assistant response must be only: DONE
"""


def _normalize_image_bytes(path: str, width: int, height: int) -> bytes:
    if not os.path.isfile(path):
        raise RuntimeError("Codex CLI did not create the requested image file")
    if os.path.getsize(path) < 1000:
        raise RuntimeError("Codex CLI image file is too small")

    with Image.open(path) as img:
        img.load()
        if img.width < 256 or img.height < 256:
            raise RuntimeError(f"Codex CLI image is too small: {img.width}x{img.height}")
        img = img.convert("RGB")
        if img.size != (width, height):
            img = img.resize((width, height), Image.LANCZOS)
        out = BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()


def generate_image_bytes_with_codex(prompt: str, *, width: int, height: int, model: str = "") -> bytes:
    """Ask the locally logged-in Codex CLI to generate a PNG and return its bytes."""
    mp_dir = get_temp_cache_path()
    os.makedirs(mp_dir, exist_ok=True)

    output_path = os.path.join(mp_dir, f"codex-image-{uuid4()}.png")
    message_path = os.path.join(mp_dir, f"codex-image-{uuid4()}.txt")
    selected_model = (model or get_codex_cli_model() or "").strip()
    effort = get_openai_reasoning_effort().lower()

    args = [
        get_codex_cli_command(),
        "-c",
        f'model_reasoning_effort="{effort}"',
        "--ask-for-approval",
        "never",
        "exec",
        "--cd",
        str(ROOT_DIR),
        "--sandbox",
        get_codex_cli_image_sandbox(),
        "--color",
        "never",
        "--ephemeral",
        "--output-last-message",
        message_path,
    ]
    if selected_model:
        args += ["--model", selected_model]
    args.append("-")

    try:
        result = subprocess.run(
            args,
            input=_build_codex_image_prompt(prompt, output_path, width, height),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=get_codex_cli_image_timeout_seconds(),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"codex exec exited {result.returncode}: {detail[-1000:]}")
        return _normalize_image_bytes(output_path, width, height)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Codex CLI was not found on PATH. Install/login with `codex login` "
            "or set MP_CODEX_CLI_COMMAND."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("codex exec timed out while generating an image") from exc
    finally:
        for path in (output_path, message_path):
            try:
                os.remove(path)
            except OSError:
                pass

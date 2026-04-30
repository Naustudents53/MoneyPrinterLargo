"""
Generate a long-form YouTube video from a YouTube Studio "inspiration playground"
URL.

Pipeline:
  1. Open the URL in Firefox using your pre-authenticated profile.
  2. Scrape the rendered text (title, description, hook, outline, suggested titles).
  3. Ask DeepSeek V4 Pro Cloud to fold all that into a single Spanish `custom_topic`
     brief (dense, narrative, sub-themes spelled out — the long-video pipeline
     uses this to plan the 15-20 min script).
  4. Instantiate the YouTube class for the configured account and run
     `generate_long_video(tts, custom_topic=brief)`.
  5. Optionally upload (off by default — pass --upload to publish).

Usage:
    python scripts/video_from_inspiration.py "<inspiration_url>" [--account <uuid_or_nickname>] [--upload] [--no-render]

Flags:
    --account     Account UUID or nickname (default: first account in .mp/youtube.json).
    --upload      Run upload_video() after generation (off by default).
    --no-render   Stop after printing the brief — skip video generation. Useful for
                  iterating on the brief without burning a 15-min render.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))

from cache import get_accounts
from classes.Tts import TTS
from classes.YouTube import YouTube
from config import get_long_video_llm_model
from llm_provider import force_provider, generate_text, warmup_ollama_model
from status import info, success, error, warning


# ---------- Step 1: scrape the inspiration page ----------

def scrape_inspiration(url: str) -> dict:
    """Open the URL in Firefox with the configured profile, wait for SPA
    hydration, and return the rendered body text + screenshot path."""
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.firefox.service import Service
    from webdriver_manager.firefox import GeckoDriverManager

    cfg = json.load(open(os.path.join(ROOT_DIR, "config.json")))
    src_profile = cfg["firefox_profile"]
    if not os.path.isdir(src_profile):
        raise SystemExit(f"firefox_profile not found: {src_profile}")

    out_dir = os.path.join(ROOT_DIR, ".mp")
    os.makedirs(out_dir, exist_ok=True)
    shot_path = os.path.join(out_dir, "inspiration.png")
    text_path = os.path.join(out_dir, "inspiration.txt")

    tmp = tempfile.mkdtemp(prefix="mpv2_peek_")
    profile = os.path.join(tmp, "profile")
    info(f" => Copying Firefox profile -> {profile}")
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

    info(" => Launching Firefox...")
    service = Service(GeckoDriverManager().install())
    driver = webdriver.Firefox(service=service, options=opts)
    try:
        driver.set_window_size(1600, 2000)
        info(f" => Navigating: {url}")
        driver.get(url)

        # Click any "Mostrar más" / "Show more" buttons to expand collapsed
        # outline sections, so the brief has all subtopics, not just the first.
        # Poll body text length until it stabilizes.
        last = -1
        for i in range(30):
            time.sleep(2)
            try:
                length = driver.execute_script("return (document.body && document.body.innerText) ? document.body.innerText.length : 0")
            except Exception:
                length = 0
            if length is None:
                length = 0
            if length > 200 and length == last:
                break
            last = length

        # Try to expand each "Mostrar más" button so collapsed outlines become visible.
        try:
            driver.execute_script("""
                const labels = ['Mostrar más', 'Show more', 'Ver más'];
                document.querySelectorAll('button, tp-yt-paper-button, ytcp-button').forEach(b => {
                    const t = (b.innerText || '').trim();
                    if (labels.some(l => t.startsWith(l))) {
                        try { b.click(); } catch(e) {}
                    }
                });
            """)
            time.sleep(3)
        except Exception:
            pass

        text = driver.execute_script("return document.body.innerText") or ""
        info(f" => Saving screenshot -> {shot_path}")
        driver.save_screenshot(shot_path)
        info(f" => Saving body text ({len(text)} chars) -> {text_path}")
        open(text_path, "w", encoding="utf-8").write(text)
        return {"text": text, "screenshot": shot_path}

    finally:
        try:
            driver.quit()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)


# ---------- Step 2: parse the page text into structured fields ----------

# YouTube Studio chrome can be in Spanish or English depending on the
# user's locale. Match both.
SECTION_MARKERS = {
    "hook":     ("Contenido atractivo", "Engaging content"),
    "outline":  ("Esquema", "Outline"),
    "titles":   ("Títulos", "Titles"),
    "thumbs":   ("Miniaturas", "Thumbnails"),
    "related":  ("Videos relacionados en YouTube", "Related videos on YouTube"),
}
BACK_MARKERS = ("Atrás", "Back")
NOISE_LINES = {"Mostrar más", "Show more", "Ver más", "Guardar", "Save", "Atrás", "Back"}


def _find_first_index(lines: list[str], markers: tuple[str, ...]) -> int:
    for i, ln in enumerate(lines):
        if any(ln.strip().startswith(m) for m in markers):
            return i
    return -1


def parse_inspiration(text: str) -> dict:
    """Extract title, description, hook, outline, and suggested titles from
    the rendered page text. Robust to chrome being in Spanish or English."""
    lines = [ln for ln in (l.strip() for l in text.splitlines()) if ln]

    back_idx = _find_first_index(lines, BACK_MARKERS)
    hook_idx = _find_first_index(lines, SECTION_MARKERS["hook"])
    outline_idx = _find_first_index(lines, SECTION_MARKERS["outline"])
    thumbs_idx = _find_first_index(lines, SECTION_MARKERS["thumbs"])
    titles_idx = _find_first_index(lines, SECTION_MARKERS["titles"])
    related_idx = _find_first_index(lines, SECTION_MARKERS["related"])

    # Title is the first line after "Atrás" / "Back".
    title = ""
    description = ""
    if back_idx >= 0 and back_idx + 1 < len(lines):
        title = lines[back_idx + 1]
        # Description = lines between title and the first known section.
        end = min(x for x in [hook_idx, outline_idx, titles_idx, len(lines)] if x > 0)
        desc_lines = lines[back_idx + 2 : end]
        description = " ".join(l for l in desc_lines if l not in NOISE_LINES)

    def slice_section(start: int, *ends: int) -> list[str]:
        if start < 0:
            return []
        end_candidates = [e for e in ends if e > start]
        end = min(end_candidates) if end_candidates else len(lines)
        return [l for l in lines[start + 1 : end] if l not in NOISE_LINES]

    hook = slice_section(hook_idx, outline_idx, thumbs_idx, titles_idx, related_idx)
    outline = slice_section(outline_idx, thumbs_idx, titles_idx, related_idx)
    titles = slice_section(titles_idx, related_idx, thumbs_idx) if titles_idx > 0 else []

    return {
        "title": title,
        "description": description,
        "hook": "\n".join(hook),
        "outline": "\n".join(outline),
        "titles": titles,
    }


# ---------- Step 3: convert the parsed inspiration to a Spanish brief ----------

BRIEF_PROMPT = """Eres un editor de contenido. Recibes una idea de video sugerida por YouTube Studio (en inglés) y debes convertirla en un BRIEF en español que sirva como `custom_topic` para un guion documental de 15-20 minutos.

REGLAS:
- Idioma de salida: ESPAÑOL NEUTRAL.
- Densidad: ~250-400 palabras. Sin relleno.
- Estructura del brief (en este orden, sin encabezados markdown):
  1. Una oración con el tema central y el ángulo narrativo.
  2. Una bajada de 2-3 oraciones explicando el conflicto/tensión central.
  3. Una lista numerada de 6-8 subtemas concretos a cubrir, con datos específicos (nombres de misiones, empresas, tratados, fechas) — investiga conocimiento general; no inventes cifras dudosas.
  4. Una línea final con TONO sugerido (ej. "investigativo, escéptico, audiencia adulta").
- NO incluyas comillas envolventes, ni JSON, ni meta-comentarios. Solo el brief.
- NO traduzcas literalmente: adapta. Conserva nombres propios y términos técnicos (LCROSS, Outer Space Treaty, etc.).

INSPIRACIÓN ORIGINAL:

Título sugerido: {title}

Descripción: {description}

Hook narrativo: {hook}

Esquema (parcial): {outline}

Títulos alternativos sugeridos:
{titles}

Devuelve SOLO el brief en español."""


def build_spanish_brief(parsed: dict) -> str:
    titles_block = "\n".join(f"- {t}" for t in parsed.get("titles", [])) or "(ninguno)"
    prompt = BRIEF_PROMPT.format(
        title=parsed.get("title") or "(sin título)",
        description=parsed.get("description") or "(sin descripción)",
        hook=parsed.get("hook") or "(sin hook)",
        outline=parsed.get("outline") or "(sin esquema)",
        titles=titles_block,
    )

    long_model = get_long_video_llm_model()
    info(f" => Generating Spanish brief with ollama/{long_model} (think=high)...")
    warmup_ollama_model(long_model)
    with force_provider("ollama", long_model, think="high"):
        brief = generate_text(prompt)
    return brief.strip()


# ---------- Step 4: pick the YouTube account ----------

def pick_account(account_arg: str | None) -> dict:
    accounts = get_accounts("youtube")
    if not accounts:
        raise SystemExit("No YouTube accounts in .mp/youtube.json — add one via main.py first.")
    if account_arg:
        for acc in accounts:
            if acc["id"] == account_arg or acc.get("nickname") == account_arg:
                return acc
        raise SystemExit(f"Account '{account_arg}' not found. Available: {[a.get('nickname') for a in accounts]}")
    return accounts[0]


# ---------- Main ----------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="YouTube Studio inspiration playground URL")
    parser.add_argument("--account", help="Account UUID or nickname")
    parser.add_argument("--upload", action="store_true", help="Upload after generation")
    parser.add_argument("--no-render", action="store_true", help="Stop after printing the brief")
    args = parser.parse_args()

    info("=" * 60)
    info("[1/4] Scraping inspiration page...")
    info("=" * 60)
    page = scrape_inspiration(args.url)

    info("=" * 60)
    info("[2/4] Parsing page text...")
    info("=" * 60)
    parsed = parse_inspiration(page["text"])
    info(f"  Title:       {parsed['title'] or '(none)'}")
    info(f"  Description: {parsed['description'][:120]}{'...' if len(parsed['description']) > 120 else ''}")
    info(f"  Hook lines:  {len(parsed['hook'].splitlines())}")
    info(f"  Outline lines: {len(parsed['outline'].splitlines())}")
    info(f"  Titles:      {len(parsed['titles'])}")
    if not parsed["title"]:
        warning("Could not detect a title — page parser may be out of date. See .mp/inspiration.txt")

    info("=" * 60)
    info("[3/4] Building Spanish brief via DeepSeek V4 Pro Cloud...")
    info("=" * 60)
    brief = build_spanish_brief(parsed)
    print()
    print("------- BRIEF (custom_topic) -------")
    print(brief)
    print("------------------------------------")
    print()

    brief_path = os.path.join(ROOT_DIR, ".mp", "inspiration_brief.txt")
    open(brief_path, "w", encoding="utf-8").write(brief)
    info(f" => Brief saved to {brief_path}")

    if args.no_render:
        success("Stopping before render (--no-render).")
        return

    info("=" * 60)
    info("[4/4] Generating long video...")
    info("=" * 60)
    acc = pick_account(args.account)
    info(f"  Account: {acc.get('nickname')} ({acc['id']})  language={acc.get('language')}  niche={acc.get('niche')}")

    tts = TTS()
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

    video_path = youtube.generate_long_video(tts, custom_topic=brief)
    if not video_path:
        error("Long-video pipeline aborted (returned empty path).")
        sys.exit(1)
    success(f"Long video rendered: {video_path}")

    if args.upload:
        info(" => Uploading to YouTube...")
        youtube.upload_video()
        success("Upload complete.")
    else:
        info(" => Skipping upload (pass --upload to publish).")


if __name__ == "__main__":
    main()

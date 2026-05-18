#!/usr/bin/env python3
import json
import os
import shutil
import sys
from typing import Tuple

import requests


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT_DIR, "config.json")


def ok(msg: str) -> None:
    print(f"[OK] {msg}")


def warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def check_url(url: str, timeout: int = 3) -> Tuple[bool, str]:
    try:
        response = requests.get(url, timeout=timeout)
        return True, f"HTTP {response.status_code}"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    if not os.path.exists(CONFIG_PATH):
        fail(f"Missing config file: {CONFIG_PATH}")
        return 1

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    failures = 0

    stt_provider = str(cfg.get("stt_provider", "local_whisper")).lower()
    llm_provider = str(cfg.get("llm_provider", "gemini")).lower()
    openai_use_codex_cli = bool(cfg.get("openai_use_codex_cli", False))
    codex_cli_generate_images = bool(cfg.get("codex_cli_generate_images", True))

    ok(f"stt_provider={stt_provider}")
    ok(f"llm_provider={llm_provider}")

    imagemagick_path = cfg.get("imagemagick_path", "")
    if imagemagick_path and os.path.exists(imagemagick_path):
        ok(f"imagemagick_path exists: {imagemagick_path}")
    else:
        warn(
            "imagemagick_path is not set to a valid executable path. "
            "MoviePy subtitle rendering may fail."
        )

    firefox_profile = cfg.get("firefox_profile", "")
    if firefox_profile:
        if os.path.isdir(firefox_profile):
            ok(f"firefox_profile exists: {firefox_profile}")
        else:
            warn(f"firefox_profile does not exist: {firefox_profile}")
    else:
        warn("firefox_profile is empty. Twitter/YouTube automation requires this.")

    # LLM provider
    if llm_provider in {"ollama", "local_ollama"}:
        base = str(cfg.get("ollama_base_url", "http://127.0.0.1:11434")).rstrip("/")
        reachable, detail = check_url(f"{base}/api/tags")
        if not reachable:
            fail(f"Ollama is not reachable at {base}: {detail}")
            failures += 1
        else:
            ok(f"Ollama reachable at {base}")
            try:
                tags = requests.get(f"{base}/api/tags", timeout=5).json()
                models = [m.get("name") for m in tags.get("models", [])]
                if models:
                    ok(f"Ollama models available: {', '.join(models[:10])}")
                else:
                    warn("No models found on Ollama. Pull a model first (e.g. 'ollama pull llama3.2:3b').")
            except Exception as exc:
                warn(f"Could not validate Ollama model list: {exc}")
    elif llm_provider == "openai" and openai_use_codex_cli:
        codex_cmd = str(cfg.get("codex_cli_command", "codex") or "codex")
        if shutil.which(codex_cmd) or os.path.exists(codex_cmd):
            ok(f"Codex CLI available: {codex_cmd}")
            if codex_cli_generate_images:
                sandbox = str(cfg.get("codex_cli_image_sandbox", "workspace-write") or "")
                if sandbox == "read-only":
                    fail("codex_cli_image_sandbox cannot be read-only when Codex CLI generates images")
                    failures += 1
                else:
                    ok(f"Codex CLI image generation enabled (sandbox={sandbox or 'workspace-write'})")
        else:
            fail(f"Codex CLI command not found: {codex_cmd}")
            failures += 1
    elif llm_provider == "openai":
        if cfg.get("openai_api_key") or os.environ.get("OPENAI_API_KEY"):
            ok("openai_api_key is set")
        else:
            fail("openai_api_key is empty and openai_use_codex_cli is false")
            failures += 1
    elif llm_provider == "gemini":
        if cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY"):
            ok("gemini_api_key is set")
        else:
            fail("gemini_api_key is empty")
            failures += 1

    # Leonardo AI (image generation)
    leonardo_key = cfg.get("leonardo_api_key", "")
    if leonardo_key:
        ok("leonardo_api_key is set")
    else:
        fail("leonardo_api_key is empty")
        failures += 1

    if stt_provider == "local_whisper":
        try:
            import faster_whisper  # noqa: F401

            ok("faster-whisper is installed")
        except Exception as exc:
            fail(f"faster-whisper is not importable: {exc}")
            failures += 1

    if failures:
        print("")
        print(f"Preflight completed with {failures} blocking issue(s).")
        return 1

    print("")
    print("Preflight passed. Local setup looks ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

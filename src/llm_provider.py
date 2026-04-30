import requests
from contextlib import contextmanager

from config import get_ollama_base_url, get_llm_provider, get_pollinations_text_model, get_nanobanana2_api_key, get_gemini_model, get_gemini_models

_selected_model: str | None = None
_llm_provider: str | None = None
_disabled_providers: set = set()
_last_used_provider: str | None = None
_disabled_gemini_models: set = set()
# Ollama "thinking" budget for the current call. Set via `force_provider` —
# the long-video pipeline pins it to "high" so DeepSeek V4 Pro Cloud reasons
# at full depth. None means: don't pass the kwarg at all.
_ollama_think: str | bool | None = None


_ollama_autostart_done: bool = False


def _ensure_ollama_serve() -> None:
    """
    Make sure an `ollama serve` daemon is running before we open a client.
    Idempotent — only spawns once per process. Used as a safety net for any
    code path that didn't go through `warmup_ollama_model` first.
    """
    global _ollama_autostart_done
    if _ollama_autostart_done:
        return
    _ollama_autostart_done = True

    base = get_ollama_base_url().rstrip("/")
    try:
        if requests.get(f"{base}/api/tags", timeout=2).status_code == 200:
            return
    except Exception:
        pass

    import subprocess as _sp
    import sys as _sys
    import time as _time
    import shutil as _shutil

    if not _shutil.which("ollama"):
        print("  [!] `ollama` CLI not found on PATH — cannot auto-start daemon")
        return

    print("  [+] Starting `ollama serve` (auto)")
    try:
        kwargs = dict(
            stdout=_sp.DEVNULL,
            stderr=_sp.DEVNULL,
            stdin=_sp.DEVNULL,
            close_fds=True,
        )
        if _sys.platform == "win32":
            kwargs["creationflags"] = 0x00000008 | 0x00000200
        _sp.Popen(["ollama", "serve"], **kwargs)
    except Exception as e:
        print(f"  [!] failed to launch `ollama serve`: {e}")
        return

    deadline = _time.time() + 30
    while _time.time() < deadline:
        try:
            if requests.get(f"{base}/api/tags", timeout=2).status_code == 200:
                return
        except Exception:
            pass
        _time.sleep(1)


def _ollama_client():
    import ollama
    _ensure_ollama_serve()
    return ollama.Client(host=get_ollama_base_url())


def list_models() -> list[str]:
    provider = _llm_provider or get_llm_provider()

    if provider == "pollinations":
        return _list_pollinations_models()

    response = _ollama_client().list()
    return sorted(m.model for m in response.models)


def _list_pollinations_models() -> list[str]:
    try:
        resp = requests.get("https://text.pollinations.ai/models", timeout=15)
        resp.raise_for_status()
        models_data = resp.json()
        return sorted(m.get("name", m.get("id", "unknown")) for m in models_data if isinstance(m, dict))
    except Exception:
        return ["openai", "openai-large", "openai-reasoning", "qwen-coder", "llama", "mistral", "deepseek", "deepseek-r1", "gemini"]


def select_model(model: str) -> None:
    global _selected_model
    _selected_model = model


def set_llm_provider(provider: str) -> None:
    global _llm_provider
    _llm_provider = provider


def get_active_model() -> str | None:
    return _selected_model


def get_active_provider() -> str:
    """Return the runtime LLM provider (override or configured)."""
    return _llm_provider or get_llm_provider() or "ollama"


def warmup_ollama_model(model: str) -> None:
    """
    Make sure the Ollama daemon is up and the requested model is preloaded
    via `ollama run <model>`. On Windows, the first CLI call also bootstraps
    the desktop app — but it exits before the HTTP server is listening, so
    we poll `/api/tags` until reachable before issuing the actual warmup.
    For cloud models (`:cloud` suffix) the warmup also forces the auth
    handshake. Failures are logged, never raised.
    """
    import subprocess
    import time

    base = get_ollama_base_url().rstrip("/")
    tags_url = f"{base}/api/tags"

    def _server_up() -> bool:
        try:
            return requests.get(tags_url, timeout=3).status_code == 200
        except Exception:
            return False

    # Step 1: if the server is down, start `ollama serve` as a detached
    # background process. Using `ollama run X hi` to bootstrap is unreliable
    # on Windows — it spawns a transient daemon that dies when the run exits,
    # leaving subsequent HTTP calls with no server to talk to.
    if not _server_up():
        print(f"  [+] Bootstrapping Ollama daemon (ollama serve)")
        import sys as _sys
        try:
            popen_kwargs = dict(
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
            if _sys.platform == "win32":
                # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP — survives this
                # Python process so the daemon stays up across runs.
                popen_kwargs["creationflags"] = 0x00000008 | 0x00000200
            subprocess.Popen(["ollama", "serve"], **popen_kwargs)
        except FileNotFoundError:
            print(f"  [!] `ollama` CLI not found on PATH — skipping warmup for {model}")
            return
        except Exception as e:
            print(f"  [!] failed to launch `ollama serve`: {e}")

        deadline = time.time() + 60
        while time.time() < deadline:
            if _server_up():
                print(f"  [+] Ollama daemon reachable at {base}")
                break
            time.sleep(1)
        else:
            print(f"  [!] Ollama daemon not reachable at {base} after 60s — skipping warmup")
            return

    # Step 2: server is up — preload the model with a synchronous one-shot.
    print(f"  [+] ollama run {model}")
    try:
        # Read raw bytes and decode manually. `text=True` + `encoding="utf-8"`
        # is unreliable on Windows + Python 3.14: the per-thread reader still
        # falls back to cp1252 and crashes on UTF-8 spinners/auth output that
        # `ollama run` emits. Binary mode bypasses TextIOWrapper entirely.
        result = subprocess.run(
            ["ollama", "run", model, "hi"],
            capture_output=True,
            timeout=180,
        )
        if result.returncode != 0:
            raw = result.stderr or result.stdout or b""
            err = raw.decode("utf-8", errors="replace").strip()
            print(f"  [!] ollama run {model} exited {result.returncode}: {err[:200]}")
    except FileNotFoundError:
        print(f"  [!] `ollama` CLI not found on PATH — skipping warmup for {model}")
    except subprocess.TimeoutExpired:
        print(f"  [!] ollama run {model} timed out during warmup (continuing)")
    except Exception as e:
        print(f"  [!] ollama warmup failed for {model}: {e}")


@contextmanager
def force_provider(provider: str, model: str | None = None, think: str | bool | None = None):
    """
    Temporarily override the active LLM provider (and optionally model + Ollama
    thinking budget) for a specific block of work. Restores prior values on
    exit, even on error. Used by the long-video pipeline to pin generation to
    a specific Ollama Cloud model without affecting Shorts or the user's config.
    """
    global _llm_provider, _selected_model, _ollama_think
    prev_provider, prev_model, prev_think = _llm_provider, _selected_model, _ollama_think
    _llm_provider = provider
    if model is not None:
        _selected_model = model
    if think is not None:
        _ollama_think = think
    try:
        yield
    finally:
        _llm_provider = prev_provider
        _selected_model = prev_model
        _ollama_think = prev_think


_SYSTEM_PROMPT = (
    "You are a content generation assistant. You NEVER engage in conversation. "
    "You NEVER ask questions. You NEVER say 'sure', 'of course', 'here you go', "
    "'let me know', or any pleasantries. You ONLY output exactly what is requested. "
    "No preamble, no explanation, no meta-commentary. Just the raw content. "
    "NEVER include JSON, API metadata, role labels, or any technical artifacts in your output. "
    "When asked to write in a specific language, you MUST write ENTIRELY in that language."
)


def generate_text(prompt: str, model_name: str = None) -> str:
    provider = _llm_provider or get_llm_provider()

    # Build ordered list: primary first, then fallbacks
    if provider == "gemini":
        providers = [
            ("gemini", lambda: _generate_text_gemini(prompt)),
            ("pollinations", lambda: _generate_text_pollinations(prompt, None)),
            ("ollama", lambda: _generate_text_ollama(prompt, None)),
        ]
    elif provider == "pollinations":
        providers = [
            ("pollinations", lambda: _generate_text_pollinations(prompt, model_name)),
            ("gemini", lambda: _generate_text_gemini(prompt)),
            ("ollama", lambda: _generate_text_ollama(prompt, None)),
        ]
    else:
        providers = [
            ("ollama", lambda: _generate_text_ollama(prompt, model_name or _selected_model)),
            ("gemini", lambda: _generate_text_gemini(prompt)),
            ("pollinations", lambda: _generate_text_pollinations(prompt, None)),
        ]

    last_error = None
    for name, fn in providers:
        if name in _disabled_providers:
            continue
        try:
            result = fn()
            if _is_garbage_response(result):
                raise RuntimeError(f"LLM returned a conversational/garbage response: {result[:80]}")
            global _last_used_provider
            if name != _last_used_provider:
                print(f"  [✓] Switched to LLM provider: {name}")
                _last_used_provider = name
            return result
        except Exception as e:
            print(f"  [!] LLM provider '{name}' failed: {e}")
            _disabled_providers.add(name)
            print(f"  [!] Disabling '{name}' for the rest of this session.")
            last_error = e

    raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")


def _is_garbage_response(text: str) -> bool:
    """Detect conversational responses that aren't actual content."""
    if not text or len(text.strip()) < 10:
        return True
    low = text.strip().lower()
    garbage_phrases = [
        "sure thing", "sure!", "of course", "let me know",
        "please provide", "please let me know", "what topic",
        "what would you like", "i'd be happy to", "i'd love to",
        "here's", "here is", "certainly!", "absolutely!",
    ]
    # Check if the response STARTS with a garbage phrase (first 60 chars)
    start = low[:60]
    return any(phrase in start for phrase in garbage_phrases)


def _generate_text_pollinations(prompt: str, model: str = None) -> str:
    import time as _time
    import random as _random

    model = model or get_pollinations_text_model() or "openai"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "seed": _random.randint(1, 999999),
        "cache": False,
    }

    last_error = None
    for attempt in range(3):
        if attempt > 0:
            wait = 10 * attempt
            print(f"[Pollinations] Retry {attempt}/2, waiting {wait}s...")
            _time.sleep(wait)

        # Try POST endpoint first
        try:
            response = requests.post(
                "https://text.pollinations.ai/openai",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last_error = e

        # Fallback to GET endpoint
        try:
            import urllib.parse
            encoded = urllib.parse.quote(prompt[:500])
            seed = _random.randint(1, 999999)
            resp = requests.get(
                f"https://text.pollinations.ai/{encoded}?model={model}&seed={seed}&noCache=true",
                timeout=120,
            )
            resp.raise_for_status()
            return resp.text.strip()
        except Exception as e2:
            last_error = e2

    raise RuntimeError(f"Pollinations text generation failed after 3 attempts: {last_error}")


def _generate_text_ollama(prompt: str, model: str = None) -> str:
    if not model:
        from config import get_ollama_model
        model = get_ollama_model()
    if not model:
        raise RuntimeError("No Ollama model configured")

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    client = _ollama_client()

    # Pass `think` only when the long-video pipeline (or another caller) asked
    # for it. Older ollama-python SDKs reject the kwarg with TypeError — fall
    # back transparently so the call still succeeds without thinking.
    if _ollama_think is not None:
        try:
            response = client.chat(model=model, messages=messages, think=_ollama_think)
        except TypeError:
            response = client.chat(model=model, messages=messages)
    else:
        response = client.chat(model=model, messages=messages)

    content = (response["message"]["content"] or "").strip()

    # Reasoning models (deepseek-v*, etc.) sometimes spend the whole budget on
    # `thinking` and emit empty content. Retry once with thinking disabled so
    # the model is forced to produce a direct answer.
    if not content:
        try:
            response = client.chat(model=model, messages=messages, think=False)
            content = (response["message"]["content"] or "").strip()
        except TypeError:
            pass

    return content


def _generate_text_gemini(prompt: str) -> str:
    """Generate text using Google Gemini API (free tier), cascading through models."""
    api_key = get_nanobanana2_api_key()
    if not api_key:
        raise RuntimeError("No Gemini API key configured (nanobanana2_api_key)")

    models = get_gemini_models()

    payload = {
        "system_instruction": {
            "parts": [{"text": _SYSTEM_PROMPT}]
        },
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.7,
        },
    }

    available_models = [m for m in models if m not in _disabled_gemini_models]
    if not available_models:
        raise RuntimeError("All Gemini models have been rate-limited this session")

    last_error = None
    for model in available_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()

            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError(f"Gemini returned no candidates: {data}")

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise RuntimeError(f"Gemini returned empty parts: {data}")

            text = parts[0].get("text", "").strip()
            if text:
                print(f"  [Gemini] Using model: {model}")
                return text
            raise RuntimeError("Gemini returned empty text")
        except Exception as e:
            print(f"  [Gemini] Model '{model}' failed: {e}")
            # Disable rate-limited models for the session
            if "429" in str(e) or "Too Many Requests" in str(e):
                _disabled_gemini_models.add(model)
                print(f"  [Gemini] Disabling '{model}' (rate limited) for this session.")
            last_error = e

    raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")

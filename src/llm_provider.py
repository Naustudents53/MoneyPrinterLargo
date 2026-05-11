import json as _json
import os as _os
import time as _time
import requests
from contextlib import contextmanager

from config import get_ollama_base_url, get_llm_provider, get_gemini_api_key, get_gemini_model, get_gemini_models


# ---------------------------------------------------------------------------
# Cost logging (writes to <ROOT>/.mp/cost_log.jsonl). Best-effort — the LLM
# call must NEVER fail because we couldn't write a log line.
# ---------------------------------------------------------------------------

_GEMINI_PRICING = {
    "gemini-2.5-flash":      {"in": 0.30, "out": 2.50},
    "gemini-2.5-flash-lite": {"in": 0.075, "out": 0.30},
    "gemini-2.5-pro":        {"in": 1.25, "out": 10.00},
    "gemini-1.5-flash":      {"in": 0.075, "out": 0.30},
    "gemini-1.5-pro":        {"in": 1.25, "out": 5.00},
    "gemini-2.0-flash":      {"in": 0.10, "out": 0.40},
}


def _estimate_gemini_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    p = _GEMINI_PRICING.get(model)
    if not p:
        for k, v in _GEMINI_PRICING.items():
            if model.startswith(k):
                p = v
                break
    if not p:
        return 0.0005
    return (in_tokens / 1_000_000) * p["in"] + (out_tokens / 1_000_000) * p["out"]


def _log_cost(provider: str, model: str, in_tokens: int, out_tokens: int,
              cost_usd: float | None = None) -> None:
    try:
        from config import ROOT_DIR
    except Exception:
        return
    if cost_usd is None and provider == "gemini":
        cost_usd = _estimate_gemini_cost(model, in_tokens, out_tokens)
    entry = {
        "ts": _time.time(),
        "provider": provider,
        "model": model,
        "kind": "text",
        "in_tokens": int(in_tokens),
        "out_tokens": int(out_tokens),
        "cost_usd": round(float(cost_usd or 0.0), 6),
    }
    try:
        mp = _os.path.join(str(ROOT_DIR), ".mp")
        _os.makedirs(mp, exist_ok=True)
        with open(_os.path.join(mp, "cost_log.jsonl"), "a", encoding="utf-8") as f:
            f.write(_json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

_selected_model: str | None = None
_llm_provider: str | None = None
_disabled_providers: set = set()
_last_used_provider: str | None = None
_disabled_gemini_models: set = set()
_disabled_ollama_models: set = set()
# When the user explicitly chose a provider+model from the UI, the long-video
# pipeline must respect that choice and skip its hardcoded force_provider call.
_user_override: bool = False

# Ordered fallback chain for Ollama. Tried in order when no explicit model is
# selected via config (`ollama_model`) or `select_model()`. If every entry
# fails this session, the outer `generate_text` cascade falls through to
# Gemini. Models are disabled per-session on failure to avoid retry storms.
_OLLAMA_FALLBACK_CHAIN: list[str] = [
    "deepseek-v4-pro:cloud",
    "gemma4-31b:cloud",
    "kimi-k2.6:cloud",
    "glm-5.1:cloud",
]
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
    response = _ollama_client().list()
    return sorted(m.model for m in response.models)


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


def set_user_override(value: bool) -> None:
    """Mark the current session as having a user-chosen provider+model.
    When set, the long-video pipeline skips its hardcoded force_provider call
    so the user's choice (e.g. Gemini Flash) is actually respected.
    """
    global _user_override
    _user_override = bool(value)


def is_user_override() -> bool:
    return _user_override


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
        result = subprocess.run(
            ["ollama", "run", model, "hi"],
            capture_output=True,
            timeout=180,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
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

    # When the user explicitly chose a provider from the UI, do NOT cross-
    # fallback to the other one. Pick Gemini → only Gemini; pick Ollama → only
    # Ollama (its internal model cascade still applies). The auto path keeps
    # the historical cross-provider safety net.
    if _user_override:
        if provider == "gemini":
            providers = [("gemini", lambda: _generate_text_gemini(prompt))]
        else:
            providers = [
                ("ollama", lambda: _generate_text_ollama(prompt, model_name or _selected_model)),
            ]
    elif provider == "gemini":
        providers = [
            ("gemini", lambda: _generate_text_gemini(prompt)),
            ("ollama", lambda: _generate_text_ollama(prompt, None)),
        ]
    else:
        providers = [
            ("ollama", lambda: _generate_text_ollama(prompt, model_name or _selected_model)),
            ("gemini", lambda: _generate_text_gemini(prompt)),
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
            # Only disable a provider for the session when the error indicates
            # something that won't fix itself: missing API key, or all of its
            # models exhausted by per-model disabling. A single 503/timeout
            # from one model must NOT poison the whole provider — try the next
            # provider this call, but keep this one available next call so a
            # transient outage doesn't break the rest of the session.
            msg = str(e).lower()
            permanent = (
                "no gemini api key" in msg
                or "all gemini models" in msg
                or "all ollama fallback models" in msg
            )
            if permanent:
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


def _ollama_chat_once(client, model: str, messages: list) -> str:
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


def _generate_text_ollama(prompt: str, model: str = None) -> str:
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    client = _ollama_client()

    # Build the cascade: explicit model (this call's preference) → configured
    # `ollama_model` → hard-coded fallback chain. An explicit model is the
    # *head* of the cascade, not a bypass — so a transient 503 on the caller's
    # preferred model still falls through to the rest of the chain instead of
    # killing the whole Ollama provider for the session.
    from config import get_ollama_model
    configured = get_ollama_model()
    chain: list[str] = []
    if model:
        chain.append(model)
    if configured and configured not in chain:
        chain.append(configured)
    for m in _OLLAMA_FALLBACK_CHAIN:
        if m not in chain:
            chain.append(m)

    candidates = [m for m in chain if m not in _disabled_ollama_models]
    if not candidates:
        raise RuntimeError("All Ollama fallback models have been disabled this session")

    last_error = None
    for candidate in candidates:
        try:
            print(f"  [Ollama] Trying model: {candidate}")
            content = _ollama_chat_once(client, candidate, messages)
            if not content:
                raise RuntimeError("empty response")
            print(f"  [Ollama] Using model: {candidate}")
            return content
        except Exception as e:
            err_msg = str(e).lower()
            print(f"  [Ollama] Model '{candidate}' failed: {e}")
            # Transient server-side errors (5xx, overloaded, timeout, rate
            # limit) — the model is fine, the cloud is just busy. Don't burn
            # it for the session; just move on this call so the next call can
            # retry it. Persistent errors (model not found, auth, "all
            # disabled") earn the per-session ban.
            transient_markers = (
                "503", "504", "overloaded", "timeout", "timed out",
                "temporarily", "rate limit", "429", "try again",
            )
            is_transient = any(t in err_msg for t in transient_markers)
            if not is_transient:
                _disabled_ollama_models.add(candidate)
            last_error = e

    raise RuntimeError(f"All Ollama fallback models failed. Last error: {last_error}")


def _generate_text_gemini(prompt: str) -> str:
    """Generate text using Google Gemini API (free tier), cascading through models."""
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("No Gemini API key configured")

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
                # Best-effort cost tracking — usageMetadata is included in v1beta
                # responses but the field is not guaranteed.
                usage = data.get("usageMetadata") or {}
                _log_cost(
                    "gemini", model,
                    int(usage.get("promptTokenCount") or 0),
                    int(usage.get("candidatesTokenCount") or 0),
                )
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

import json as _json
import os as _os
import time as _time
import requests
from contextlib import contextmanager

from config import (
    get_ollama_base_url,
    get_llm_provider,
    get_gemini_api_key,
    get_gemini_model,
    get_gemini_models,
    get_ollama_models,
)

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


# `_selected_model` may be either a single model name (str) or an ordered
# list of model names that the Ollama provider will try in sequence.
_selected_model: "str | list[str] | None" = None
_llm_provider: str | None = None
_disabled_providers: set = set()
_last_used_provider: str | None = None
_disabled_gemini_models: set = set()
_disabled_ollama_models: set = set()
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


def select_model(model) -> None:
    """Pin the Ollama model (or ordered chain) used by subsequent calls."""
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
def force_provider(provider: str, model=None, think: str | bool | None = None):
    """
    Temporarily override the active LLM provider (and optionally model + Ollama
    thinking budget) for a specific block of work. Restores prior values on
    exit, even on error. Used by the long-video pipeline to pin generation to
    a specific Ollama Cloud model — or an ordered chain of fallback models —
    without affecting Shorts or the user's config.

    ``model`` accepts either a single model name (str) or an ordered list of
    model names. When a list is provided, ``_generate_text_ollama`` will try
    each entry in turn before raising and letting the cross-provider fallback
    fire (e.g. fall through to Gemini).
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


def _resolve_ollama_model_chain(model) -> list[str]:
    """
    Normalize the caller's model argument into an ordered list of model names
    to try. Falls back to the configured ``ollama_models`` chain when no
    explicit model is forced.
    """
    if isinstance(model, list):
        chain = [m for m in model if m]
    elif isinstance(model, str) and model:
        chain = [model]
    else:
        chain = list(get_ollama_models())
    # Drop models we already burned this session, while preserving order.
    return [m for m in chain if m not in _disabled_ollama_models]


def _ollama_chat_once(client, model: str, messages: list[dict]) -> str:
    """
    Single Ollama chat round-trip with the empty-content retry that reasoning
    models occasionally need. Raises on transport errors so the caller can
    cascade to the next model.
    """
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


def _generate_text_ollama(prompt: str, model=None) -> str:
    """
    Run text generation through Ollama with a chained-fallback strategy.
    ``model`` may be a single name, a list, or None (use config default).
    Each model in the chain is tried in order; the first one that returns a
    non-empty, non-garbage response wins. Models that fail the call are added
    to ``_disabled_ollama_models`` so the rest of the session skips them.
    Raises only when every model in the chain has been exhausted.
    """
    chain = _resolve_ollama_model_chain(model)
    if not chain:
        raise RuntimeError("No Ollama model configured")

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    client = _ollama_client()

    last_error: Exception | None = None
    for candidate in chain:
        try:
            content = _ollama_chat_once(client, candidate, messages)
            if not content:
                raise RuntimeError(f"Ollama model '{candidate}' returned empty content")
            if len(chain) > 1:
                print(f"  [Ollama] Using model: {candidate}")
            return content
        except Exception as e:
            print(f"  [Ollama] Model '{candidate}' failed: {e}")
            _disabled_ollama_models.add(candidate)
            print(f"  [Ollama] Disabling '{candidate}' for the rest of this session.")
            last_error = e

    raise RuntimeError(f"All Ollama models failed. Last error: {last_error}")


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

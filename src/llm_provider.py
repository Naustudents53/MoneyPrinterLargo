import json as _json
import os as _os
import time as _time
import requests
from contextlib import contextmanager

from config import (
    ROOT_DIR,
    get_claude_cli_command,
    get_claude_cli_model,
    get_claude_cli_models,
    get_claude_cli_timeout_seconds,
    get_ollama_base_url,
    get_llm_provider,
    get_pollinations_text_model,
    get_codex_cli_command,
    get_codex_cli_model,
    get_codex_cli_sandbox,
    get_codex_cli_timeout_seconds,
    get_gemini_api_key,
    get_gemini_model,
    get_gemini_models,
    get_ollama_models,
    get_openai_api_key,
    get_openai_base_url,
    get_openai_models,
    get_openai_reasoning_effort,
    get_openai_use_codex_cli,
)

# ---------------------------------------------------------------------------
# Cost logging (writes to <ROOT>/.mp/cost_log.jsonl). Best-effort â€” the LLM
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

_OPENAI_PRICING = {
    "gpt-5.5": {"in": 5.00, "out": 30.00},
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


def _estimate_openai_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    p = _OPENAI_PRICING.get(model)
    if not p:
        for k, v in _OPENAI_PRICING.items():
            if model.startswith(k):
                p = v
                break
    if not p:
        return 0.0
    return (in_tokens / 1_000_000) * p["in"] + (out_tokens / 1_000_000) * p["out"]


def _log_cost(provider: str, model: str, in_tokens: int, out_tokens: int,
              cost_usd: float | None = None) -> None:
    try:
        from config import ROOT_DIR
    except Exception:
        return
    if cost_usd is None and provider == "gemini":
        cost_usd = _estimate_gemini_cost(model, in_tokens, out_tokens)
    if cost_usd is None and provider == "openai":
        cost_usd = _estimate_openai_cost(model, in_tokens, out_tokens)
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
_disabled_openai_models: set = set()
_disabled_claude_models: set = set()
# Live availability cache for Claude CLI models (see probe_claude_cli_models).
_claude_probe_cache: dict = {}
_claude_probe_cache_at: float = 0.0
CLAUDE_PROBE_TTL_SECONDS = 600
CLAUDE_PROBE_TIMEOUT_SECONDS = 20
# When the user explicitly chose a provider+model from the UI, the long-video
# pipeline must respect that choice and skip its hardcoded force_provider call.
_user_override: bool = False

# Ordered fallback chain for Ollama. Tried in order when no explicit model is
# selected via config (`ollama_model`) or `select_model()`. If every entry
# fails this session, the outer `generate_text` cascade falls through to
# Gemini. Models are disabled per-session on failure to avoid retry storms.
_OLLAMA_FALLBACK_CHAIN: list[str] = [
    "deepseek-v4-pro:cloud",
    "gemma4:31b-cloud",
    "kimi-k2.6:cloud",
    "glm-5.1:cloud",
]

# Curated catalog shown by the interactive selector even when the model
# isn't installed locally yet. The user can pick any of these â€” Ollama
# auto-pulls on first run (see `warmup_ollama_model`). Cloud entries
# (suffixed `:cloud`) require an Ollama Cloud account but no disk space.
# Each entry is (model_id, short_label) â€” keep the label under ~55 chars
# so the menu reads cleanly in a normal terminal.
#
# Ranking sources (verified May 2026):
#   - LMArena open-weights leaderboard
#   - GPQA Diamond, MMLU, IFEval, MATH-500
#   - SWE-bench Verified, HumanEval, LiveCodeBench
#   - Official cloud catalog: https://ollama.com/search?c=cloud
RECOMMENDED_OLLAMA_MODELS: list[tuple[str, str]] = [
    # --- Cloud â€” frontier (paid usage, zero disk) ---
    ("kimi-k2.6:cloud",           "Moonshot Kimi K2.6 â€” #1 open-weights (GPQA 90.5)"),
    ("deepseek-v4-pro:cloud",     "DeepSeek V4 Pro â€” 1M ctx, 3 reasoning modes"),
    ("glm-4.7:cloud",             "Z.ai GLM 4.7 â€” 94.2 HumanEval, practical king"),
    ("glm-5.1:cloud",             "Z.ai GLM 5.1 â€” newest, top agentic coding"),
    ("minimax-m2.5:cloud",        "MiniMax M2.5 â€” SWE-bench leader (80.2)"),
    ("minimax-m2.7:cloud",        "MiniMax M2.7 â€” coding + agentic workflows"),
    ("gemma4:cloud",              "Google Gemma 4 â€” frontier multilingual"),
    ("qwen3.5:cloud",             "Qwen 3.5 â€” multimodal, strong Spanish"),
    ("deepseek-v4-flash:cloud",   "DeepSeek V4 Flash â€” fast MoE, 1M ctx"),
    ("nemotron-3-super:cloud",    "NVIDIA Nemotron 3 Super 120B MoE"),
    # --- Local â€” large (48GB+ RAM / 24GB+ VRAM) ---
    ("qwen3:235b",                "Alibaba Qwen 3 235B MoE â€” frontier local"),
    ("gpt-oss:120b",              "OpenAI gpt-oss 120B â€” top local reasoning"),
    ("llama3.3:70b",              "Meta Llama 3.3 70B â€” flagship dense"),
    ("deepseek-r1:70b",           "DeepSeek R1 70B â€” local reasoning"),
    # --- Local â€” medium (16-24GB RAM) ---
    ("gemma3:27b",                "Google Gemma 3 27B â€” multilingual practical"),
    ("qwen3:32b",                 "Qwen 3 32B â€” balanced quality / speed"),
    ("qwen2.5-coder:32b",         "Qwen2.5 Coder 32B â€” top local code / JSON"),
    # --- Local â€” small / fast (4-8GB VRAM or CPU) ---
    ("phi4:14b",                  "Microsoft Phi-4 14B â€” reasoning per-param king"),
]


# Curated Gemini text-generation models, ranked by current benchmarks
# (May 2026). Image / TTS / video / embedding / robotics variants are
# excluded â€” only models suitable for the documentary text-gen pipeline.
#
# Sources (verified May 2026):
#   - Official model list: https://ai.google.dev/gemini-api/docs/models
#   - LMArena (Gemini 3 Pro tops with 1501 Elo)
#   - ARC-AGI-2 (Gemini 3.1 Pro: 77.1%)
#   - GPQA Diamond / SWE-bench (Gemini 3 Flash: 90.4% / 78%)
RECOMMENDED_GEMINI_MODELS: list[tuple[str, str]] = [
    ("gemini-3-pro-preview",         "Gemini 3 Pro Preview â€” highest quality"),
    ("gemini-3-flash-preview",       "Gemini 3 Flash Preview â€” frontier fast"),
    ("gemini-2.5-pro",               "Gemini 2.5 Pro â€” stable high quality"),
    ("gemini-2.5-flash",             "Gemini 2.5 Flash â€” stable fast"),
    ("gemini-2.5-flash-lite",        "Gemini 2.5 Flash-Lite â€” fastest budget"),
    ("gemini-2.0-flash",             "Gemini 2.0 Flash â€” legacy compatibility"),
    ("gemma-4-31b-it",               "Gemma 4 31B IT â€” open model via Gemini API"),
    ("gemma-4-26b-a4b-it",           "Gemma 4 26B A4B IT â€” open model via Gemini API"),
]

_GEMINI_MODEL_ALIASES = {
    # Old / UI-only labels that are not valid Gemini API model resource names.
    "gemma-4-31b": "gemma-4-31b-it",
    "gemma-4-26b": "gemma-4-26b-a4b-it",
    # Common confusion with Ollama Cloud tags.
    "gemma4:31b-cloud": "gemma-4-31b-it",
    "gemma4-31b:cloud": "gemma-4-31b-it",
    "gemma4:26b-cloud": "gemma-4-26b-a4b-it",
    "gemma4-26b:cloud": "gemma-4-26b-a4b-it",
}


def normalize_gemini_model_id(model: str | None) -> str | None:
    """Return a Gemini API model id, translating legacy UI aliases."""
    if not model:
        return model
    cleaned = str(model).strip()
    return _GEMINI_MODEL_ALIASES.get(cleaned.lower(), cleaned)
# Ollama "thinking" budget for the current call. Set via `force_provider` â€”
# the long-video pipeline pins it to "high" so DeepSeek V4 Pro Cloud reasons
# at full depth. None means: don't pass the kwarg at all.
_ollama_think: str | bool | None = None


_ollama_autostart_done: bool = False


def _ensure_ollama_serve() -> None:
    """
    Make sure an `ollama serve` daemon is running before we open a client.
    Idempotent â€” only spawns once per process. Used as a safety net for any
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
        print("  [!] `ollama` CLI not found on PATH â€” cannot auto-start daemon")
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
    if provider == "openai":
        return get_openai_models()
    if provider == "claude":
        return get_claude_cli_models()
    response = _ollama_client().list()
    return sorted(m.model for m in response.models)


def _list_pollinations_models() -> list[str]:
    try:
        resp = requests.get("https://text.pollinations.ai/models", timeout=15)
        resp.raise_for_status()
        models_data = resp.json()
        return sorted(
            m.get("name", m.get("id", "unknown"))
            for m in models_data
            if isinstance(m, dict)
        )
    except Exception:
        return [
            "openai", "openai-large", "openai-reasoning",
            "qwen-coder", "llama", "mistral",
            "deepseek", "deepseek-r1", "gemini",
        ]


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
    the desktop app â€” but it exits before the HTTP server is listening, so
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
    # on Windows â€” it spawns a transient daemon that dies when the run exits,
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
                # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP â€” survives this
                # Python process so the daemon stays up across runs.
                popen_kwargs["creationflags"] = 0x00000008 | 0x00000200
            subprocess.Popen(["ollama", "serve"], **popen_kwargs)
        except FileNotFoundError:
            print(f"  [!] `ollama` CLI not found on PATH â€” skipping warmup for {model}")
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
            print(f"  [!] Ollama daemon not reachable at {base} after 60s â€” skipping warmup")
            return

    # Step 2: server is up â€” preload the model with a synchronous one-shot.
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
        print(f"  [!] `ollama` CLI not found on PATH â€” skipping warmup for {model}")
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
    a specific Ollama Cloud model â€” or an ordered chain of fallback models â€”
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


def generate_text(prompt: str, model_name: str = None, temperature: float = 0.7) -> str:
    provider = (_llm_provider or get_llm_provider() or "").lower()

    # When the user explicitly chose a provider from the UI, do NOT cross-
    # fallback to the other one. Pick Gemini â†’ only Gemini; pick OpenAI â†’ only
    # OpenAI; pick Ollama â†’ only Ollama (its internal model cascade still
    # applies). The auto path keeps the historical cross-provider safety net.
    if _user_override:
        if provider == "gemini":
            # Pin to the model the user explicitly chose; if none, fall back
            # to the configured cascade (mirrors Ollama's behaviour).
            providers = [
                ("gemini", lambda: _generate_text_gemini(
                    prompt,
                    model=model_name or _selected_model or None,
                    temperature=temperature,
                )),
            ]
        elif provider == "claude":
            providers = [("claude", lambda: _generate_text_claude_cli(prompt, model_name or _selected_model))]
        elif provider == "openai":
            providers = [("openai", lambda: _generate_text_openai(prompt, model_name or _selected_model, temperature=temperature))]
        elif provider == "pollinations":
            providers = [("pollinations", lambda: _generate_text_pollinations(prompt, model_name or _selected_model))]
        else:
            providers = [
                ("ollama", lambda: _generate_text_ollama(prompt, model_name or _selected_model)),
            ]
    elif provider == "openai":
        providers = [
            ("openai", lambda: _generate_text_openai(prompt, model_name or _selected_model, temperature=temperature)),
            ("gemini", lambda: _generate_text_gemini(prompt, temperature=temperature)),
            ("ollama", lambda: _generate_text_ollama(prompt, None)),
            ("pollinations", lambda: _generate_text_pollinations(prompt, None)),
        ]
    elif provider == "claude":
        providers = [
            ("claude", lambda: _generate_text_claude_cli(prompt, model_name or _selected_model)),
            ("gemini", lambda: _generate_text_gemini(prompt, temperature=temperature)),
            ("ollama", lambda: _generate_text_ollama(prompt, None)),
            ("pollinations", lambda: _generate_text_pollinations(prompt, None)),
        ]
    elif provider == "gemini":
        providers = [
            ("gemini", lambda: _generate_text_gemini(prompt, temperature=temperature)),
            ("ollama", lambda: _generate_text_ollama(prompt, None)),
            ("pollinations", lambda: _generate_text_pollinations(prompt, None)),
        ]
    elif provider == "pollinations":
        providers = [
            ("pollinations", lambda: _generate_text_pollinations(prompt, model_name)),
            ("gemini", lambda: _generate_text_gemini(prompt, temperature=temperature)),
            ("ollama", lambda: _generate_text_ollama(prompt, None)),
        ]
    else:
        providers = [
            ("ollama", lambda: _generate_text_ollama(prompt, model_name or _selected_model)),
            ("gemini", lambda: _generate_text_gemini(prompt, temperature=temperature)),
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
                print(f"  [ok] Switched to LLM provider: {name}")
                _last_used_provider = name
            return result
        except Exception as e:
            print(f"  [!] LLM provider '{name}' failed: {e}")
            # Only disable a provider for the session when the error indicates
            # something that won't fix itself: missing API key, or all of its
            # models exhausted by per-model disabling. A single 503/timeout
            # from one model must NOT poison the whole provider â€” try the next
            # provider this call, but keep this one available next call so a
            # transient outage doesn't break the rest of the session.
            msg = str(e).lower()
            permanent = (
                "no gemini api key" in msg
                or "no openai api key" in msg
                or "claude cli was not found" in msg
                or "all gemini models" in msg
                or "all openai models" in msg
                or "all claude models" in msg
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


def _extract_openai_text(data: dict) -> str:
    text = data.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    chunks: list[str] = []
    for item in data.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content", []) or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"output_text", "text"} and part.get("text"):
                chunks.append(str(part["text"]))

    if chunks:
        return "\n".join(chunks).strip()

    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""


def _is_openai_reasoning_model(model: str) -> bool:
    m = (model or "").lower()
    return m.startswith("gpt-5") or m.startswith("o")


def _openai_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
        err = payload.get("error") or {}
        if isinstance(err, dict):
            return str(err.get("message") or payload)
        return str(err or payload)
    except Exception:
        return response.text[:500]


def _build_codex_cli_prompt(prompt: str) -> str:
    return (
        "You are being used as a non-interactive text-generation backend for "
        "MoneyPrinter Largo. Do not inspect files, run commands, edit files, "
        "or explain what you are doing. Return only the final text requested "
        "by the user.\n\n"
        f"Output contract:\n{_SYSTEM_PROMPT}\n\n"
        f"User request:\n{prompt}"
    )


def _generate_text_codex_cli(prompt: str, model: str = None) -> str:
    """Generate text through the locally authenticated Codex CLI account."""
    import subprocess
    import tempfile

    cli = get_codex_cli_command()
    selected_model = (model or get_codex_cli_model() or "").strip()
    sandbox = get_codex_cli_sandbox()
    timeout = get_codex_cli_timeout_seconds()
    effort = get_openai_reasoning_effort().lower()

    fd, output_path = tempfile.mkstemp(prefix="mp_codex_", suffix=".txt")
    _os.close(fd)

    args = [
        cli,
        "-c",
        f'model_reasoning_effort="{effort}"',
        "--ask-for-approval",
        "never",
        "exec",
        "--cd",
        str(ROOT_DIR),
        "--sandbox",
        sandbox,
        "--color",
        "never",
        "--ephemeral",
        "--output-last-message",
        output_path,
    ]
    if selected_model:
        args += ["--model", selected_model]
    args.append("-")

    try:
        result = subprocess.run(
            args,
            input=_build_codex_cli_prompt(prompt),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

        text = ""
        try:
            with open(output_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read().strip()
        except FileNotFoundError:
            pass

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"codex exec exited {result.returncode}: {detail[-1000:]}")

        if not text:
            text = (result.stdout or "").strip()
        if not text:
            raise RuntimeError("codex exec returned empty text")

        model_label = selected_model or "codex-default"
        print(f"  [Codex CLI] Using model: {model_label} (thinking={effort})")
        return text
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Codex CLI was not found on PATH. Install/login with `codex login` "
            "or set MP_CODEX_CLI_COMMAND."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"codex exec timed out after {timeout}s") from exc
    finally:
        try:
            _os.remove(output_path)
        except OSError:
            pass


def _probe_claude_cli_model(cli: str, model: str, timeout: int) -> bool:
    """Quick liveness check: can this Claude CLI account use `model`?

    Skips the heavy system prompt used by `_generate_text_claude_cli` — a
    one-word probe is enough to know whether the model id/alias is accepted.
    """
    import subprocess

    args = [
        cli, "--print", "--output-format", "text",
        "--no-session-persistence", "--permission-mode", "dontAsk",
        "--tools", "",
    ]
    if model:
        args += ["--model", model]
    args.append("-")

    try:
        result = subprocess.run(
            args,
            input="ping",
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return result.returncode == 0
    except Exception:
        return False


def probe_claude_cli_models(candidates: list[str], force: bool = False) -> dict[str, bool] | None:
    """Live-check which Claude CLI model ids/aliases this account can use.

    Runs a minimal `claude --print --model <id>` call per candidate in
    parallel and caches the result for `CLAUDE_PROBE_TTL_SECONDS` so the
    model selector can refresh on every load without re-spawning the CLI for
    each request. Returns None (instead of all-False) when the CLI itself
    seems unreachable, so callers don't mark every model "unavailable" due to
    an environment problem rather than account permissions.
    """
    import time as _time
    from concurrent.futures import ThreadPoolExecutor

    global _claude_probe_cache, _claude_probe_cache_at

    now = _time.time()
    if (
        not force
        and _claude_probe_cache
        and (now - _claude_probe_cache_at) < CLAUDE_PROBE_TTL_SECONDS
        and all(c in _claude_probe_cache for c in candidates)
    ):
        return {c: _claude_probe_cache[c] for c in candidates}

    cli = get_claude_cli_command()
    timeout = min(CLAUDE_PROBE_TIMEOUT_SECONDS, get_claude_cli_timeout_seconds())

    results: dict[str, bool] = {}
    try:
        with ThreadPoolExecutor(max_workers=max(1, len(candidates))) as pool:
            futures = {
                pool.submit(_probe_claude_cli_model, cli, candidate, timeout): candidate
                for candidate in candidates
            }
            for future, candidate in futures.items():
                results[candidate] = future.result()
    except Exception:
        return None

    if not any(results.values()):
        return None

    _claude_probe_cache = results
    _claude_probe_cache_at = now
    return dict(results)


def _build_claude_cli_prompt(prompt: str) -> str:
    return (
        "You are being used as a non-interactive text-generation backend for "
        "MoneyPrinter Largo. Do not inspect files, run commands, edit files, "
        "or explain what you are doing. Return only the final text requested "
        "by the user.\n\n"
        f"Output contract:\n{_SYSTEM_PROMPT}\n\n"
        f"User request:\n{prompt}"
    )


def _generate_text_claude_cli(prompt: str, model: str = None) -> str:
    """Generate text through the locally authenticated Claude CLI account."""
    import subprocess

    explicit = (model or "").strip()
    chain = []
    if explicit:
        chain.append(explicit)
    for item in get_claude_cli_models():
        if item and item not in chain:
            chain.append(item)
    if not chain:
        chain = [get_claude_cli_model()]
    candidates = [m for m in chain if m not in _disabled_claude_models]
    if not candidates:
        raise RuntimeError("All Claude models have been disabled this session")

    cli = get_claude_cli_command()
    timeout = get_claude_cli_timeout_seconds()
    last_error = None
    for candidate in candidates:
        args = [
            cli,
            "--print",
            "--output-format",
            "text",
            "--no-session-persistence",
            "--permission-mode",
            "dontAsk",
            "--tools",
            "",
            "--system-prompt",
            _SYSTEM_PROMPT,
        ]
        if candidate:
            args += ["--model", candidate]

        try:
            result = subprocess.run(
                args,
                input=_build_claude_cli_prompt(prompt),
                cwd=str(ROOT_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            text = (result.stdout or "").strip()
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "").strip()
                raise RuntimeError(f"claude --print exited {result.returncode}: {detail[-1000:]}")
            if not text:
                raise RuntimeError("claude --print returned empty text")
            print(f"  [Claude CLI] Using model: {candidate or 'claude-default'}")
            _log_cost("claude", candidate or "claude-default", 0, 0, 0.0)
            return text
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Claude CLI was not found on PATH. Install/login with `claude auth` "
                "or set MP_CLAUDE_CLI_COMMAND."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            last_error = RuntimeError(f"claude --print timed out after {timeout}s")
            continue
        except Exception as exc:
            print(f"  [Claude CLI] Model '{candidate}' failed: {exc}")
            msg = str(exc).lower()
            if any(marker in msg for marker in ("model", "not found", "unknown", "permission", "auth")):
                _disabled_claude_models.add(candidate)
            last_error = exc

    raise RuntimeError(f"All Claude models failed. Last error: {last_error}")


def _generate_text_openai(prompt: str, model: str = None, temperature: float = 0.7) -> str:
    """Generate text using the OpenAI Responses API, cascading through models."""
    if get_openai_use_codex_cli():
        return _generate_text_codex_cli(prompt, model=model)

    api_key = get_openai_api_key()
    if not api_key:
        raise RuntimeError("No OpenAI API key configured")

    chain: list[str] = []
    if model:
        chain.append(model)
    for m in get_openai_models():
        if m not in chain:
            chain.append(m)

    candidates = [m for m in chain if m not in _disabled_openai_models]
    if not candidates:
        raise RuntimeError("All OpenAI models have been disabled this session")

    effort = get_openai_reasoning_effort().lower()
    if effort not in {"none", "low", "medium", "high", "xhigh"}:
        effort = "medium"

    url = f"{get_openai_base_url().rstrip('/')}/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error = None
    for candidate in candidates:
        payload = {
            "model": candidate,
            "instructions": _SYSTEM_PROMPT,
            "input": prompt,
            "store": False,
        }
        if _is_openai_reasoning_model(candidate):
            payload["reasoning"] = {"effort": effort}
        else:
            payload["temperature"] = temperature

        try:
            print(f"  [OpenAI] Trying model: {candidate}")
            response = requests.post(url, headers=headers, json=payload, timeout=180)
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code}: {_openai_error_message(response)}")

            data = response.json()
            text = _extract_openai_text(data)
            if not text:
                raise RuntimeError(f"OpenAI returned empty text: {data}")

            usage = data.get("usage") or {}
            _log_cost(
                "openai", candidate,
                int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
                int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
            )
            print(f"  [OpenAI] Using model: {candidate}")
            return text
        except Exception as e:
            err_msg = str(e).lower()
            print(f"  [OpenAI] Model '{candidate}' failed: {e}")
            model_error_markers = (
                "model", "not found", "does not exist", "unsupported",
                "not available", "permission",
            )
            transient_markers = (
                "429", "rate limit", "timeout", "timed out", "temporarily",
                "503", "504", "overloaded",
            )
            if (
                any(t in err_msg for t in model_error_markers)
                and not any(t in err_msg for t in transient_markers)
            ):
                _disabled_openai_models.add(candidate)
            last_error = e

    raise RuntimeError(f"All OpenAI models failed. Last error: {last_error}")


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
    started = _time.time()
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

    def _stat(key):
        try:
            v = response.get(key) if hasattr(response, "get") else getattr(response, key, 0)
        except Exception:
            v = 0
        return int(v or 0)

    prompt_tok = _stat("prompt_eval_count")
    out_tok = _stat("eval_count")
    elapsed = _time.time() - started
    return content, prompt_tok, out_tok, elapsed


def _generate_text_ollama(prompt: str, model=None) -> str:
    """Generate text with Ollama, trying the configured model chain in order."""
    chain = _resolve_ollama_model_chain(model)
    if not chain:
        raise RuntimeError("No Ollama model configured")

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    client = _ollama_client()

    last_error: Exception | None = None
    for idx, candidate in enumerate(chain):
        try:
            if idx > 0:
                print(f"  [Ollama] Falling back to {candidate}")
            content, in_tok, out_tok, elapsed = _ollama_chat_once(client, candidate, messages)
            if not content:
                raise RuntimeError("empty response")
            chars = len(content)
            words = len(content.split())
            tok_part = f"{in_tok}->{out_tok} tok" if (in_tok or out_tok) else f"~{words} words"
            print(f"  [Ollama] {candidate} - {elapsed:.1f}s - {tok_part} - {chars} chars")
            _log_cost("ollama", candidate, in_tok, out_tok, 0.0)
            return content
        except Exception as e:
            print(f"  [Ollama] Model '{candidate}' failed: {e}")
            transient_markers = (
                "503", "504", "overloaded", "timeout", "timed out",
                "temporarily", "rate limit", "429", "try again",
            )
            if not any(t in str(e).lower() for t in transient_markers):
                _disabled_ollama_models.add(candidate)
            last_error = e

    raise RuntimeError(f"All Ollama models failed. Last error: {last_error}")


def _generate_text_gemini(
    prompt: str,
    model: str | None = None,
    temperature: float = 0.7,
) -> str:
    """Generate text using Google Gemini API, optionally pinned to one model.

    When the user picked a specific Gemini model from the UI (via
    `select_model()` + `set_user_override(True)`), `model` is passed in
    explicitly and we call ONLY that model â€” no fallback cascade through
    `config.json`. Otherwise, fall back to the configured cascade.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("No Gemini API key configured")

    if model:
        models = [normalize_gemini_model_id(model)]
    else:
        models = [normalize_gemini_model_id(m) for m in get_gemini_models()]

    payload = {
        "system_instruction": {
            "parts": [{"text": _SYSTEM_PROMPT}]
        },
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": temperature,
        },
    }

    available_models = [m for m in models if m not in _disabled_gemini_models]
    if not available_models:
        raise RuntimeError("All Gemini models have been rate-limited this session")

    last_error = None
    for idx, model in enumerate(available_models):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            if idx > 0:
                print(f"  [Gemini] Falling back to {model}")
            started = _time.time()
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            elapsed = _time.time() - started

            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError(f"Gemini returned no candidates: {data}")

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise RuntimeError(f"Gemini returned empty parts: {data}")

            text = parts[0].get("text", "").strip()
            if text:
                # Best-effort cost tracking â€” usageMetadata is included in v1beta
                # responses but the field is not guaranteed.
                usage = data.get("usageMetadata") or {}
                in_tok = int(usage.get("promptTokenCount") or 0)
                out_tok = int(usage.get("candidatesTokenCount") or 0)
                _log_cost("gemini", model, in_tok, out_tok)
                chars = len(text)
                tok_part = f"{in_tok}->{out_tok} tok" if (in_tok or out_tok) else f"~{len(text.split())} words"
                print(f"  [Gemini] {model} - {elapsed:.1f}s - {tok_part} - {chars} chars")
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


def _generate_text_pollinations(prompt: str, model: str = None) -> str:
    """Generate text using the free text.pollinations.ai endpoint.

    Tries the OpenAI-compatible POST first, then falls back to the simple
    GET endpoint. Retries up to 3 times with progressive backoff because the
    free tier can rate-limit aggressively.
    """
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

    last_error: Exception | None = None
    for attempt in range(3):
        if attempt > 0:
            wait = 10 * attempt
            print(f"  [Pollinations] Retry {attempt}/2, waiting {wait}s...")
            _time.sleep(wait)

        try:
            response = requests.post(
                "https://text.pollinations.ai/openai",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"].strip()
            if text:
                print(f"  [Pollinations] Using model: {model}")
                return text
            raise RuntimeError("Pollinations returned empty text")
        except Exception as e:
            last_error = e

        try:
            import urllib.parse
            encoded = urllib.parse.quote(prompt[:500])
            seed = _random.randint(1, 999999)
            resp = requests.get(
                f"https://text.pollinations.ai/{encoded}?model={model}&seed={seed}&noCache=true",
                timeout=120,
            )
            resp.raise_for_status()
            text = resp.text.strip()
            if text:
                print(f"  [Pollinations] Using model: {model} (GET fallback)")
                return text
        except Exception as e2:
            last_error = e2

    raise RuntimeError(
        f"Pollinations text generation failed after 3 attempts: {last_error}"
    )

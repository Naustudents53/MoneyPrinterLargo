import requests

from config import get_ollama_base_url, get_llm_provider, get_pollinations_text_model, get_gemini_api_key, get_gemini_model, get_gemini_models

_selected_model: str | None = None
_llm_provider: str | None = None
_disabled_providers: set = set()
_last_used_provider: str | None = None
_disabled_gemini_models: set = set()


def _ollama_client():
    import ollama
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
            ("pollinations", lambda: _generate_text_pollinations(prompt, None)),
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

    response = _ollama_client().chat(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    return response["message"]["content"].strip()


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

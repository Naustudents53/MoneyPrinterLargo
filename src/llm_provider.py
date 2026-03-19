import requests

from config import get_ollama_base_url, get_llm_provider, get_pollinations_text_model

_selected_model: str | None = None
_llm_provider: str | None = None


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


def generate_text(prompt: str, model_name: str = None) -> str:
    provider = _llm_provider or get_llm_provider()
    model = model_name or _selected_model

    if provider == "pollinations":
        return _generate_text_pollinations(prompt, model)

    return _generate_text_ollama(prompt, model)


def _generate_text_pollinations(prompt: str, model: str = None) -> str:
    import time as _time

    model = model or get_pollinations_text_model() or "openai"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    last_error = None
    for attempt in range(5):
        if attempt > 0:
            wait = 10 * attempt
            print(f"[Pollinations] Retry {attempt}/4, waiting {wait}s...")
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
            resp = requests.get(
                f"https://text.pollinations.ai/{encoded}?model={model}",
                timeout=120,
            )
            resp.raise_for_status()
            return resp.text.strip()
        except Exception as e2:
            last_error = e2

    raise RuntimeError(f"Pollinations text generation failed after 5 attempts: {last_error}")


def _generate_text_ollama(prompt: str, model: str = None) -> str:
    if not model:
        raise RuntimeError(
            "No Ollama model selected. Call select_model() first or pass model_name."
        )

    response = _ollama_client().chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )

    return response["message"]["content"].strip()

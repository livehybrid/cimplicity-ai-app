"""Provider-aware model catalogue for the Configuration page's Model dropdown.

The globalConfig `model` field is a UCC singleSelect populated from the
ai_model_choices REST endpoint (bin/ai_model_choices.py). That handler passes
the configured LLM API Endpoint here; this module works out which provider is
behind it, fetches that provider's live model catalogue and shapes it into the
EAI entries UCC expects. It lives in lib/ (like pii_detection_logic) so the
logic is importable and unit-testable without splunk.persistconn on the path.

The LLM API Endpoint setting holds a *chat completions* URL (e.g.
https://openrouter.ai/api/v1/chat/completions). Each provider publishes its
catalogue at a sibling /models endpoint with a slightly different response
shape, hence the per-provider handling below. Anything unrecognised is treated
as OpenAI-compatible (LM Studio, Ollama, Groq, Mistral etc. all serve
GET <base>/models in the OpenAI {"data": [{"id": ...}]} shape).
"""
import re

PROVIDER_OPENROUTER = "openrouter"
PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_GENERIC = "generic"

ANTHROPIC_VERSION = "2023-06-01"

# OpenAI's /v1/models mixes chat models with embeddings, audio and image
# models that make no sense in this dropdown; filter on these id fragments.
_OPENAI_NON_CHAT = (
    "embed", "whisper", "tts", "dall-e", "moderation", "audio",
    "transcribe", "realtime", "davinci", "babbage", "image",
)

# Shown when the live catalogue is unreachable (no key yet, offline, provider
# down) so the dropdown is never empty. Kept short - the catalogue is the real
# source, and createSearchChoice lets any model id be typed regardless.
_FALLBACKS = {
    PROVIDER_OPENROUTER: [
        ("anthropic/claude-sonnet-4.6", "Claude Sonnet 4.6 (recommended)"),
        ("anthropic/claude-haiku-4.5", "Claude Haiku 4.5 (fast/cheap)"),
        ("openai/gpt-4o", "GPT-4o"),
        ("openai/gpt-4o-mini", "GPT-4o mini"),
        ("google/gemini-2.5-flash", "Gemini 2.5 Flash"),
        ("deepseek/deepseek-chat", "DeepSeek Chat"),
    ],
    PROVIDER_OPENAI: [
        ("gpt-4o", "GPT-4o"),
        ("gpt-4o-mini", "GPT-4o mini"),
    ],
    PROVIDER_ANTHROPIC: [
        ("claude-sonnet-5", "Claude Sonnet 5"),
        ("claude-haiku-4-5", "Claude Haiku 4.5"),
        ("claude-opus-5", "Claude Opus 5"),
    ],
}


def detect_provider(api_endpoint):
    """Map the configured chat-completions URL to a known provider."""
    endpoint = (api_endpoint or "").lower()
    if "openrouter.ai" in endpoint:
        return PROVIDER_OPENROUTER
    if "api.openai.com" in endpoint:
        return PROVIDER_OPENAI
    if "api.anthropic.com" in endpoint:
        return PROVIDER_ANTHROPIC
    return PROVIDER_GENERIC


def models_url(api_endpoint):
    """Derive the provider's model-catalogue URL from the completions URL."""
    provider = detect_provider(api_endpoint)
    if provider == PROVIDER_OPENROUTER:
        return "https://openrouter.ai/api/v1/models"
    if provider == PROVIDER_OPENAI:
        return "https://api.openai.com/v1/models"
    if provider == PROVIDER_ANTHROPIC:
        return "https://api.anthropic.com/v1/models"
    base = re.sub(r"/chat/completions/?$", "", (api_endpoint or "").strip())
    base = base.rstrip("/")
    if not base:
        return None
    if base.endswith("/models"):
        return base
    return base + "/models"


def request_headers(provider, api_key):
    """Auth headers for the catalogue request (OpenRouter's is public)."""
    if provider == PROVIDER_ANTHROPIC:
        headers = {"anthropic-version": ANTHROPIC_VERSION}
        if api_key:
            headers["x-api-key"] = api_key
        return headers
    if api_key:
        return {"Authorization": "Bearer %s" % api_key}
    return {}


def parse_models(provider, payload):
    """Normalise a provider catalogue payload to [{"id", "label"}, ...]."""
    items = payload.get("data") or payload.get("models") or []
    models = []
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not model_id:
            continue
        if provider == PROVIDER_OPENAI and any(
            marker in model_id for marker in _OPENAI_NON_CHAT
        ):
            continue
        if provider == PROVIDER_ANTHROPIC:
            label = item.get("display_name") or model_id
        else:
            label = item.get("name") or model_id
        ctx = item.get("context_length") or 0
        if ctx:
            label = "%s (%dk ctx)" % (label, round(ctx / 1000))
        models.append({"id": model_id, "label": label})
    if provider in (PROVIDER_OPENAI, PROVIDER_ANTHROPIC):
        models.sort(key=lambda m: m["id"])
    return models


def fallback_models(provider):
    pairs = _FALLBACKS.get(provider) or _FALLBACKS[PROVIDER_OPENROUTER]
    return [{"id": model_id, "label": label} for model_id, label in pairs]


def eai_entries(models):
    """Shape models into the EAI collection UCC's endpointUrl expects."""
    return [
        {"name": m["id"], "content": {"label": m["label"], "id": m["id"]}}
        for m in models
    ]


def fetch_models(api_endpoint, api_key, timeout=10):
    """Fetch the live catalogue; fall back to the static list on any failure."""
    provider = detect_provider(api_endpoint)
    url = models_url(api_endpoint)
    if not url:
        return fallback_models(provider)
    try:
        import requests

        response = requests.get(
            url, headers=request_headers(provider, api_key), timeout=timeout
        )
        response.raise_for_status()
        models = parse_models(provider, response.json())
        return models or fallback_models(provider)
    except Exception:
        return fallback_models(provider)

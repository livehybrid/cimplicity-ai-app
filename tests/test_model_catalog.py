"""Tests for lib/model_catalog.py (provider detection, parsing, fallbacks).

Pure-logic tests: no network, no splunk.persistconn. fetch_models is covered
only for its no-endpoint fallback path; the live paths are exercised against
real providers by the config page itself.
"""
import model_catalog as mc


class TestDetectProvider:
    def test_openrouter(self):
        assert mc.detect_provider(
            "https://openrouter.ai/api/v1/chat/completions"
        ) == mc.PROVIDER_OPENROUTER

    def test_openai(self):
        assert mc.detect_provider(
            "https://api.openai.com/v1/chat/completions"
        ) == mc.PROVIDER_OPENAI

    def test_anthropic(self):
        assert mc.detect_provider(
            "https://api.anthropic.com/v1/chat/completions"
        ) == mc.PROVIDER_ANTHROPIC

    def test_generic_and_empty(self):
        assert mc.detect_provider(
            "http://lmstudio.local:1234/v1/chat/completions"
        ) == mc.PROVIDER_GENERIC
        assert mc.detect_provider("") == mc.PROVIDER_GENERIC
        assert mc.detect_provider(None) == mc.PROVIDER_GENERIC


class TestModelsUrl:
    def test_known_providers_use_canonical_urls(self):
        assert mc.models_url(
            "https://openrouter.ai/api/v1/chat/completions"
        ) == "https://openrouter.ai/api/v1/models"
        assert mc.models_url(
            "https://api.openai.com/v1/chat/completions"
        ) == "https://api.openai.com/v1/models"
        assert mc.models_url(
            "https://api.anthropic.com/v1/chat/completions"
        ) == "https://api.anthropic.com/v1/models"

    def test_generic_strips_chat_completions_suffix(self):
        assert mc.models_url(
            "http://lmstudio.local:1234/v1/chat/completions"
        ) == "http://lmstudio.local:1234/v1/models"

    def test_generic_bare_base_url(self):
        assert mc.models_url("http://ollama.local:11434/v1/") == \
            "http://ollama.local:11434/v1/models"

    def test_generic_already_models_url(self):
        assert mc.models_url("http://x.local/v1/models") == "http://x.local/v1/models"

    def test_empty_endpoint(self):
        assert mc.models_url("") is None
        assert mc.models_url(None) is None


class TestRequestHeaders:
    def test_anthropic_uses_x_api_key_and_version(self):
        headers = mc.request_headers(mc.PROVIDER_ANTHROPIC, "sk-test")
        assert headers["x-api-key"] == "sk-test"
        assert headers["anthropic-version"] == mc.ANTHROPIC_VERSION

    def test_bearer_for_openai_compatible(self):
        headers = mc.request_headers(mc.PROVIDER_OPENAI, "sk-test")
        assert headers == {"Authorization": "Bearer sk-test"}

    def test_no_key_no_auth_header(self):
        assert mc.request_headers(mc.PROVIDER_OPENROUTER, None) == {}


class TestParseModels:
    def test_openrouter_shape_with_context_length(self):
        payload = {"data": [
            {"id": "anthropic/claude-sonnet-4.6", "name": "Claude Sonnet 4.6",
             "context_length": 200000},
        ]}
        models = mc.parse_models(mc.PROVIDER_OPENROUTER, payload)
        assert models == [{
            "id": "anthropic/claude-sonnet-4.6",
            "label": "Claude Sonnet 4.6 (200k ctx)",
        }]

    def test_openai_filters_non_chat_and_sorts(self):
        payload = {"data": [
            {"id": "gpt-4o-mini"},
            {"id": "text-embedding-3-small"},
            {"id": "whisper-1"},
            {"id": "gpt-4o"},
            {"id": "dall-e-3"},
        ]}
        models = mc.parse_models(mc.PROVIDER_OPENAI, payload)
        assert [m["id"] for m in models] == ["gpt-4o", "gpt-4o-mini"]

    def test_anthropic_display_name(self):
        payload = {"data": [{"id": "claude-sonnet-5", "display_name": "Claude Sonnet 5"}]}
        models = mc.parse_models(mc.PROVIDER_ANTHROPIC, payload)
        assert models == [{"id": "claude-sonnet-5", "label": "Claude Sonnet 5"}]

    def test_ignores_malformed_entries(self):
        payload = {"data": [{"no_id": True}, "not-a-dict", {"id": "ok"}]}
        assert mc.parse_models(mc.PROVIDER_GENERIC, payload) == [
            {"id": "ok", "label": "ok"}
        ]

    def test_empty_payload(self):
        assert mc.parse_models(mc.PROVIDER_GENERIC, {}) == []


class TestFallbacksAndEntries:
    def test_every_provider_has_a_nonempty_fallback(self):
        for provider in (mc.PROVIDER_OPENROUTER, mc.PROVIDER_OPENAI,
                         mc.PROVIDER_ANTHROPIC, mc.PROVIDER_GENERIC):
            assert mc.fallback_models(provider)

    def test_eai_entries_shape(self):
        entries = mc.eai_entries([{"id": "m1", "label": "Model 1"}])
        assert entries == [{"name": "m1", "content": {"label": "Model 1", "id": "m1"}}]

    def test_fetch_models_without_endpoint_returns_fallback(self):
        models = mc.fetch_models("", None)
        assert models == mc.fallback_models(mc.PROVIDER_GENERIC)

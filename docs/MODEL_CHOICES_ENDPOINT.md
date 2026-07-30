# Model Choices Endpoint

`GET /services/cim-plicity/ai_model_choices` (splunkd, also proxied via Splunk Web)

Feeds the Configuration page's **Model** dropdown (`globalConfig.json` field
`model`, a UCC `singleSelect` with `options.endpointUrl`). Returns the live
model catalogue of whichever provider sits behind the configured **LLM API
Endpoint**, shaped as the EAI collection UCC expects:

```json
{
  "entry": [
    { "name": "anthropic/claude-sonnet-4.6",
      "content": { "id": "anthropic/claude-sonnet-4.6", "label": "Claude Sonnet 4.6 (200k ctx)" } }
  ]
}
```

## Provider detection

The field declares `dependencies: ["api_endpoint"]`, so UCC re-fetches this
endpoint with `?api_endpoint=<value>` whenever the LLM API Endpoint changes.
`lib/model_catalog.py` maps the endpoint to a provider:

| Endpoint contains | Catalogue fetched | Auth |
| --- | --- | --- |
| `openrouter.ai` | `https://openrouter.ai/api/v1/models` | none needed (public) |
| `api.openai.com` | `https://api.openai.com/v1/models` | `Authorization: Bearer` (stored API key) |
| `api.anthropic.com` | `https://api.anthropic.com/v1/models` | `x-api-key` + `anthropic-version` |
| anything else | `<base>/models` (chat/completions suffix stripped) | `Authorization: Bearer` if a key is stored |

The "anything else" row makes OpenAI-compatible servers (LM Studio, Ollama,
Groq, Mistral etc.) work without special-casing.

## Behaviour notes

- When no `api_endpoint` query param is supplied, the stored
  `ai_configuration` value is used. The stored (encrypted) API key is read via
  `passSystemAuth` so no list-passwords capability is needed.
- Responses are cached in the persistent process for 5 minutes per endpoint.
- Failures never surface as errors: a static per-provider fallback list is
  returned instead, and `createSearchChoice` on the field means any model ID
  can always be typed manually.
- OpenAI results are filtered to chat-capable models (embeddings, audio,
  image and moderation models are dropped).

Implementation: `ucc-app/bin/ai_model_choices.py` (persistconn handler) +
`ucc-app/lib/model_catalog.py` (pure logic, tested in
`tests/test_model_catalog.py`).

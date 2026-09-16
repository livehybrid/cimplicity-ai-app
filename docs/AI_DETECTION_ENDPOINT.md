# AI Detection Endpoint Documentation

## Overview

The AI Detection endpoint analyses a raw log sample and suggests Splunk field extractions: props.conf-ready PCRE regexes with named capture groups, a suggested sourcetype and timestamp settings. It is implemented as a Splunk persistent REST handler in the `ai_detection.py` script. When an API key is configured it calls the app's configured AI provider (OpenRouter by default, or any OpenAI-compatible endpoint); when no key is set, or the AI call fails, it falls back to a deterministic local regex extractor.

---

## Endpoint Details

- **Script Location:** `ucc-app/bin/ai_detection.py`
- **REST URL (splunkd):** `https://<splunkd>:8089/services/ai_detection` (also `https://<splunkd>:8089/servicesNS/-/cim-plicity/ai_detection`, since the `[script:ai_detection]` stanza in `restmap.conf` declares `match = /ai_detection`)
- **Splunk Web proxy:** the UI calls it via `createRESTURL('/servicesNS/-/cim-plicity/ai_detection')`, exposed through the `[expose:ai_detection]` stanza in `web.conf`
- **Method:** `POST`
- **Handler:** `ai_detection.AiDetection`
- **Authentication:** Requires Splunk session authentication

---

## Request Structure

Callers POST a raw JSON body with `Content-Type: application/json` (splunkd delivers it to the persistent handler as the JSON-encoded `payload` string):

```
{
  "text": "<raw sample event or lines>",
  "description": "<optional context about the data>",
  "selected_fields": ["field_a", "field_b"]
}
```

- `text` (required): the raw log sample to analyse. Returns `400` with `{"error": "No text provided for AI detection"}` if missing.
- `description` (optional): free-text context passed to the AI prompt to improve suggestions.
- `selected_fields` (optional): array of field names. When given, the handler builds a `combined_regex` covering exactly those fields (unselected fields become non-capturing groups) and echoes the list back as `selected_fields`.

### Example Request

```
curl -k -u admin:changeme \
  -H "Content-Type: application/json" \
  -d '{"text": "2024-06-01T12:00:00 INFO user=alice src=10.0.0.1 action=login", "description": "auth events from the SSO gateway"}' \
  https://localhost:8089/services/ai_detection
```

---

## Response Structure

```
{
  "payload": {
    "sourcetype": "custom_log",
    "fields": [
      { "name": "user", "regex": "user=(?<user>[^\\s,]+)" },
      { "name": "src", "regex": "src=(?<src>(?:[0-9]{1,3}\\.){3}[0-9]{1,3})" }
    ],
    "combined_regex": "single regex extracting all fields, or null",
    "time_format": "%Y-%m-%dT%H:%M:%S",
    "time_prefix": "",
    "max_timestamp_lookahead": "25",
    "source": "ai_detection"
  },
  "status": 200
}
```

### Response Fields
- `payload.sourcetype`: Suggested Splunk sourcetype for the sample.
- `payload.fields`: List of `{name, regex}` objects; each regex is a PCRE pattern with a named capture group, suitable for props.conf `EXTRACT-` stanzas. Fields returned without a usable name are auto-named from the regex's named group or as `field_N`.
- `payload.combined_regex`: A single regex extracting all (or the selected) fields in one pass; `null` when the local fallback is used and no `selected_fields` were given.
- `payload.time_format`, `payload.time_prefix`, `payload.max_timestamp_lookahead`: Timestamp settings for props.conf (`TIME_FORMAT`, `TIME_PREFIX`, `MAX_TIMESTAMP_LOOKAHEAD`). `time_format` is `CURRENT_TIME` when no timestamp pattern is recognised.
- `payload.source`: `"ai_detection"` for AI-derived results, `"local_fallback"` for the deterministic extractor.
- `payload.selected_fields`: Echo of the request's `selected_fields` (only present when a combined regex was built from them).
- `status`: 200 on success, 400/500 for errors.

Responses from different AI models are normalised into this shape (e.g. `field_extractions`/`combined_extraction`/`timestamp_analysis` variants are converted) so the contract above holds regardless of the configured model.

### Error Responses
- Malformed request or payload JSON: `{"payload": {"error": "Malformed input, must be valid JSON."}, "status": 400}` (or `"Malformed payload, must be valid JSON."`)
- No session key: `{"payload": {"error": "No session key provided"}, "status": 401}`
- Missing text: `{"payload": {"error": "No text provided for AI detection"}, "status": 400}`
- Unexpected errors: `{"payload": {"error": "Internal error during AI detection"}, "status": 500}`

---

## AI Provider vs Local Fallback

- **Configured provider:** The `api_key`, `api_endpoint` and `model` come from the app's Configuration page (`cim-plicity_settings.conf`, `[ai_configuration]`, key stored in the Splunk credential store). Any OpenAI-compatible chat-completions endpoint works; OpenRouter is the default.
- **Local fallback:** Used when no API key is configured or the AI call fails/times out (60 s timeout). It detects common patterns (timestamp, IP address, log level, email, key=value pairs) and common timestamp formats. Fallback results carry `"source": "local_fallback"`.
- **Logging:** `$SPLUNK_HOME/var/log/splunk/cim-plicity.log`.

---

## Notes & Limitations

- The endpoint is stateless; each request is independent.
- AI-generated regexes are best-effort: always test them against representative samples before deploying to props.conf.
- The sample text (and any description) is sent to the configured LLM service; for privacy-sensitive data use the local fallback or review your provider's policy.
- This endpoint is also exposed as the `ai_detection` MCP tool (see [MCP_TOOLS.md](MCP_TOOLS.md)).

---

## References
- [PII Detection Endpoint](PII_DETECTION_ENDPOINT.md)
- [CIM Mapping Endpoint](CIM_MAPPING_ENDPOINT.md)
- [Splunk REST Handler Documentation](https://dev.splunk.com/enterprise/docs/developapps/customresthandlers/)

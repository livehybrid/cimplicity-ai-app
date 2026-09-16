# MCP Tools

## Overview

CIMPlicity AI exposes its REST endpoints as tools for the Splunk MCP Server, so AI agents can drive the onboarding workflow (field extraction, PII detection, CIM mapping) programmatically. The tool declarations ship in `ucc-app/default/tools.conf`; self-registration for Splunk Enterprise is handled by `ucc-app/bin/autoregister.py`.

Typical agent flow: `cim_plicity_ping` → `ai_detection` (suggest field extractions from a raw sample) → `pii_detection` (scan the sample for PII) → `cim_mapping` (map the extracted fields onto a CIM data model).

## How registration works

Each `[restmap:<tool>]` stanza in `tools.conf` maps an MCP tool to a REST endpoint via `endpoint_name` (the matching `[script:<name>]` stanza in `restmap.conf`). Note the HTTP URL is not `/services/<endpoint_name>`: it is whatever `match =` declares on that `[script:]` stanza; the real URLs are listed per tool below.

Registration is instance-aware:

- **Splunk Cloud** (`server/info` `instance_type` = `cloud`): a native synced-apps registrar registers the tools directly from `default/tools.conf` on install. `autoregister.py` detects this and no-ops.
- **Splunk Enterprise**: older MCP servers have no native registrar or `tool_registration` endpoint, so `autoregister.py` upserts the tools into the Splunk MCP Server's `mcp_tools` and `mcp_tools_enabled` KV collections. The upsert is idempotent (full-document replace by `_key`), and the tool documents (inputSchema + execution body template, which `tools.conf` cannot express) live in the inline `TOOLS` table in `autoregister.py`; keep it in lockstep with `tools.conf`.

The registration fires automatically: CI's "Update app version" step adds `reload.tools = http_post /cim-plicity/autoregister` to `app.conf [triggers]`, so Splunk POSTs the autoregister endpoint on every app-state change (install, enable, upgrade). AppInspect also requires a reload trigger for every shipped custom conf, which this satisfies for `tools.conf`. You can also fire it manually as a one-shot:

```
curl -k -u admin:changeme -X POST https://localhost:8089/services/cim-plicity/autoregister
```

The response reports the detected `instance_type` and the action taken (`kv_upsert` with per-tool statuses on Enterprise, `skipped` on Cloud).

## Tools

All POST tools take a raw JSON body with `Content-Type: application/json` (the handlers json-parse the payload; form-encoding fails). Full request/response contracts are in the linked endpoint docs.

### cim_plicity_ping

Health check. Call first to verify connectivity before other tools.

- **URL:** `GET https://<splunkd>:8089/services/cim-plicity/ping`
- **Payload:** none
- **Response:** `{ "ok": true, "app": "cim-plicity", "tools": ["cim_plicity_ping", "ai_detection", "pii_detection", "cim_mapping"] }`

```
curl -k -u admin:changeme https://localhost:8089/services/cim-plicity/ping
```

### ai_detection

Suggest Splunk field extractions for a raw log sample: props.conf-ready PCRE regexes with named capture groups, a suggested sourcetype and timestamp settings. Uses the app-configured AI provider with a deterministic local regex fallback when no API key is set. See [AI_DETECTION_ENDPOINT.md](AI_DETECTION_ENDPOINT.md).

- **URL:** `POST https://<splunkd>:8089/services/ai_detection`
- **Payload:** `{ text (required), description (optional), selected_fields (optional array of field names) }`
- **Response:** `{ sourcetype, fields: [{name, regex}], combined_regex, time_format, time_prefix, max_timestamp_lookahead, source }`

```
curl -k -u admin:changeme \
  -H "Content-Type: application/json" \
  -d '{"text": "2024-06-01T12:00:00 INFO user=alice src=10.0.0.1 action=login"}' \
  https://localhost:8089/services/ai_detection
```

### pii_detection

Detect PII in a raw log sample using scrubadub detectors (detector set configurable on the Configuration page) plus optional caller-supplied regex patterns. See [PII_DETECTION_ENDPOINT.md](PII_DETECTION_ENDPOINT.md).

- **URL:** `POST https://<splunkd>:8089/services/pii_detection`
- **Payload:** `{ text (required), custom_patterns (optional array of {name, regex}, matched case-insensitively) }`
- **Response:** `{ pii_results: [{type, text, score, start, end, field, examples, regex_pattern}], suggestion }`

```
curl -k -u admin:changeme \
  -H "Content-Type: application/json" \
  -d '{"text": "John Doe'\''s email is john.doe@example.com", "custom_patterns": [{"name": "employee_id", "regex": "\\bEMP\\d{6}\\b"}]}' \
  https://localhost:8089/services/pii_detection
```

### cim_mapping

Map extracted log fields onto a Splunk CIM data model with AI, returning per-field confidence and reasoning. Requires the AI `api_key` to be configured; CIM models are loaded dynamically from `Splunk_SA_CIM` when installed, with a built-in fallback for `authentication`, `network_traffic` and `web`. See [CIM_MAPPING_ENDPOINT.md](CIM_MAPPING_ENDPOINT.md).

- **URL:** `POST https://<splunkd>:8089/services/cim_mapping`
- **Payload:** `{ extractedFields (required array, e.g. [{name, sample}]), cimModel (required lowercase_underscore model key) }`
- **Response:** `[{field, cimField, confidence, reasoning}]` or `{error}`

```
curl -k -u admin:changeme \
  -H "Content-Type: application/json" \
  -d '{"extractedFields": [{"name": "user_ip", "sample": "10.0.0.1"}], "cimModel": "authentication"}' \
  https://localhost:8089/services/cim_mapping
```

## Notes

- All URLs are also reachable app-scoped, e.g. `/servicesNS/-/cim-plicity/ai_detection` (and `/servicesNS/-/cim-plicity/cim-plicity/ping` for the ping tool).
- Browser/Splunk Web access goes via the splunkd proxy and the `[expose:]` stanzas in `web.conf`; MCP calls hit splunkd (`:8089`) directly and do not need `web.conf`.
- `autoregister.py` is pure stdlib plus `splunk.rest`, so it runs on Splunk's default persistent-handler Python and never raises out of a reload trigger.

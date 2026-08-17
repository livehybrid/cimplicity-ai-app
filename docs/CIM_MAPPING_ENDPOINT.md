# CIM Mapping Endpoint Documentation

## Overview

The CIM Mapping endpoint maps a list of extracted log fields onto a Splunk Common Information Model (CIM) data model using AI, returning a confidence score and reasoning per mapping. It is implemented as a Splunk persistent REST handler in the `cim_mapping.py` script. The available CIM models and their fields are loaded dynamically from an installed `Splunk_SA_CIM` app, with a built-in fallback set when the CIM app is absent.

Note: the app's UI currently generates CIM mapping suggestions locally in the browser (fuzzy matching in `CIMMapping.jsx`); this endpoint provides the server-side AI-assisted mapping used by MCP agents and external callers (see [MCP_TOOLS.md](MCP_TOOLS.md)).

---

## Endpoint Details

- **Script Location:** `ucc-app/bin/cim_mapping.py` (model loading in `ucc-app/bin/load_cim_models.py`)
- **REST URL (splunkd):** `https://<splunkd>:8089/services/cim_mapping` (also `https://<splunkd>:8089/servicesNS/-/cim-plicity/cim_mapping`, since the `[script:cim_mapping]` stanza in `restmap.conf` declares `match = /cim_mapping`)
- **Splunk Web proxy:** exposed through the `[expose:cim_mapping]` stanza in `web.conf`
- **Method:** `POST`
- **Handler:** `cim_mapping.CimMappingHandler`
- **Authentication:** Requires Splunk session authentication

---

## Request Structure

Callers POST a raw JSON body with `Content-Type: application/json` (splunkd delivers it to the persistent handler as the JSON-encoded `payload` string):

```
{
  "extractedFields": [
    { "name": "user_ip", "sample": "10.0.0.1" },
    { "name": "username", "sample": "alice" }
  ],
  "cimModel": "authentication"
}
```

- `extractedFields` (required): array of extracted fields. Objects like `{name, sample}` work best: sample values improve mapping quality.
- `cimModel` (required): the CIM model key, lowercase with underscores (e.g. `authentication`, `network_traffic`, `web`). With `Splunk_SA_CIM` installed, every model shipped by the CIM app is available (the key is the model name lowercased with spaces replaced by underscores). Without it, only the built-in fallback models `authentication`, `network_traffic` and `web` are valid; an unknown key returns `{"error": "Invalid CIM model specified: <model>"}`.

### Example Request

```
curl -k -u admin:changeme \
  -H "Content-Type: application/json" \
  -d '{"extractedFields": [{"name": "user_ip", "sample": "10.0.0.1"}, {"name": "username", "sample": "alice"}], "cimModel": "authentication"}' \
  https://localhost:8089/services/cim_mapping
```

---

## Response Structure

On success the payload is a JSON array of mapping suggestions:

```
{
  "payload": [
    {
      "field": "user_ip",
      "cimField": "src_ip",
      "confidence": 0.95,
      "reasoning": "Field name 'user_ip' is a clear synonym for 'src_ip'"
    },
    {
      "field": "username",
      "cimField": "user",
      "confidence": 0.98,
      "reasoning": "Direct match on username semantics"
    }
  ],
  "status": 200
}
```

### Response Fields
- `field`: The original extracted field name.
- `cimField`: The standard CIM field it maps to. Multiple extracted fields may map to the same CIM field.
- `confidence`: Float between 0.0 and 1.0.
- `reasoning`: Brief explanation for the mapping.
- Extracted fields with no clear CIM mapping are omitted from the array.

### Error Responses
- No session key: `{"payload": {"error": "No session key provided"}, "status": 401}`
- Missing parameters: `{"payload": {"error": "Missing required parameters: extractedFields and cimModel"}, "status": 400}`
- AI not configured: `{"payload": {"error": "AI service is not configured."}, "status": 500}`
- Invalid model or AI failure: `{"payload": {"error": "<message>"}, "status": 200}` (errors from the AI call are returned in the payload)

---

## Dynamic CIM Model Loading

`load_cim_models.py` builds the model catalogue lazily on the first request and caches it for the handler process, so a handler recycle picks up a newly installed `Splunk_SA_CIM` without a full splunkd restart:

1. **Locate Splunk_SA_CIM:** Looks for `$SPLUNK_HOME/etc/apps/Splunk_SA_CIM` (case-insensitive fallback scan of the apps directory).
2. **Parse model definitions:** Reads each JSON data-model file under `default/data/models/` (then `local/data/models/`, whose per-file overrides win), collecting every object's extracted fields and calculated/derived output fields (evals, lookups) with their descriptions, de-duplicated per model.
3. **Model keys:** `modelName` (or `displayName`) lowercased with spaces replaced by underscores, e.g. `Network Traffic` becomes `network_traffic`.
4. **Fallback:** If the CIM app is missing or no models parse, a hardcoded set covering `authentication`, `network_traffic` and `web` is used so the endpoint still works on installations without `Splunk_SA_CIM`.

The loaded field list (name + description) for the requested model is given to the AI as the allowed mapping targets. Tests live in `tests/test_load_cim_models.py` and run in CI.

---

## Configuration & Environment

- **AI provider:** Uses the provider configured on the app's Configuration page (`cim-plicity_settings.conf`, `[ai_configuration]`: `api_endpoint`, `model`, with `api_key` in the Splunk credential store), the same configuration as the [AI Detection endpoint](AI_DETECTION_ENDPOINT.md). There is no local fallback: without a configured API key the endpoint returns `AI service is not configured.`
- **Logging:** `$SPLUNK_HOME/var/log/splunk/cim-plicity_cim_mapping.log`.

---

## References
- [AI Detection Endpoint](AI_DETECTION_ENDPOINT.md)
- [MCP Tools](MCP_TOOLS.md)
- [Splunk Common Information Model](https://docs.splunk.com/Documentation/CIM/latest/User/Overview)
- [Splunk REST Handler Documentation](https://dev.splunk.com/enterprise/docs/developapps/customresthandlers/)

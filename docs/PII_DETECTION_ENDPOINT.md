# PII Detection Endpoint Documentation

## Overview

The PII (Personally Identifiable Information) Detection endpoint provides an automated way to analyze text data for sensitive information using the [scrubadub](https://github.com/datasnakes/scrubadub) library and custom detectors. It is implemented as a Splunk persistent REST handler in the `pii_detection.py` script and is designed to be called by Splunk or external clients to identify and help mask PII before indexing or further processing.

---

## Endpoint Details

- **Script Location:** `splunk-app/ucc-app/bin/pii_detection.py`
- **REST Path:** `/pii_detection`
- **Method:** `POST`
- **Handler:** `application.PiiDetection`
- **Authentication:** Requires Splunk session authentication (see Splunk REST handler docs)

---

## Request Structure

The endpoint expects a JSON payload with the following structure:

```
{
  "payload": "{\"text\": \"<text to analyze>\"}"
}
```

- The `payload` field is a JSON-encoded string containing a `text` field with the data to be analyzed for PII.
- The outer request may include additional Splunk context fields, but only `payload` is required for PII detection.

### Example Request

```
POST /pii_detection
Content-Type: application/json

{
  "payload": "{\"text\": \"John Doe's email is john.doe@example.com and his SSN is 123-45-6789.\"}"
}
```

---

## Response Structure

The endpoint returns a JSON object with the following structure:

```
{
  "payload": {
    "pii_results": [
      {
        "type": "EmailDetector",
        "text": "john.doe@example.com",
        "score": 1.0,
        "start": 21,
        "end": 41,
        "field": "email",
        "regex_pattern": "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b"
      },
      {
        "type": "en_US.SocialSecurityNumberDetector",
        "text": "123-45-6789",
        "score": 1.0,
        "start": 59,
        "end": 70,
        "field": "ssn",
        "regex_pattern": "\\b\\d{3}[-.]?\\d{2}[-.]?\\d{4}\\b"
      }
    ],
    "suggestion": "Detected PII types: EmailDetector, en_US.SocialSecurityNumberDetector. Recommended action: Review and mask sensitive data before indexing."
  },
  "status": 200
}
```

### Response Fields
- `payload.pii_results`: List of detected PII entities, each with:
  - `type`: The PII entity type (scrubadub detector name, e.g., EmailDetector, en_US.SocialSecurityNumberDetector, IpAddressDetector, etc.)
  - `text`: The exact text detected as PII
  - `score`: Confidence score (always 1.0 for scrubadub detectors)
  - `start`, `end`: Character offsets in the input text
  - `field`: Inferred field name (if possible)
  - `regex_pattern`: Regex pattern for Splunk SEDCMD masking (PCRE2 syntax)
- `payload.suggestion`: Human-readable summary and recommended action
- `status`: HTTP-like status code (200 for success, 400/500 for errors)

### Error Responses
- If the request is malformed or missing required fields:
  ```
  {
    "payload": {"error": "No text provided for PII detection"},
    "status": 400
  }
  ```
- If an internal error occurs:
  ```
  {
    "payload": {"error": "<error message>"},
    "status": 500
  }
  ```

---

## Configuration & Environment

- **PII Detection Engine:** [scrubadub](https://github.com/datasnakes/scrubadub) with custom detectors and patterns.
- **Custom Patterns:** You can provide custom regex patterns for PII detection. The redaction replacement string will use the custom pattern name (e.g., `[REDACTED_EMPLOYEE_ID]`).
- **Logging:** Logs are written to `$SPLUNK_HOME/var/log/splunk/cim-plicity.log`. PII is never logged directly; only text length and a hash are recorded for privacy.
- **Detectors:** The set of enabled detectors can be configured in `cim-plicity_settings.conf`.

---

## Example Use Cases

- **Splunk Data Onboarding:** Automatically scan incoming logs or events for PII before indexing.
- **Compliance Auditing:** Identify and report on sensitive data exposure in log streams.
- **Automated Masking:** Use the returned `regex_pattern` patterns to configure Splunk SEDCMD transforms for masking detected PII.
- **Custom PII Patterns:** Define your own PII patterns and get redaction rules with descriptive replacement names.

---

## Notes & Limitations

- The endpoint is stateless; each request is independent.
- Only the `text` field in the payload is analyzed.
- Some entity types (e.g., URL) are filtered out as non-PII unless they contain personal info.
- The regex patterns are best-effort and may need review for complex log formats.
- The endpoint is designed for integration with Splunk, but can be called by any authenticated client.

---

## References
- [scrubadub Documentation](https://datasnakes.github.io/scrubadub/)
- [Splunk REST Handler Documentation](https://dev.splunk.com/enterprise/docs/developapps/customresthandlers/)
- [Splunk SEDCMD Documentation](https://docs.splunk.com/Documentation/Splunk/latest/SearchReference/SED) 
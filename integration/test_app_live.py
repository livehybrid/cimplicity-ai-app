"""CIM-plicity on a real Splunk: install, REST handlers and the PII pipeline.

The AI-backed endpoints (ai_detection, the LLM half of cim_mapping) need an LLM
endpoint and key, which CI does not hold. They are covered only for their
'not configured' path; the live call is skipped with a reason.
"""
import json

import pytest

from conftest import APP, _loads

# Free text. The key=value email span case is guarded in test_bugfixes_live.py.
SAMPLE = "Contact john.doe@example.com about the login from 192.168.10.20 today"


def test_app_installed_and_enabled(splunk):
    status, body = splunk.get(f"/services/apps/local/{APP}")
    assert status == 200, body[:300]
    content = json.loads(body)["entry"][0]["content"]
    assert content["disabled"] is False
    assert content.get("version"), content


@pytest.mark.parametrize("stanza,key,want", [
    ("ai_configuration", "api_endpoint", "https://openrouter.ai/api/v1/chat/completions"),
    ("logging", "log_level", "INFO"),
])
def test_settings_handler_serves_stanza(splunk, stanza, key, want):
    # UCC admin_external handler (cim-plicity_rh_settings.py), per stanza as the
    # Configuration page reads it. The bare collection GET is covered in
    # test_bugfixes_live.py.
    status, body = splunk.get(f"/servicesNS/nobody/{APP}/cim-plicity_settings/{stanza}")
    assert status == 200, body[:400]
    assert json.loads(body)["entry"][0]["content"][key] == want


def test_pii_detection_finds_email_and_ip(splunk):
    # Runs the vendored scrubadub -> scikit-learn/scipy/nltk stack inside
    # Splunk's own Python. Those libs are cp39 builds, which is why the handler
    # pins python.required = 3.9. Watched fail: with the handler on 3.13 this and
    # the next test get 500 "bad character (49) in reply size". splunkd.log does
    # not record that error, so only the REST response can catch it.
    status, body = splunk.post_json("/services/pii_detection", {"text": SAMPLE})
    assert status == 200, body[:600]
    found = {r["text"] for r in json.loads(body)["pii_results"]}
    assert "john.doe@example.com" in found, found
    assert "192.168.10.20" in found, found


def test_pii_detection_rejects_empty_text(splunk):
    status, body = splunk.post_json("/services/pii_detection", {"text": ""})
    assert status == 400, body[:300]
    assert "No text provided" in body


def test_cim_mapping_reports_ai_not_configured(splunk):
    # Handler loads and validates; with no API key it must refuse cleanly.
    status, body = splunk.post_json(
        "/services/cim_mapping",
        {"extractedFields": [{"name": "user", "value": "john"}], "cimModel": "authentication"})
    assert status == 500, body[:300]
    assert "AI service is not configured" in body, body[:300]


def test_cim_mapping_rejects_missing_params(splunk):
    status, body = splunk.post_json("/services/cim_mapping", {})
    assert status == 400, body[:300]


def test_model_choices_serves_a_catalogue(splunk):
    # With no key it serves the fallback list (or the provider's public list).
    status, body = splunk.get(f"/servicesNS/nobody/{APP}/cim-plicity/ai_model_choices")
    assert status == 200, body[:300]
    entries = (_loads(body) or {}).get("entry") or []
    assert entries, body[:300]


@pytest.mark.skip(reason="needs an LLM endpoint + API key (AI Toolkit / OpenRouter) configured in "
                         "the app; CI holds none")
def test_ai_detection_live(splunk):
    status, body = splunk.post_json("/services/ai_detection", {"text": SAMPLE})
    assert status == 200, body[:600]

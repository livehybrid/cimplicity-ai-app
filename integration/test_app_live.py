"""CIM-plicity on a real Splunk: install, REST handlers and the PII pipeline.

The AI-backed endpoints (ai_detection, the LLM half of cim_mapping) need an LLM
endpoint and key, which CI does not hold. They are covered only for their
'not configured' path; the live call is skipped with a reason.
"""
import json

import pytest

from conftest import APP, _loads

SAMPLE = "user=john.doe@example.com action=login src=192.168.10.20 msg=ok"


def test_app_installed_and_enabled(splunk):
    status, body = splunk.get(f"/services/apps/local/{APP}")
    assert status == 200, body[:300]
    content = json.loads(body)["entry"][0]["content"]
    assert content["disabled"] is False
    assert content.get("version"), content


def test_settings_handler_lists_stanzas(splunk):
    # UCC admin_external handler (cim-plicity_rh_settings.py) loads and serves.
    status, body = splunk.get(f"/servicesNS/nobody/{APP}/cim-plicity_settings")
    assert status == 200, body[:400]
    names = {e["name"] for e in json.loads(body)["entry"]}
    assert {"ai_configuration", "logging"} <= names, names


def test_pii_detection_finds_email_and_ip(splunk):
    # Runs the vendored scrubadub -> scikit-learn/scipy/nltk stack inside
    # Splunk's own Python. Those libs are cp39 builds, which is why the handler
    # pins python.required = 3.9; on another interpreter this import fails.
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


def test_no_persistconn_protocol_errors(splunk):
    # The failure mode of an import crash in a persistent handler.
    bad = [l for l in splunk.splunkd_log().splitlines()
           if "bad character in reply size" in l]
    assert not bad, bad[-5:]


@pytest.mark.skip(reason="needs an LLM endpoint + API key (AI Toolkit / OpenRouter) configured in "
                         "the app; CI holds none")
def test_ai_detection_live(splunk):
    status, body = splunk.post_json("/services/ai_detection", {"text": SAMPLE})
    assert status == 200, body[:600]

"""Real-Splunk checks for the develop work (AI Toolkit backend, Prompts tab).

CI has no AI Toolkit and no LLM, so nothing here asserts a model's answer.
What it can prove without one:

- the Prompts tab's stanza exists and saves through the UCC handler,
- "Restore to default" serves exactly the prompt splunkd holds in default/,
- the connection dropdown degrades to an empty list when the Toolkit is absent,
- selecting the Toolkit backend with no API key reaches the Toolkit path in
  both AI handlers instead of stopping at "not configured" (docs/LLM_BACKENDS.md:
  "No API key needed").

Expected values come from splunkd's own conf endpoint and from cim-plicity.log
read with docker exec, never from the handlers under test.
"""
import json
import uuid

import pytest

from conftest import APP, _loads, container_exec

SETTINGS = f"/servicesNS/nobody/{APP}/cim-plicity_settings"
CONF = f"/servicesNS/nobody/{APP}/configs/conf-cim-plicity_settings"
LOG_PATH = "/opt/splunk/var/log/splunk/cim-plicity.log"
TOOLKIT_LINE = "AI Toolkit request via | ai"


def _entries(body):
    return {e["name"]: e["content"] for e in (_loads(body) or {}).get("entry", [])}


def _conf_stanza(splunk, stanza):
    status, body = splunk.get(f"{CONF}/{stanza}")
    assert status == 200, body[:300]
    return _entries(body)[stanza]


def _toolkit_lines():
    code, out = container_exec("cat", LOG_PATH)
    assert code == 0, f"{LOG_PATH} does not exist in the container"
    return out.count(TOOLKIT_LINE)


def test_prompt_defaults_serve_the_prompt_splunkd_ships(splunk):
    status, body = splunk.get(f"/services/{APP}/prompt_defaults")
    assert status == 200, body[:300]
    defaults = json.loads(body)["defaults"]
    assert set(defaults) == {"ai_detection", "cim_mapping"}, defaults.keys()
    shipped = _conf_stanza(splunk, "prompts")
    # splunkd keeps each continuation line's indentation and trailing space;
    # the button offers the same lines without it.
    def lines(text):
        return [line.strip() for line in text.strip().splitlines()]
    for name, text in defaults.items():
        assert text and lines(text) == lines(shipped[f"{name}_guidance"]), name


def test_toolkit_connections_are_empty_without_the_ai_toolkit(splunk):
    status, body = splunk.get(f"/services/{APP}/toolkit_connections")
    assert status == 200, body[:300]
    assert json.loads(body)["entry"] == []


def test_prompts_tab_saves_through_the_settings_handler(splunk):
    original = _conf_stanza(splunk, "prompts")["cim_mapping_guidance"]
    marker = "it-" + uuid.uuid4().hex
    edited = original + " " + marker
    try:
        status, body = splunk.post_form(f"{SETTINGS}/prompts", {"cim_mapping_guidance": edited})
        assert status == 200, body[:400]
        assert marker in _conf_stanza(splunk, "prompts")["cim_mapping_guidance"]
    finally:
        splunk.post_form(f"{SETTINGS}/prompts", {"cim_mapping_guidance": original})
    assert marker not in _conf_stanza(splunk, "prompts")["cim_mapping_guidance"]


def _not_configured(splunk):
    status, body = splunk.post_json(
        "/services/cim_mapping",
        {"extractedFields": [{"name": "user", "value": "john"}], "cimModel": "authentication"})
    return status == 500 and "AI service is not configured" in body, (status, body[:300])


def test_direct_backend_without_a_key_is_not_configured_before(splunk):
    # Positive control for the Toolkit tests: no key, direct backend.
    ok, detail = _not_configured(splunk)
    assert ok, detail


@pytest.fixture
def toolkit_backend(splunk):
    # Set through splunkd's conf endpoint, not the UCC handler: saving the
    # ai_configuration tab without an api_key leaves a truthy key behind, which
    # would let these tests pass with the key check still in place.
    ok, detail = _not_configured(splunk)
    assert ok, f"precondition: no API key configured; {detail}"
    status, body = splunk.post_form(f"{CONF}/ai_configuration", {"backend": "splunk_ai_toolkit"})
    assert status == 200, body[:400]
    yield
    status, body = splunk.post_form(f"{CONF}/ai_configuration", {"backend": "direct"})
    assert status == 200, body[:400]


def test_cim_mapping_on_the_toolkit_backend_needs_no_api_key(splunk, toolkit_backend):
    before = _toolkit_lines()
    status, body = splunk.post_json(
        "/services/cim_mapping",
        {"extractedFields": [{"name": "user", "value": "john"}], "cimModel": "authentication"})
    assert "AI service is not configured" not in body, (status, body[:300])
    assert _toolkit_lines() > before, (status, body[:300])
    # CI has no AI Toolkit, so `| ai` is an unknown command.
    assert "Splunk AI Toolkit is not available" in body, (status, body[:300])


def test_ai_detection_on_the_toolkit_backend_needs_no_api_key(splunk, toolkit_backend):
    before = _toolkit_lines()
    status, body = splunk.post_json("/services/ai_detection",
                                    {"text": "user=alice action=login status=200"})
    # No Toolkit in CI: the call fails and ai_detection uses its local fallback.
    assert status == 200, body[:300]
    assert _toolkit_lines() > before, body[:300]


def test_direct_backend_without_a_key_is_not_configured_after(splunk):
    assert _conf_stanza(splunk, "ai_configuration").get("backend") == "direct"
    ok, detail = _not_configured(splunk)
    assert ok, detail

"""Real-Splunk guards for three defects that only show inside splunkd.

1. The bare settings collection GET answered 500 wrapping splunktaucclib's
   "REST Error [404]: Not Found -- name=None" (bin/cim_plicity_settings_handler.py).
2. PII email spans swallowed the key in key=value text (lib/email_detector.py),
   emails were labelled with the first key= nearby and given the escaped literal
   address as their redaction pattern (lib/pii_detection_logic.py).
3. cim-plicity.log was never created when cim_mapping.py was the first handler
   the shared persistconn process imported, its lines had no timestamp, and the
   Configuration page's log level was written to a key no handler read
   (lib/cim_plicity_logging.py, globalConfig loggingTab field, default/props.conf).

Expected values come from routes the app code never consults: the shipped
default conf on disk (the extracted package), str.index on the test's own text,
the log file read with docker exec, and Splunk's own indexing of _internal.

Run after test_app_live.py: the masking test stores and then removes an API key.
"""
import configparser
import hashlib
import json
import os
import time
import urllib.parse
import uuid

import pytest

from conftest import APP, APP_STAGE, _loads, container_exec

SETTINGS = f"/servicesNS/nobody/{APP}/cim-plicity_settings"
LOG_PATH = "/opt/splunk/var/log/splunk/cim-plicity.log"
REALM = f"__REST_CREDENTIAL__#{APP}#configs/conf-cim-plicity_settings"


def _shipped_settings():
    conf = configparser.ConfigParser(interpolation=None, strict=False)
    conf.read(os.path.join(APP_STAGE, "default", "cim-plicity_settings.conf"))
    return {s: dict(conf.items(s)) for s in conf.sections()}


def _entries(body):
    return {e["name"]: e["content"] for e in (_loads(body) or {}).get("entry", [])}


def _read_log():
    code, out = container_exec("cat", LOG_PATH)
    assert code == 0, f"{LOG_PATH} does not exist in the container"
    return out


def _wait_for(pred, timeout=60, every=2):
    deadline = time.time() + timeout
    while True:
        value = pred()
        if value or time.time() > deadline:
            return value
        time.sleep(every)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pii(splunk, text):
    status, body = splunk.post_json("/services/pii_detection", {"text": text})
    assert status == 200, body[:400]
    return json.loads(body)


# --- 1. settings collection -------------------------------------------------

def test_settings_collection_lists_every_stanza(splunk):
    shipped = _shipped_settings()
    assert set(shipped) == {"ai_configuration", "logging", "prompts"}, shipped

    status, body = splunk.get(SETTINGS)
    assert status == 200, body[:500]
    listed = _entries(body)
    assert set(listed) == set(shipped), listed.keys()
    for stanza, keys in shipped.items():
        if stanza == "prompts":
            continue  # multi-line conf values: configparser cannot join them as Splunk does
        for key, value in keys.items():
            assert listed[stanza].get(key) == value, (stanza, key, listed[stanza])
    # The prompts are compared with splunkd's own conf endpoint instead.
    status, body = splunk.get(f"/servicesNS/nobody/{APP}/configs/conf-cim-plicity_settings/prompts")
    assert status == 200, body[:300]
    conf = _entries(body)["prompts"]
    for key in shipped["prompts"]:
        assert listed["prompts"].get(key) == conf.get(key), key
        assert conf.get(key), key


def test_settings_collection_agrees_with_per_stanza_reads(splunk):
    # The per-stanza GET is what the Configuration page uses; it must keep working
    # and the list must not disagree with it.
    status, body = splunk.get(SETTINGS)
    assert status == 200, body[:500]
    listed = _entries(body)
    for stanza in ("ai_configuration", "logging", "prompts"):
        status, one = splunk.get(f"{SETTINGS}/{stanza}")
        assert status == 200, one[:300]
        assert _entries(one)[stanza] == listed[stanza]


def test_settings_collection_masks_the_api_key(splunk):
    secret = "sk-it-" + uuid.uuid4().hex
    shipped = _shipped_settings()["ai_configuration"]
    status, body = splunk.post_form(f"{SETTINGS}/ai_configuration", {
        "api_endpoint": shipped["api_endpoint"], "model": shipped["model"], "api_key": secret})
    assert status == 200, body[:400]
    try:
        status, body = splunk.get(SETTINGS)
        assert status == 200, body[:500]
        assert secret not in body
        assert _entries(body)["ai_configuration"]["api_key"] == "******"
    finally:
        name = urllib.parse.quote(f"{REALM}:ai_configuration:", safe="")
        splunk.remove(f"/servicesNS/nobody/{APP}/storage/passwords/{name}")
        splunk.post_form(f"/servicesNS/nobody/{APP}/configs/conf-cim-plicity_settings/ai_configuration",
                         {"api_key": ""})
    # Cleanup really landed: the app is back to "not configured".
    status, body = splunk.post_json(
        "/services/cim_mapping",
        {"extractedFields": [{"name": "user", "value": "john"}], "cimModel": "authentication"})
    assert status == 500 and "AI service is not configured" in body, body[:300]


# --- 2. PII email span ------------------------------------------------------

def test_pii_email_span_in_key_value_text_is_the_address_only(splunk):
    text = "user=alice@example.com action=login"
    results = _pii(splunk, text)["pii_results"]
    emails = [r for r in results if "@" in r["text"]]
    assert len(emails) == 1, results
    start = text.index("alice@example.com")
    assert (emails[0]["start"], emails[0]["end"]) == (start, start + len("alice@example.com")), emails
    assert text[:emails[0]["start"]] + "#" + text[emails[0]["end"]:] == "user=# action=login"


def test_pii_email_field_and_redaction_pattern(splunk):
    # src= is the first key near the address; the address belongs to user=.
    import re
    text = 'src=10.0.0.1 user="alice@example.com" action=login'
    results = _pii(splunk, text)["pii_results"]
    start = text.index("alice@example.com")
    emails = [r for r in results if r["start"] == start]
    assert len(emails) == 1, results
    assert emails[0]["field"] == "user", emails
    # Generic, not the escaped literal: it matches addresses not in the input.
    pattern = re.compile(emails[0]["regex_pattern"])
    assert pattern.fullmatch("bob@example.co.uk"), emails[0]["regex_pattern"]


# --- 3. logging -------------------------------------------------------------

def _restart_persistent_handlers():
    """Kill splunkd's shared Python 3.9 persistconn process so the next request
    starts a fresh one; splunkd respawns it on demand."""
    container_exec("sh", "-c", "kill $(pgrep -f '[p]ython3.9 .*persistconn/appserver.py') 2>/dev/null; true")


def test_logs_land_in_cim_plicity_log_when_cim_mapping_loads_first(splunk):
    # Reproduce the ordering that lost the file: cim_mapping.py is the first app
    # script the fresh shared process imports, pii_detection.py comes second.
    _restart_persistent_handlers()

    def cim_mapping_up():
        status, _ = splunk.post_json("/services/cim_mapping", {})
        return status == 400
    assert _wait_for(cim_mapping_up, timeout=120), "cim_mapping never answered after the restart"

    text = f"login from 10.20.30.40 marker {uuid.uuid4().hex}"
    _pii(splunk, text)
    marker = f"sha256={_sha(text)}"

    log = _wait_for(lambda: (lambda s: s if marker in s else "")(_read_log()), timeout=30)
    assert marker in log, "pii_detection's line did not reach cim-plicity.log"
    assert "cim-plicity.cim_mapping - Starting CIM Mapping REST handler" in log
    code, _ = container_exec("test", "-e", "/opt/splunk/var/log/splunk/cim-plicity_cim_mapping.log")
    assert code != 0, "a second, per-handler log file still exists"


def test_log_lines_are_timestamped_and_indexed_with_the_app_sourcetype(splunk):
    text = f"indexing probe {uuid.uuid4().hex} bob@example.com"
    _pii(splunk, text)
    marker = f"sha256={_sha(text)}"
    line = _wait_for(lambda: next((ln for ln in _read_log().splitlines() if marker in ln), ""), timeout=30)
    assert line, "marker line never written"
    assert line[:4].isdigit() and line[4] == "-" and line[10] == " ", line

    spl = f'search index=_internal source="*cim-plicity.log" "{marker}" | table sourcetype linecount _time _indextime'
    rows = _wait_for(lambda: splunk.oneshot(spl, earliest_time="-1h"), timeout=240, every=10)
    assert rows, "the marker line was never indexed in _internal"
    assert {r["sourcetype"] for r in rows} == {"cim-plicity:log"}, rows
    assert all(r["linecount"] == "1" for r in rows), rows


def test_log_level_from_the_configuration_page_is_honoured(splunk):
    # The Configuration page posts the loggingTab field; it must be the key the
    # handlers read (log_level), or the setting does nothing.
    status, body = splunk.post_form(f"{SETTINGS}/logging", {"log_level": "ERROR"})
    assert status == 200, body[:400]
    try:
        quiet = f"quiet {uuid.uuid4().hex}"
        _pii(splunk, quiet)
    finally:
        status, body = splunk.post_form(f"{SETTINGS}/logging", {"log_level": "INFO"})
        assert status == 200, body[:400]
    loud = f"loud {uuid.uuid4().hex}"
    _pii(splunk, loud)  # positive control: same path, INFO again, must be written

    log = _wait_for(lambda: (lambda s: s if _sha(loud) in s else "")(_read_log()), timeout=30)
    assert _sha(loud) in log, "INFO line missing after restoring INFO"
    assert _sha(quiet) not in log, "INFO line written while log_level was ERROR"

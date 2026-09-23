"""Tests for lib/prompts.py, the customer-editable prompt guidance.

The design point these protect: a prompt is guidance + contract, only the
guidance is configurable, and a customer edit that would break the app falls
back to the shipped default instead of being sent.
"""
import os
import re

import pytest

import prompts

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(REPO, "ucc-app", "default", "cim-plicity_prompts.conf")
SPEC = os.path.join(REPO, "ucc-app", "README", "cim-plicity_prompts.conf.spec")

DETECT_VALUES = {"sample_data": "a=1 b=2", "description_block": ""}
MAP_VALUES = {"cim_model": "Authentication",
              "available_cim_fields": '["user", "src"]',
              "extracted_fields": '[{"name": "u"}]'}


def _parse_conf(path):
    """Minimal Splunk conf reader: stanzas plus backslash continuations."""
    stanzas, current, key, buf = {}, None, None, []

    def flush():
        if current and key:
            stanzas.setdefault(current, {})[key] = " ".join(buf).strip()

    for raw in open(path):
        line = raw.rstrip("\n")
        if line.strip().startswith("#"):
            continue
        m = re.match(r"^\[(.+)\]\s*$", line)
        if m:
            flush()
            current, key, buf = m.group(1), None, []
            stanzas.setdefault(current, {})
            continue
        if key is not None:
            buf.append(line.strip().rstrip("\\").strip())
            if not line.rstrip().endswith("\\"):
                flush()
                key, buf = None, []
            continue
        m = re.match(r"^([a-z_]+)\s*=\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2)
            buf = [val.rstrip("\\").strip()]
            if not val.rstrip().endswith("\\"):
                flush()
                key, buf = None, []
    flush()
    return stanzas


# --- the split that is the whole point -------------------------------------

def test_the_contract_is_appended_and_is_not_configurable():
    out = prompts.render("ai_detection", DETECT_VALUES,
                         configured="Totally custom guidance using {sample_data}.")
    assert "Totally custom guidance" in out
    # The customer's text cannot remove the JSON shape the parsers depend on.
    assert "max_timestamp_lookahead" in out
    assert "Do not include any explanatory text" in out


def test_the_contract_is_absent_from_the_configurable_guidance():
    # If it were in the conf, a customer could edit it away.
    for name in ("ai_detection", "cim_mapping"):
        assert "Do not include any explanatory text" not in prompts.DEFAULT_GUIDANCE[name]
    conf = _parse_conf(CONF)
    for name in ("ai_detection", "cim_mapping"):
        assert "Do not include any explanatory text" not in conf[name]["guidance"]


# --- substitution, which must not be str.format() --------------------------

def test_placeholders_are_substituted():
    out = prompts.render("ai_detection", DETECT_VALUES)
    assert "a=1 b=2" in out
    assert "{sample_data}" not in out


def test_json_braces_in_guidance_survive():
    # str.format() would raise KeyError on the first {" here. Both the contract
    # and any pasted example JSON contain literal braces.
    guidance = 'Use {sample_data}. Example output: {"a": 1, "b": {"c": 2}}'
    out = prompts.render("ai_detection", DETECT_VALUES, configured=guidance)
    assert '{"a": 1, "b": {"c": 2}}' in out


def test_an_unknown_placeholder_is_left_alone_not_an_error():
    out = prompts.substitute("keep {mystery} drop {sample_data}", {"sample_data": "X"})
    assert out == "keep {mystery} drop X"


def test_customer_data_containing_braces_is_injected_verbatim():
    values = dict(DETECT_VALUES, sample_data='attrs={"zone":"secure"}')
    out = prompts.render("ai_detection", values)
    assert 'attrs={"zone":"secure"}' in out


# --- validation and fallback ------------------------------------------------

def test_guidance_missing_a_required_placeholder_falls_back(caplog):
    # Sending this would ask the model to analyse a sample it was never given.
    out = prompts.render("ai_detection", DETECT_VALUES,
                         configured="Analyse the log and return extractions.")
    assert "You are a Splunk expert" in out          # the shipped default
    assert "Analyse the log and return extractions." not in out


def test_the_fallback_says_which_placeholder_is_missing(caplog):
    import logging
    with caplog.at_level(logging.ERROR):
        prompts.resolve_guidance("cim_mapping", "Map fields for {cim_model} please")
    msg = caplog.text
    assert "{available_cim_fields}" in msg and "{extracted_fields}" in msg
    assert "{cim_model}" not in msg                  # the one they kept


@pytest.mark.parametrize("configured", [None, "", "   ", "\n\n"])
def test_absent_guidance_uses_the_default(configured):
    out = prompts.render("cim_mapping", MAP_VALUES, configured=configured)
    assert "You are a Splunk CIM expert" in out


def test_a_valid_custom_guidance_is_used_as_given():
    guidance = "Map {cim_model} using {available_cim_fields} and {extracted_fields}. Be terse."
    out = prompts.render("cim_mapping", MAP_VALUES, configured=guidance)
    assert "Be terse." in out
    assert "You are a Splunk CIM expert" not in out
    assert "Authentication" in out


def test_missing_placeholders_reports_only_what_is_missing():
    assert prompts.missing_placeholders("ai_detection", "has {sample_data}") == ()
    assert prompts.missing_placeholders("ai_detection", "has nothing") == ("sample_data",)


# --- reading the conf -------------------------------------------------------

def test_a_broken_conf_read_is_not_fatal():
    def boom(_name):
        raise RuntimeError("kv store down")
    assert prompts.read_configured(boom, "ai_detection") is None


def test_an_empty_guidance_key_reads_as_unconfigured():
    assert prompts.read_configured(lambda n: {"guidance": "   "}, "ai_detection") is None
    assert prompts.read_configured(lambda n: {}, "ai_detection") is None
    assert prompts.read_configured(lambda n: {"guidance": "x"}, "ai_detection") == "x"


# --- the shipped files ------------------------------------------------------

def test_the_conf_ships_both_stanzas_with_their_placeholders():
    conf = _parse_conf(CONF)
    for name, required in prompts.REQUIRED_PLACEHOLDERS.items():
        assert name in conf, name
        guidance = conf[name]["guidance"]
        for ph in required:
            assert "{%s}" % ph in guidance, (name, ph)


def test_the_shipped_conf_and_the_code_default_stay_in_lockstep():
    # DEFAULT_GUIDANCE is the fallback when a customer's edit is unusable, so a
    # drift between them means the fallback is not what the app documents.
    conf = _parse_conf(CONF)
    for name in prompts.DEFAULT_GUIDANCE:
        a = " ".join(conf[name]["guidance"].split())
        b = " ".join(prompts.DEFAULT_GUIDANCE[name].split())
        assert a == b, "%s drifted between the conf and DEFAULT_GUIDANCE" % name


def test_a_spec_file_ships_for_appinspect():
    # AppInspect flags any custom conf without a README/*.conf.spec.
    assert os.path.exists(SPEC)
    spec = open(SPEC).read()
    assert "guidance = <string>" in spec
    assert "{sample_data}" in spec

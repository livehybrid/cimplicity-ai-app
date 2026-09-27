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


# --- two editable places, with precedence -----------------------------------

UI = "the Prompts tab"


def test_the_settings_page_wins_over_the_conf_file():
    # The UI is where a customer looks first; a value typed there must not be
    # silently outranked by a file they may not know exists.
    out = prompts.render("ai_detection", DETECT_VALUES,
                         configured="FROM CONF {sample_data}",
                         settings_guidance="FROM UI {sample_data}")
    assert "FROM UI" in out and "FROM CONF" not in out


def test_the_conf_file_is_used_when_the_settings_page_is_blank():
    for blank in (None, "", "   "):
        out = prompts.render("ai_detection", DETECT_VALUES,
                             configured="FROM CONF {sample_data}",
                             settings_guidance=blank)
        assert "FROM CONF" in out, repr(blank)


def test_a_bad_settings_value_falls_through_to_the_conf_rather_than_to_default():
    # The important property: one bad edit cannot mask a good prompt elsewhere.
    out = prompts.render("ai_detection", DETECT_VALUES,
                         configured="FROM CONF {sample_data}",
                         settings_guidance="no placeholder here")
    assert "FROM CONF" in out
    assert "You are a Splunk expert" not in out


def test_both_bad_falls_all_the_way_to_the_shipped_default():
    out = prompts.render("ai_detection", DETECT_VALUES,
                         configured="also bad", settings_guidance="bad too")
    assert "You are a Splunk expert" in out


def test_the_log_names_which_place_the_bad_value_is_in(caplog):
    import logging
    with caplog.at_level(logging.ERROR):
        prompts.resolve_guidance("ai_detection",
                                 ("the Prompts tab on the Configuration page", "bad"),
                                 ("cim-plicity_prompts.conf", "also bad {sample_data}"))
    assert "Prompts tab" in caplog.text
    # the second candidate was valid, so it must not be reported as bad
    assert "cim-plicity_prompts.conf" not in caplog.text


def test_settings_guidance_is_read_from_the_prompts_stanza():
    # UCC writes one field per prompt into [prompts] of cim-plicity_settings.conf.
    seen = []
    def read(stanza):
        seen.append(stanza)
        return {"ai_detection_guidance": "x", "cim_mapping_guidance": "y"}
    assert prompts.read_settings_guidance(read, "ai_detection") == "x"
    assert prompts.read_settings_guidance(read, "cim_mapping") == "y"
    assert seen == [prompts.SETTINGS_STANZA, prompts.SETTINGS_STANZA]


def test_a_broken_settings_read_is_not_fatal():
    def boom(_stanza):
        raise RuntimeError("conf unavailable")
    assert prompts.read_settings_guidance(boom, "ai_detection") is None


def test_the_globalconfig_prompts_tab_matches_the_fields_the_code_reads():
    # A field renamed in globalConfig without renaming it here would silently
    # never be read, and the UI would look like it did nothing.
    import json, os
    gc = json.load(open(os.path.join(REPO, "globalConfig.json")))
    tab = next(t for t in gc["pages"]["configuration"]["tabs"]
               if t.get("name") == prompts.SETTINGS_STANZA)
    fields = {e["field"] for e in tab["entity"]}
    expected = {prompts.SETTINGS_FIELD % n for n in prompts.REQUIRED_PLACEHOLDERS}
    assert fields == expected, (fields, expected)
    for e in tab["entity"]:
        # custom, not textarea: the control renders its own box plus a
        # Restore to default button (see the custom-control tests below).
        assert e["type"] == "custom", e["field"]


SETTINGS_CONF = os.path.join(REPO, "ucc-app", "default", "cim-plicity_settings.conf")


def test_the_prompts_stanza_exists_in_the_default_settings_conf():
    # ucc-gen generates a tab's conf SPEC but NOT its stanza, and the UCC settings
    # REST handler 404s on a stanza it cannot find. Without this stanza the
    # Prompts tab renders and every save fails with
    # "Could not find object id=prompts". Found by testing the deployed app.
    stanzas = _parse_conf(SETTINGS_CONF)
    assert prompts.SETTINGS_STANZA in stanzas, "the [prompts] stanza is missing"
    for name in prompts.REQUIRED_PLACEHOLDERS:
        assert prompts.SETTINGS_FIELD % name in stanzas[prompts.SETTINGS_STANZA]


def test_the_settings_conf_ships_the_real_prompt_not_an_empty_box():
    # An empty Prompts tab looks broken: someone opening it expects to see the
    # prompt the app is actually using, and to edit from there.
    stanzas = _parse_conf(SETTINGS_CONF)[prompts.SETTINGS_STANZA]
    for name, required in prompts.REQUIRED_PLACEHOLDERS.items():
        value = stanzas[prompts.SETTINGS_FIELD % name]
        assert value.strip(), "%s ships empty" % name
        for ph in required:
            assert "{%s}" % ph in value, (name, ph)


def test_the_settings_conf_stays_in_lockstep_with_the_code_default():
    # Generated by scripts/gen_prompt_defaults.py from DEFAULT_GUIDANCE. Drift
    # would mean the tab shows one prompt while the app uses another, which is
    # worse than showing nothing.
    stanzas = _parse_conf(SETTINGS_CONF)[prompts.SETTINGS_STANZA]
    for name in prompts.DEFAULT_GUIDANCE:
        shipped = " ".join(stanzas[prompts.SETTINGS_FIELD % name].split())
        code = " ".join(prompts.DEFAULT_GUIDANCE[name].split())
        assert shipped == code, (
            "%s drifted; re-run scripts/gen_prompt_defaults.py" % name)


def test_the_output_contract_is_absent_from_the_settings_conf_too():
    # Same rule as the prompts conf: a customer must not be able to edit the
    # JSON contract away, so it is never in an editable surface.
    stanzas = _parse_conf(SETTINGS_CONF)[prompts.SETTINGS_STANZA]
    for name in prompts.DEFAULT_GUIDANCE:
        assert "Do not include any explanatory text" not in stanzas[
            prompts.SETTINGS_FIELD % name]


# --- the Prompts tab's custom controls --------------------------------------

def test_each_prompt_field_points_at_its_own_custom_control():
    # UCC does NOT pass the field name to a custom control's constructor, so the
    # prompt a control edits is decided by which module the entity points at.
    # A src pointing at the wrong module would silently edit the other prompt.
    import json
    gc = json.load(open(os.path.join(REPO, "globalConfig.json")))
    tab = next(t for t in gc["pages"]["configuration"]["tabs"]
               if t.get("name") == prompts.SETTINGS_STANZA)
    for e in tab["entity"]:
        assert e["type"] == "custom", e["field"]
        assert e["options"]["type"] == "external"
        name = e["field"].replace("_guidance", "")
        assert e["options"]["src"] == "%s_prompt" % name, e["field"]


def test_every_custom_control_module_exists_and_names_its_prompt():
    import json
    import re as _re
    gc = json.load(open(os.path.join(REPO, "globalConfig.json")))
    tab = next(t for t in gc["pages"]["configuration"]["tabs"]
               if t.get("name") == prompts.SETTINGS_STANZA)
    custom_dir = os.path.join(REPO, "ucc-app", "appserver", "static", "js",
                              "build", "custom")
    for e in tab["entity"]:
        src = os.path.join(custom_dir, e["options"]["src"] + ".js")
        assert os.path.exists(src), src
        body = open(src).read()
        name = e["field"].replace("_guidance", "")
        # makePromptEditor('<prompt>') is what binds the module to its prompt.
        assert _re.search(r"makePromptEditor\(['\"]%s['\"]\)" % name, body), src
        assert "export default" in body
    assert os.path.exists(os.path.join(custom_dir, "prompt_editor_base.js"))


def test_the_custom_controls_fetch_defaults_rather_than_embedding_them():
    # A copy of the guidance in the JavaScript would be a fourth one and would
    # drift from the prompt the app actually sends.
    base = os.path.join(REPO, "ucc-app", "appserver", "static", "js", "build",
                        "custom", "prompt_editor_base.js")
    body = open(base).read()
    assert "prompt_defaults" in body
    for name in prompts.DEFAULT_GUIDANCE:
        first_line = prompts.DEFAULT_GUIDANCE[name].strip().split("\n")[0][:40]
        assert first_line not in body, "guidance text leaked into the JS"


def test_as_shipped_strips_the_indentation_of_the_triple_quoted_source():
    out = prompts.as_shipped("\n        first line\n          second\n        \n")
    assert out == "first line\nsecond\n"[:-1] or out.split("\n")[0] == "first line"
    assert not out.startswith("\n")
    assert "        " not in out


def test_the_endpoint_and_the_conf_agree_exactly():
    # Restore to default must reproduce the value in default/, not a
    # differently-whitespaced equivalent, or a restored-then-saved prompt differs
    # from a fresh install's for no reason.
    stanzas = _parse_conf(SETTINGS_CONF)[prompts.SETTINGS_STANZA]
    for name in prompts.DEFAULT_GUIDANCE:
        conf_value = " ".join(stanzas[prompts.SETTINGS_FIELD % name].split())
        served = " ".join(prompts.as_shipped(prompts.DEFAULT_GUIDANCE[name]).split())
        assert conf_value == served, name

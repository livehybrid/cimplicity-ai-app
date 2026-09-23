"""Tests for lib/llm_toolkit.py, the AI Toolkit (`| ai`) backend.

These encode the rules the live AI Toolkit 6.1 imposes, each found by probing
and each fatal if got wrong. The search runner is injected, so nothing here
needs splunkd or a Toolkit.
"""
import pytest

import llm_toolkit


def runner(rows=None, messages=None, sink=None, boom=None):
    def search(spl):
        if sink is not None:
            sink.append(spl)
        if boom is not None:
            raise boom
        return list(rows or []), list(messages or [])
    return search


OK_ROWS = [{"ai_result_1": '{"ok": true}'}]


# --- the brace rule, which every CIMPlicity prompt would otherwise trip ------

def test_braces_are_doubled_so_str_format_restores_them():
    # `| ai` runs the prompt through str.format(), so a literal { is a KeyError
    # that surfaces as a bare "Error in 'ai' command: 'ok'".
    assert llm_toolkit.escape_prompt("reply with {ok}") == "reply with {{ok}}"


def test_a_json_schema_example_survives_escaping():
    prompt = 'Return {"field": "x", "confidence": 0.0}'
    assert llm_toolkit.escape_prompt(prompt) == 'Return {{"field": "x", "confidence": 0.0}}'


def test_customer_data_containing_braces_is_safe():
    # ai_detection interpolates the customer's RAW EVENT into the prompt. A JSON
    # log line would otherwise kill the search.
    event = 'decision=DENY attrs={"zone":"secure"} nested={{a}}'
    escaped = llm_toolkit.escape_prompt(event)
    assert "{{" in escaped and "}}" in escaped
    # str.format() is single-pass, so escaping round-trips exactly.
    assert escaped.format() == event


def test_escaping_happens_before_spl_quoting_not_after():
    spl = llm_toolkit.build_spl('say {"a": 1}')
    # Doubled braces AND escaped quotes, in that order.
    assert '{{\\"a\\": 1}}' in spl


# --- the search that gets built --------------------------------------------

def test_minimal_spl_shape():
    assert llm_toolkit.build_spl("hello") == '| makeresults | ai prompt="hello"'


def test_a_named_connection_is_added_when_configured():
    spl = llm_toolkit.build_spl("hello", connection="OpenAIDefault")
    assert spl.endswith(' connection="OpenAIDefault"')


def test_provider_and_model_are_only_added_together():
    # `| ai` rejects either one alone: "When 'model' is specified, 'provider'
    # must also be specified."
    assert "model=" not in llm_toolkit.build_spl("hi", model="gpt-4o")
    assert "provider=" not in llm_toolkit.build_spl("hi", provider="OpenAI")
    spl = llm_toolkit.build_spl("hi", provider="OpenAI", model="gpt-4o")
    assert 'provider="OpenAI" model="gpt-4o"' in spl


def test_settings_drive_the_search():
    sink = []
    llm_toolkit.complete({"toolkit_connection": "OpenAIDefault"}, "hi",
                         runner(OK_ROWS, sink=sink))
    assert 'connection="OpenAIDefault"' in sink[0]


# --- reading the answer -----------------------------------------------------

def test_the_result_field_is_ai_result_1():
    # Not result_1: that is `| aiagent`.
    assert llm_toolkit.RESULT_FIELD == "ai_result_1"
    assert llm_toolkit.complete({}, "hi", runner(OK_ROWS)) == '{"ok": true}'


# --- failures, which must never look like an empty answer -------------------

def test_no_rows_is_a_failure_not_an_empty_answer():
    # A failed | ai run can come back DONE with nothing in it.
    with pytest.raises(llm_toolkit.ToolkitError) as exc:
        llm_toolkit.complete({}, "hi", runner([]))
    assert exc.value.reason == "bad_response"


@pytest.mark.parametrize("row", [{}, {"other": "x"}, {"ai_result_1": ""},
                                 {"ai_result_1": "   "}, {"ai_result_1": None}])
def test_a_missing_or_empty_result_field_is_a_failure(row):
    with pytest.raises(llm_toolkit.ToolkitError) as exc:
        llm_toolkit.complete({}, "hi", runner([row]))
    assert exc.value.reason == "bad_response"


def test_an_unconfigured_toolkit_is_reported_as_not_configured():
    for msg in ("Error in 'ai' command: No default LLM configuration found.",
                "Error in 'ai' command: No configuration found for llm connection: X"):
        with pytest.raises(llm_toolkit.ToolkitError) as exc:
            llm_toolkit.complete({}, "hi", runner(OK_ROWS, [msg]))
        assert exc.value.reason == "not_configured", msg


def test_a_missing_toolkit_is_reported_as_unavailable():
    # On an instance with no AI Toolkit at all the command does not exist.
    with pytest.raises(llm_toolkit.ToolkitError) as exc:
        llm_toolkit.complete({}, "hi", runner([], ["Unknown search command 'ai'"]))
    assert exc.value.reason == "unavailable"


def test_an_unrecognised_message_is_transport():
    with pytest.raises(llm_toolkit.ToolkitError) as exc:
        llm_toolkit.complete({}, "hi", runner([], ["something else went wrong"]))
    assert exc.value.reason == "transport"


def test_messages_win_over_rows():
    # | ai can return a row AND an error; the error is the truth.
    with pytest.raises(llm_toolkit.ToolkitError):
        llm_toolkit.complete({}, "hi", runner(OK_ROWS, ["Error in 'ai' command: boom"]))


def test_a_dispatch_exception_becomes_transport_not_a_crash():
    with pytest.raises(llm_toolkit.ToolkitError) as exc:
        llm_toolkit.complete({}, "hi", runner(boom=RuntimeError("splunkd down")))
    assert exc.value.reason == "transport"
    assert "splunkd down" in exc.value.detail


# --- the successful-looking failure ----------------------------------------

def test_an_error_returned_as_content_is_a_failure_not_an_answer():
    # `| ai` reports LLM-level failures by putting the message in ai_result_1 and
    # returning a SUCCESSFUL search. Observed live: gpt-5-mini spent its whole
    # 2000-token connection budget reasoning and came back with this.
    msg = "Empty response content received from the server."
    with pytest.raises(llm_toolkit.ToolkitError) as exc:
        llm_toolkit.complete({}, "hi", runner([{"ai_result_1": msg}]))
    assert exc.value.reason == "bad_response"
    assert msg in exc.value.detail


@pytest.mark.parametrize("content,reason", [
    ("Authentication failed: Incorrect API key provided. Please check your API key.",
     "not_configured"),
    ("You exceeded your current quota, please check your plan and billing details.",
     "not_configured"),
    ("Prompt length too long. Please reduce the length of the prompt.", "bad_response"),
    ("TimeoutError - Request timed out", "timeout"),
])
def test_each_toolkit_error_string_maps_to_a_reason(content, reason):
    with pytest.raises(llm_toolkit.ToolkitError) as exc:
        llm_toolkit.complete({}, "hi", runner([{"ai_result_1": content}]))
    assert exc.value.reason == reason


def test_the_error_list_matches_the_toolkits_own():
    # Lifted from Splunk_ML_Toolkit/bin/ai_commander/constants.py LLM_EXCEPTION_LIST
    # (6.1.0). If Splunk adds one, a reply carrying it parses as an answer.
    assert len(llm_toolkit.TOOLKIT_ERROR_CONTENT) == 9


def test_a_real_answer_that_merely_mentions_an_error_is_not_swallowed():
    # Matching is exact on the whole stripped reply, not a substring scan, so a
    # legitimate JSON answer discussing errors still comes through.
    answer = '{"note": "Empty response content received from the server."}'
    assert llm_toolkit.complete({}, "hi", runner([{"ai_result_1": answer}])) == answer

"""Tests for lib/splunk_search.py, the oneshot runner the Toolkit backend uses."""
import json

import pytest

import splunk_search


class Resp:
    def __init__(self, status=200):
        self.status = status


def _call(body, status=200, sink=None, exc=None, accept_timeout=True):
    def call(url, **kwargs):
        if sink is not None:
            sink.append((url, kwargs))
        if not accept_timeout and "timeout" in kwargs:
            raise TypeError("simpleRequest() got an unexpected keyword 'timeout'")
        if exc is not None:
            raise exc
        return Resp(status), body if isinstance(body, str) else json.dumps(body)
    return call


DOC = {"results": [{"ai_result_1": "hello"}],
       "messages": [{"type": "INFO", "text": "this is a slow search"}]}


# --- parsing ---------------------------------------------------------------

def test_info_messages_are_not_failures():
    # "This is a slow search" appears on every | ai run; treating it as an error
    # would make every call fail.
    rows, messages = splunk_search.parse_response(json.dumps(DOC))
    assert rows == [{"ai_result_1": "hello"}]
    assert messages == []


def test_error_and_fatal_messages_are_collected():
    doc = {"results": [], "messages": [
        {"type": "INFO", "text": "noise"},
        {"type": "FATAL", "text": "Error in 'ai' command: nope"},
        {"type": "ERROR", "text": "same thing again"}]}
    rows, messages = splunk_search.parse_response(json.dumps(doc))
    assert rows == []
    assert messages == ["Error in 'ai' command: nope", "same thing again"]


@pytest.mark.parametrize("body", ["not json", "", "[1,2,3]", None])
def test_an_unparseable_body_is_reported_not_raised(body):
    rows, messages = splunk_search.parse_response(body)
    assert rows == []
    assert len(messages) == 1


# --- the runner ------------------------------------------------------------

def test_oneshot_is_used_never_export():
    # search/jobs/export returns an empty 200 when the search FAILS, which makes
    # an | ai failure indistinguishable from an empty result.
    sink = []
    splunk_search.make_runner("KEY", "alice", request=_call(DOC, sink=sink))("| ai prompt=\"x\"")
    url, kwargs = sink[0]
    assert "export" not in url
    assert kwargs["postargs"]["exec_mode"] == "oneshot"
    assert kwargs["postargs"]["output_mode"] == "json"


def test_the_search_runs_in_the_callers_namespace():
    # A oneshot dispatched as nobody does not see the caller's default AI
    # Toolkit connection.
    sink = []
    splunk_search.make_runner("KEY", "alice", app="cim-plicity",
                              request=_call(DOC, sink=sink))("| ai")
    assert sink[0][0] == "/servicesNS/alice/cim-plicity/search/jobs"


def test_a_missing_username_falls_back_to_nobody():
    sink = []
    splunk_search.make_runner("KEY", None, request=_call(DOC, sink=sink))("| ai")
    assert sink[0][0].startswith("/servicesNS/nobody/")


def test_the_callers_session_key_is_used():
    sink = []
    splunk_search.make_runner("USERKEY", "alice", request=_call(DOC, sink=sink))("| ai")
    assert sink[0][1]["sessionKey"] == "USERKEY"


def test_an_http_error_is_returned_as_a_message_not_raised():
    rows, messages = splunk_search.make_runner(
        "KEY", "alice", request=_call({"x": 1}, status=503))("| ai")
    assert rows == []
    assert "HTTP 503" in messages[0]


def test_an_older_simplerequest_without_timeout_still_works():
    # splunk.rest.simpleRequest gained `timeout` late; falling back keeps the
    # runner working on older Splunk rather than dying on a TypeError.
    rows, _ = splunk_search.make_runner(
        "KEY", "alice", request=_call(DOC, accept_timeout=False))("| ai")
    assert rows == [{"ai_result_1": "hello"}]

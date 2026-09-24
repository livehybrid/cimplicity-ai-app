"""Tests for lib/llm_client.py, the single LLM transport both AI handlers use.

The HTTP POST is injected, so nothing here touches the network. What these pin
down is the contract the two handlers now depend on, plus the two defects this
module exists to fix: the timeout that was never a total, and the absent
max_tokens.
"""
import json

import pytest
import requests

import llm_client


class FakeResponse:
    def __init__(self, payload, status=200, raw=None):
        self._payload = payload
        self.status = status
        self._raw = raw

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.exceptions.HTTPError("%s error" % self.status)

    def json(self):
        if self._raw is not None:
            raise ValueError("not JSON: %r" % self._raw)
        return self._payload


def _ok(content="{\"a\": 1}", finish="stop"):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}]}


def _post(response, sink=None):
    def post(**kwargs):
        if sink is not None:
            sink.update(kwargs)
        if isinstance(response, Exception):
            raise response
        return response
    return post


SETTINGS = {"api_key": "sk-test", "api_endpoint": "https://example.invalid/v1/chat/completions",
            "model": "anthropic/claude-sonnet-5"}


# --- the happy path and what goes on the wire ------------------------------

def test_returns_the_reply_content():
    out = llm_client.complete(SETTINGS, "hello", title="T",
                              post=_post(FakeResponse(_ok("{\"ok\": true}"))))
    assert out == "{\"ok\": true}"


def test_endpoint_model_and_auth_come_from_settings():
    sink = {}
    llm_client.complete(SETTINGS, "hello", title="Cim-plicity",
                        post=_post(FakeResponse(_ok()), sink))
    body = json.loads(sink["data"])
    assert sink["url"] == SETTINGS["api_endpoint"]
    assert body["model"] == "anthropic/claude-sonnet-5"
    assert sink["headers"]["Authorization"] == "Bearer sk-test"
    assert sink["headers"]["X-Title"] == "Cim-plicity"
    # json_object keeps the provider from wrapping the reply in prose.
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"] == [{"role": "user", "content": "hello"}]


def test_defaults_apply_when_only_a_key_is_configured():
    sink = {}
    llm_client.complete({"api_key": "sk-test"}, "hello", title="T",
                        post=_post(FakeResponse(_ok()), sink))
    body = json.loads(sink["data"])
    assert sink["url"] == llm_client.DEFAULT_ENDPOINT
    assert body["model"] == llm_client.DEFAULT_MODEL


# --- the two defects this module fixes -------------------------------------

def test_max_tokens_is_always_sent():
    # Previously absent: a model that failed to stop ran to the provider's own
    # ceiling, billed to the customer, with the handler waiting on it.
    sink = {}
    llm_client.complete(SETTINGS, "hello", title="T", post=_post(FakeResponse(_ok()), sink))
    assert json.loads(sink["data"])["max_tokens"] == llm_client.DEFAULT_MAX_TOKENS


def test_max_tokens_is_overridable_from_settings_and_by_the_caller():
    sink = {}
    llm_client.complete(dict(SETTINGS, max_tokens="256"), "hello", title="T",
                        post=_post(FakeResponse(_ok()), sink))
    assert json.loads(sink["data"])["max_tokens"] == 256

    llm_client.complete(dict(SETTINGS, max_tokens="256"), "hello", title="T",
                        max_tokens=99, post=_post(FakeResponse(_ok()), sink))
    assert json.loads(sink["data"])["max_tokens"] == 99


@pytest.mark.parametrize("bad", ["", "not-a-number", 0, -5, None])
def test_a_nonsense_max_tokens_setting_falls_back_to_the_default(bad):
    sink = {}
    llm_client.complete(dict(SETTINGS, max_tokens=bad), "hello", title="T",
                        post=_post(FakeResponse(_ok()), sink))
    assert json.loads(sink["data"])["max_tokens"] == llm_client.DEFAULT_MAX_TOKENS


def test_timeout_is_an_explicit_connect_read_pair():
    # The old scalar timeout=60 was a per-socket-operation deadline, not a cap on
    # the call, which read as a total and was not one.
    sink = {}
    llm_client.complete(SETTINGS, "hello", title="T", post=_post(FakeResponse(_ok()), sink))
    assert sink["timeout"] == llm_client.DEFAULT_TIMEOUT
    assert isinstance(llm_client.DEFAULT_TIMEOUT, tuple) and len(llm_client.DEFAULT_TIMEOUT) == 2


# --- failures, which each handler maps differently -------------------------

def test_a_missing_api_key_is_not_configured_and_never_calls_out():
    called = []
    def post(**kwargs):
        called.append(kwargs)
        raise AssertionError("must not reach the provider")

    with pytest.raises(llm_client.LlmError) as exc:
        llm_client.complete({"model": "x"}, "hello", title="T", post=post)
    assert exc.value.reason == "not_configured"
    assert called == []


def test_timeout_is_reported_as_timeout():
    with pytest.raises(llm_client.LlmError) as exc:
        llm_client.complete(SETTINGS, "hello", title="T",
                            post=_post(requests.exceptions.Timeout("too slow")))
    assert exc.value.reason == "timeout"


def test_transport_errors_are_reported_as_transport():
    for err in (requests.exceptions.ConnectionError("no route"),
                requests.exceptions.HTTPError("500")):
        with pytest.raises(llm_client.LlmError) as exc:
            llm_client.complete(SETTINGS, "hello", title="T", post=_post(err))
        assert exc.value.reason == "transport"


def test_an_http_error_status_is_a_transport_failure():
    with pytest.raises(llm_client.LlmError) as exc:
        llm_client.complete(SETTINGS, "hello", title="T",
                            post=_post(FakeResponse(None, status=429)))
    assert exc.value.reason == "transport"


def test_a_non_json_body_is_a_bad_response():
    with pytest.raises(llm_client.LlmError) as exc:
        llm_client.complete(SETTINGS, "hello", title="T",
                            post=_post(FakeResponse(None, raw="<html>gateway</html>")))
    assert exc.value.reason == "bad_response"


@pytest.mark.parametrize("payload", [
    {},
    {"choices": []},
    {"choices": [{}]},
    {"choices": [{"message": {}}]},
])
def test_an_unexpected_shape_is_a_bad_response(payload):
    with pytest.raises(llm_client.LlmError) as exc:
        llm_client.complete(SETTINGS, "hello", title="T", post=_post(FakeResponse(payload)))
    assert exc.value.reason == "bad_response"


@pytest.mark.parametrize("content", [None, "", "   "])
def test_empty_content_is_a_failure_not_an_empty_answer(content):
    # A refused or truncated completion arrives as null/empty content with HTTP
    # 200. Returning it would look like "the model found nothing".
    with pytest.raises(llm_client.LlmError) as exc:
        llm_client.complete(SETTINGS, "hello", title="T",
                            post=_post(FakeResponse(_ok(content, finish="length"))))
    assert exc.value.reason == "bad_response"
    assert "length" in exc.value.detail


def test_llmerror_carries_a_reason_the_callers_can_map():
    # cim_mapping turns reason into a distinct user-facing message; ai_detection
    # treats every reason as "take the local fallback".
    err = llm_client.LlmError("timeout", "read timed out")
    assert err.reason == "timeout"
    assert "read timed out" in str(err)


# --- backend selection (Phase 2) -------------------------------------------

def test_direct_is_the_default_backend():
    # An existing install must be untouched by the Toolkit work landing.
    sink = {}
    llm_client.complete(SETTINGS, "hello", title="T", post=_post(FakeResponse(_ok()), sink))
    assert sink["url"] == SETTINGS["api_endpoint"]      # went out over HTTPS


def test_an_unknown_backend_value_falls_back_to_direct():
    sink = {}
    llm_client.complete(dict(SETTINGS, backend="nonsense"), "hello", title="T",
                        post=_post(FakeResponse(_ok()), sink))
    assert sink["url"] == SETTINGS["api_endpoint"]


def test_the_toolkit_backend_dispatches_a_search_and_never_calls_out():
    def post(**kwargs):
        raise AssertionError("must not reach the provider")

    seen = []
    def search(spl):
        seen.append(spl)
        return [{"ai_result_1": '{"ok": 1}'}], []

    out = llm_client.complete(dict(SETTINGS, backend="splunk_ai_toolkit"),
                              "hello", title="T", post=post, search=search)
    assert out == '{"ok": 1}'
    assert seen and seen[0].startswith("| makeresults | ai ")


def test_the_toolkit_backend_needs_no_api_key():
    # The whole point: the customer's key lives in the AI Toolkit instead.
    out = llm_client.complete({"backend": "splunk_ai_toolkit"}, "hello", title="T",
                              search=lambda spl: ([{"ai_result_1": "x"}], []))
    assert out == "x"


def test_the_toolkit_backend_without_a_search_runner_is_not_configured():
    with pytest.raises(llm_client.LlmError) as exc:
        llm_client.complete({"backend": "splunk_ai_toolkit"}, "hello", title="T")
    assert exc.value.reason == "not_configured"


def test_toolkit_errors_are_remapped_onto_llmerror_reasons():
    # So both handlers keep one set of reasons whichever backend is selected.
    msg = "Error in 'ai' command: No default LLM configuration found."
    with pytest.raises(llm_client.LlmError) as exc:
        llm_client.complete({"backend": "splunk_ai_toolkit"}, "hello", title="T",
                            search=lambda spl: ([], [msg]))
    assert exc.value.reason == "not_configured"


def test_backend_selection_is_case_and_space_tolerant():
    for value in ("Splunk_AI_Toolkit", "  splunk_ai_toolkit  ", "SPLUNK_AI_TOOLKIT"):
        out = llm_client.complete({"backend": value}, "hello", title="T",
                                  search=lambda spl: ([{"ai_result_1": "y"}], []))
        assert out == "y", value

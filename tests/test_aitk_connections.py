"""Tests for lib/aitk_connections.py, the AI Toolkit connection dropdown source.

The transport is injected, so these need no splunkd and no AI Toolkit. What they
pin down is that the dropdown only ever offers connections the caller can
actually use, and that it degrades to an empty list rather than breaking the
Configuration page.
"""
import json

import aitk_connections as ac


def req(status=200, body=None, boom=None, sink=None):
    def request(path):
        if sink is not None:
            sink.append(path)
        if boom is not None:
            raise boom
        return status, json.dumps(body if body is not None else [])
    return request


SHARED = {"name": "OpenAIDefault", "provider": "OpenAI", "model": "gpt-5-mini",
          "default_users": ["*"]}
OWNER_ONLY = {"name": "Private", "provider": "OpenAI", "model": "gpt-5",
              "default_users": []}
NAMED = {"name": "Mine", "provider": "OpenAI", "model": "gpt-4o",
         "default_users": ["will@livehybrid.com"]}


# --- only what the caller can actually use ---------------------------------

def test_a_globally_shared_connection_is_offered_to_everyone():
    assert ac.usable_by(SHARED, "anyone") is True


def test_an_owner_only_connection_is_offered_to_nobody():
    # default_users [] means owner-only. Offering it produces
    # "No configuration found for llm connection" at call time, which reads as
    # broken rather than as not-shared.
    assert ac.usable_by(OWNER_ONLY, "will@livehybrid.com") is False
    assert ac.usable_by(OWNER_ONLY, "admin") is False


def test_a_named_user_gets_their_own_connection_and_others_do_not():
    assert ac.usable_by(NAMED, "will@livehybrid.com") is True
    assert ac.usable_by(NAMED, "admin") is False


def test_a_malformed_default_users_is_treated_as_not_usable():
    for bad in (None, "*", {}, 0):
        assert ac.usable_by({"name": "x", "default_users": bad}, "admin") is False


def test_the_listing_is_filtered_per_caller():
    rows = [SHARED, OWNER_ONLY, NAMED]
    assert [e["name"] for e in ac.to_entries(rows, "will@livehybrid.com")] == \
        ["Mine", "OpenAIDefault"]
    assert [e["name"] for e in ac.to_entries(rows, "admin")] == ["OpenAIDefault"]


# --- the shape UCC expects --------------------------------------------------

def test_entries_use_the_eai_shape():
    e = ac.to_entries([SHARED], "admin")[0]
    assert set(e) == {"name", "content"}
    assert e["name"] == "OpenAIDefault"
    assert e["content"]["label"]


def test_the_label_distinguishes_connections_that_differ_only_by_model():
    a = dict(SHARED, name="One", model="gpt-4o")
    b = dict(SHARED, name="Two", model="gpt-5")
    labels = [e["content"]["label"] for e in ac.to_entries([a, b], "admin")]
    assert labels == ["One (OpenAI, gpt-4o)", "Two (OpenAI, gpt-5)"]


def test_a_connection_with_no_provider_or_model_still_gets_a_label():
    e = ac.to_entries([{"name": "Bare", "default_users": ["*"]}], "admin")[0]
    assert e["content"]["label"] == "Bare"


def test_duplicates_are_collapsed_and_the_list_is_sorted():
    rows = [dict(SHARED, name="b"), dict(SHARED, name="A"), dict(SHARED, name="b")]
    assert [e["name"] for e in ac.to_entries(rows, "admin")] == ["A", "b"]


# --- never break the Configuration page -------------------------------------

def test_no_toolkit_installed_is_an_empty_list_not_an_error():
    assert ac.list_connections(req(status=404), "admin") == []


def test_a_server_error_is_an_empty_list():
    assert ac.list_connections(req(status=503), "admin") == []


def test_a_raising_transport_is_an_empty_list():
    assert ac.list_connections(req(boom=RuntimeError("splunkd down")), "admin") == []


def test_an_unparseable_body_is_an_empty_list():
    def request(path):
        return 200, "<html>not json</html>"
    assert ac.list_connections(request, "admin") == []


def test_a_non_list_body_is_an_empty_list():
    assert ac.list_connections(req(body={"messages": []}), "admin") == []


def test_the_collection_is_read_in_the_nobody_namespace():
    # The AI Toolkit writes everything with namespace="app", so reading as the
    # caller returns nothing at all.
    sink = []
    ac.list_connections(req(body=[SHARED], sink=sink), "admin")
    assert sink == [ac.KV_PATH]
    assert "/servicesNS/nobody/Splunk_ML_Toolkit/" in ac.KV_PATH


def test_a_good_listing_comes_through():
    out = ac.list_connections(req(body=[SHARED, OWNER_ONLY]), "admin")
    assert [e["name"] for e in out] == ["OpenAIDefault"]

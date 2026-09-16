"""Static validation of CIMPlicity's MCP tool registration.

Unlike the Data Dictionary app there is no shipped
`tool_input_payload_signatures.json` here: the signatures live inline in the
`TOOLS` table in `ucc-app/bin/autoregister.py`, next to the code that ships
them. These tests parse that table and assert the invariants the Splunk MCP
Server enforces at load and exec time, so a rebuild cannot silently reintroduce
a regression.

The regression this exists to prevent (2026-07-31, commit d01b087):

    tools/call -> -32004  Tool 'cim-plicity_ai_detection' not found

The MCP Server prefixes every tool name on load
(`Tool._convert_from_new_schema`) with `_meta.name_prefix`, falling back to
`_meta.external_app_id`, unless the name already starts with that prefix, and
publishes THAT name from `tools/list`. But `tools/call` resolves the tool via
`get_enabled_tool()` -> `ToolEnabledCollection.get()`, a plain `_key` lookup in
the `mcp_tools_enabled` collection, which registration writes from the raw
`name`. When the two diverge, every call fails with the exact name `tools/list`
just handed the client.

`autoregister.py` imports `splunk.persistconn.application`, which only exists
inside splunkd, so the stubs below let the module import in plain pytest.
"""
from __future__ import annotations

import os
import sys
import types

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "ucc-app", "bin")

APP = "cim-plicity"
EXPECTED_PREFIX = "cim_plicity"
# Every tool the app ships. Keep in lockstep with default/tools.conf.
EXPECTED_TOOLS = {
    "cim_plicity_ping",
    "ai_detection",
    "pii_detection",
    "cim_mapping",
}


def _stub_splunk():
    """Make `import splunk.persistconn.application` succeed outside splunkd."""
    if "splunk.persistconn.application" in sys.modules:
        return
    splunk = sys.modules.setdefault("splunk", types.ModuleType("splunk"))
    persistconn = types.ModuleType("splunk.persistconn")
    application = types.ModuleType("splunk.persistconn.application")

    class PersistentServerConnectionApplication:  # pragma: no cover - stub
        pass

    application.PersistentServerConnectionApplication = PersistentServerConnectionApplication
    persistconn.application = application
    splunk.persistconn = persistconn
    sys.modules["splunk.persistconn"] = persistconn
    sys.modules["splunk.persistconn.application"] = application


@pytest.fixture(scope="module")
def autoregister():
    _stub_splunk()
    if BIN not in sys.path:
        sys.path.insert(0, BIN)
    import autoregister as mod  # noqa: PLC0415 - deliberately late, after stubbing

    return mod


def _tools(mod):
    """(name, method, endpoint, description, properties, required, body) tuples."""
    return list(mod.TOOLS)


def test_expected_tools_present(autoregister):
    names = {t[0] for t in _tools(autoregister)}
    assert names == EXPECTED_TOOLS, (
        f"TOOLS drifted from the shipped set: missing {EXPECTED_TOOLS - names}, "
        f"unexpected {names - EXPECTED_TOOLS}. Keep TOOLS in lockstep with "
        f"default/tools.conf."
    )


def test_name_prefix_is_underscored_not_the_app_id(autoregister):
    """`cim-plicity` carries a hyphen, so falling back to external_app_id would
    both stutter (`cim-plicity_cim_plicity_ping`) and put a hyphen in a tool
    name. NAME_PREFIX must be the underscored form."""
    assert autoregister.NAME_PREFIX == EXPECTED_PREFIX
    assert "-" not in autoregister.NAME_PREFIX
    assert autoregister.APP == APP


def test_advertised_name_matches_enabled_key(autoregister):
    """The name `tools/list` advertises must equal the `mcp_tools_enabled` _key
    that `tools/call` resolves by. This is the -32004 regression guard."""
    for name, *_ in _tools(autoregister):
        advertised = autoregister.mcp_name(name)
        assert advertised.startswith(f"{EXPECTED_PREFIX}_"), (
            f"{name}: advertised as {advertised!r}, which does not carry the "
            f"{EXPECTED_PREFIX!r} prefix"
        )
        # Round-tripping must be stable: prefixing an already-prefixed name is a no-op.
        assert autoregister.mcp_name(advertised) == advertised, (
            f"{name}: mcp_name is not idempotent ({advertised!r} -> "
            f"{autoregister.mcp_name(advertised)!r}); a double prefix would make the "
            f"tool uncallable"
        )


def test_mcp_name_mirrors_the_servers_rule(autoregister):
    """Mirror of Tool._convert_from_new_schema: prefix unless already prefixed."""
    assert autoregister.mcp_name("ai_detection") == "cim_plicity_ai_detection"
    assert autoregister.mcp_name("cim_plicity_ping") == "cim_plicity_ping"


def test_registration_doc_declares_name_prefix(autoregister):
    """Without `_meta.name_prefix` the server falls back to external_app_id and
    the advertised name diverges from what we enable."""
    for name, method, endpoint, desc, props, required, body in _tools(autoregister):
        doc = autoregister._doc(name, method, endpoint, desc, props, required, body)
        meta = doc.get("_meta", {})
        assert meta.get("name_prefix") == EXPECTED_PREFIX, (
            f"{name}: _meta.name_prefix should be {EXPECTED_PREFIX!r}, got "
            f"{meta.get('name_prefix')!r}"
        )
        assert meta.get("external_app_id") == APP, (
            f"{name}: _meta.external_app_id should be {APP!r} (immutable + required)"
        )
        assert doc.get("_key") == doc.get("tool_id"), (
            f"{name}: mcp_tools _key must be the tool_id"
        )


def test_endpoints_are_real_http_paths(autoregister):
    """`endpoint` must be the path from the restmap [script:...] `match`, not
    /services/<endpoint_name>, or the API executor 404s."""
    for name, method, endpoint, *_ in _tools(autoregister):
        assert endpoint.startswith("/services/"), (
            f"{name}: endpoint {endpoint!r} should be a real /services/ path"
        )
        assert method.upper() in {"GET", "POST"}, f"{name}: odd method {method!r}"


def test_input_schema_is_flat_no_refs(autoregister):
    """The MCP Server does not resolve $ref, so schemas must be self-contained."""
    import json  # noqa: PLC0415

    for name, method, endpoint, desc, props, required, body in _tools(autoregister):
        doc = autoregister._doc(name, method, endpoint, desc, props, required, body)
        blob = json.dumps(doc.get("inputSchema", {}))
        for token in ("$ref", "$defs", "definitions"):
            assert token not in blob, f"{name}: inputSchema uses {token}"


def test_every_tool_has_a_description(autoregister):
    """The description is what the model selects on. An empty one makes the tool
    effectively invisible."""
    for name, method, endpoint, desc, *_ in _tools(autoregister):
        assert desc and len(desc) > 40, (
            f"{name}: description is missing or too short to disambiguate ({desc!r})"
        )


if __name__ == "__main__":  # allow `python tests/test_tool_signatures.py`
    raise SystemExit(pytest.main([__file__, "-v"]))

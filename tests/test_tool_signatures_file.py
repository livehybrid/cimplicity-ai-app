"""The shipped Cloud signatures file must stay in lockstep with autoregister.TOOLS.

`appserver/static/tool_input_payload_signatures.json` is what the Splunk Cloud
synced-apps registrar reads to give each MCP tool its inputSchema and execution
body. `tools.conf` alone can express neither, so without this file Cloud
registers every tool with an empty inputSchema and no body, and a client sees a
parameterless tool it cannot call (confirmed on a live Cloud stack, MCP Server
2.0.0, 2026-09-16). The file is generated from `TOOLS` by
`scripts/gen_tool_signatures.py`; this guards against it drifting or going
missing.
"""
from __future__ import annotations

import json
import os
import sys
import types

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "ucc-app", "bin")
SIG = os.path.join(REPO, "ucc-app", "appserver", "static",
                   "tool_input_payload_signatures.json")


def _stub_splunk():
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
    import autoregister as mod  # noqa: PLC0415

    return mod


def _shipped():
    with open(SIG) as fh:
        return json.load(fh)


def test_signatures_file_exists():
    assert os.path.isfile(SIG), (
        "tool_input_payload_signatures.json missing; run "
        "scripts/gen_tool_signatures.py (Cloud needs it to expose tool schemas)"
    )


def test_signatures_match_autoregister_tools(autoregister):
    assert _shipped() == autoregister.build_tool_docs(), (
        "signatures file is out of date; re-run scripts/gen_tool_signatures.py"
    )


def test_post_tools_carry_schema_and_body():
    by_name = {d["name"]: d for d in _shipped()}
    for name, required in (("ai_detection", ["text"]),
                           ("pii_detection", ["text"]),
                           ("cim_mapping", ["extractedFields", "cimModel"])):
        doc = by_name[name]
        schema = doc["inputSchema"]
        assert schema["properties"], f"{name}: no inputSchema properties"
        assert schema["required"] == required, f"{name}: required mismatch"
        ex = doc["_meta"]["execution"]
        assert ex["method"] == "POST"
        assert ex.get("body"), f"{name}: no execution.body template"
        assert ex.get("headers", {}).get("Content-Type") == "application/json", (
            f"{name}: must force a JSON body"
        )


def test_ping_is_a_bare_get():
    ping = {d["name"]: d for d in _shipped()}["cim_plicity_ping"]
    assert ping["_meta"]["execution"]["method"] == "GET"
    assert ping["inputSchema"]["properties"] == {}

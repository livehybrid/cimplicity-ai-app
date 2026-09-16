#!/usr/bin/env python3
"""Generate appserver/static/tool_input_payload_signatures.json from autoregister.

On Splunk Cloud the synced-apps registrar reads this file to register each MCP
tool with its inputSchema and execution body. tools.conf alone cannot express
either, so without this file Cloud registers parameterless tools that clients
cannot call (see ucc-app-builder docs/MCP-AUTOREGISTER.md).

The file is generated, never hand-edited: bin/autoregister.py's TOOLS table is
the single source of truth. Re-run after changing TOOLS; the lockstep test
tests/test_tool_signatures.py fails if the shipped file drifts.

    python3 scripts/gen_tool_signatures.py
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BIN = os.path.join(_HERE, "..", "ucc-app", "bin")
sys.path.insert(0, _BIN)

import autoregister  # noqa: E402

OUT = os.path.join(_HERE, "..", "ucc-app", "appserver", "static",
                   "tool_input_payload_signatures.json")


def main():
    docs = autoregister.build_tool_docs()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(docs, fh, indent=2)
        fh.write("\n")
    print("wrote %d tool signatures -> %s" % (len(docs), os.path.relpath(OUT, os.path.join(_HERE, ".."))))


if __name__ == "__main__":
    main()

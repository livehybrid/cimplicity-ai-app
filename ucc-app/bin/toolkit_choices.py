"""Endpoint for the Configuration page's "AI Toolkit connection" dropdown.

Serves the Splunk EAI collection shape UCC's singleSelect expects from
`options.endpointUrl`:

    { "entry": [ { "name": "<connection>", "content": { "label": "..." } } ] }

The filtering and shaping live in lib/aitk_connections.py so they are testable
without splunkd; this only supplies the transport and the caller's identity.

Uses the CALLER'S session key, never the system one: AI Toolkit connections are
per-user (see lib/aitk_connections.py), and the AI Toolkit's own REST surface
refuses splunk-system-user outright.
"""
import json
import logging
import os
import re
import sys
from os.path import dirname

from splunk.persistconn.application import PersistentServerConnectionApplication

# The app's lib/ must be on sys.path BEFORE importing solnlib (bundled there).
ta_name = 'cim-plicity'
pattern = re.compile(r'[\\/]etc[\\/]apps[\\/][^\\/]+[\\/]bin[\\/]?$')
new_paths = [path for path in sys.path if not pattern.search(path) or ta_name in path]
new_paths.append(os.path.join(dirname(dirname(__file__)), "lib"))
new_paths.insert(0, os.path.sep.join([os.path.dirname(__file__), ta_name]))
sys.path = new_paths

import splunk.rest as rest

import aitk_connections

ADDON_NAME = 'cim-plicity'

logfile = os.sep.join([os.environ['SPLUNK_HOME'], 'var', 'log', 'splunk', f'{ADDON_NAME}.log'])
logging.basicConfig(filename=logfile, level=logging.INFO)


class ToolkitChoicesHandler(PersistentServerConnectionApplication):
    """GET -> the AI Toolkit connections this caller may select."""

    def __init__(self, _command_line=None, _command_arg=None):
        super(ToolkitChoicesHandler, self).__init__()

    @staticmethod
    def _requester(session_key):
        def request(path):
            resp, content = rest.simpleRequest(
                path, sessionKey=session_key, method="GET",
                getargs={"output_mode": "json", "count": "0"},
                raiseAllErrors=False)
            if isinstance(content, bytes):
                content = content.decode("utf-8", "replace")
            return int(getattr(resp, "status", 0) or 0), content
        return request

    def handle(self, in_string):
        try:
            request = json.loads(in_string) if in_string else {}
            session = request.get("session") or {}
            session_key = session.get("authtoken") or request.get("system_authtoken")
            username = session.get("user")
            if not session_key:
                # An empty list rather than a 401: the dropdown degrades to a
                # typeable box instead of erroring the Configuration page.
                logging.warning("No session key for the connection dropdown")
                return {"payload": json.dumps({"entry": []}), "status": 200}
            entries = aitk_connections.list_connections(
                self._requester(session_key), username)
            return {"payload": json.dumps({"entry": entries}), "status": 200}
        except Exception as exc:  # noqa: BLE001 - never 500 the Configuration page
            logging.error("Connection dropdown failed: %s", exc, exc_info=True)
            return {"payload": json.dumps({"entry": []}), "status": 200}

    def handleStream(self, handle, in_string):
        raise NotImplementedError("handleStream not implemented")

    def done(self):
        pass

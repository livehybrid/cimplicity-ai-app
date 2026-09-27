"""Serve the shipped prompt guidance to the Configuration page.

The Prompts tab's "Restore to default" button needs the shipped text, and the
only correct copy is lib/prompts.DEFAULT_GUIDANCE. Embedding it in the
JavaScript would make a fourth copy that silently drifts from the prompt the app
actually sends, so the button fetches it from here instead and is always current.

    GET /services/cim-plicity/prompt_defaults
    { "defaults": { "ai_detection": "...", "cim_mapping": "..." } }

Guidance only; the JSON output contract is appended by the app and is
deliberately not editable.
"""
import json
import logging
import os
import re
import sys
from os.path import dirname

from splunk.persistconn.application import PersistentServerConnectionApplication

ta_name = 'cim-plicity'
pattern = re.compile(r'[\\/]etc[\\/]apps[\\/][^\\/]+[\\/]bin[\\/]?$')
new_paths = [path for path in sys.path if not pattern.search(path) or ta_name in path]
new_paths.append(os.path.join(dirname(dirname(__file__)), "lib"))
new_paths.insert(0, os.path.sep.join([os.path.dirname(__file__), ta_name]))
sys.path = new_paths

import prompts

ADDON_NAME = 'cim-plicity'
logfile = os.sep.join([os.environ['SPLUNK_HOME'], 'var', 'log', 'splunk', f'{ADDON_NAME}.log'])
logging.basicConfig(filename=logfile, level=logging.INFO)


class PromptDefaultsHandler(PersistentServerConnectionApplication):
    """GET -> the shipped guidance, keyed by prompt name."""

    def __init__(self, _command_line=None, _command_arg=None):
        super(PromptDefaultsHandler, self).__init__()

    def handle(self, in_string):
        try:
            return {"payload": json.dumps({"defaults": dict(prompts.DEFAULT_GUIDANCE)}),
                    "status": 200}
        except Exception as exc:  # noqa: BLE001 - never 500 the Configuration page
            logging.error("prompt_defaults failed: %s", exc, exc_info=True)
            return {"payload": json.dumps({"defaults": {}}), "status": 200}

    def handleStream(self, handle, in_string):
        raise NotImplementedError("handleStream not implemented")

    def done(self):
        pass

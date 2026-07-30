"""Model-choice endpoint for the Configuration page's Model dropdown.

The AI Configuration tab's `model` field was free text, so a typo was only
discovered when an LLM call failed. UCC's singleSelect can populate itself
from a REST endpoint (options.endpointUrl) expecting a Splunk EAI collection:

    { "entry": [ { "name": "<model id>", "content": { "label": "..." } } ] }

This handler serves that shape. The field declares `dependencies:
["api_endpoint"]`, so UCC re-fetches with ?api_endpoint=<value> whenever the
LLM API Endpoint changes - OpenRouter endpoints list OpenRouter's catalogue,
OpenAI endpoints list OpenAI's, and anything else is probed as an
OpenAI-compatible /models API (see lib/model_catalog.py). `createSearchChoice`
on the field keeps arbitrary model ids typeable, so a model missing from the
catalogue is never a blocker - and a dropdown must never 500 the config page,
hence the blanket fallback handling.
"""
import json
import logging
import os
import re
import sys
import time
from os.path import dirname

from splunk.persistconn.application import PersistentServerConnectionApplication

# Setup paths - the app's lib/ must be on sys.path BEFORE importing solnlib
# (which is bundled there), or the import fails with ModuleNotFoundError.
ta_name = 'cim-plicity'
pattern = re.compile(r'[\\/]etc[\\/]apps[\\/][^\\/]+[\\/]bin[\\/]?$')
new_paths = [path for path in sys.path if not pattern.search(path) or ta_name in path]
new_paths.append(os.path.join(dirname(dirname(__file__)), "lib"))
new_paths.insert(0, os.path.sep.join([os.path.dirname(__file__), ta_name]))
sys.path = new_paths

from solnlib import conf_manager
import model_catalog

ADDON_NAME = 'cim-plicity'

logfile = os.sep.join([os.environ['SPLUNK_HOME'], 'var', 'log', 'splunk', f'{ADDON_NAME}.log'])
logging.basicConfig(filename=logfile, level=logging.INFO)

# The persistent process outlives requests, so a small TTL cache keeps the
# config page snappy while the user tabs between fields.
_CACHE_TTL_SECONDS = 300
_cache = {}


class ModelChoicesHandler(PersistentServerConnectionApplication):
    """GET -> the EAI-shaped model catalogue for the `model` singleSelect."""

    def __init__(self, _command_line=None, _command_arg=None):
        super(PersistentServerConnectionApplication, self).__init__()

    def handle(self, in_string):
        try:
            request = json.loads(in_string) if in_string else {}
            api_endpoint = self._query_param(request, 'api_endpoint')
            stored = self._stored_settings(request.get('system_authtoken'))
            if not api_endpoint:
                api_endpoint = stored.get('api_endpoint')
            api_key = stored.get('api_key')

            cache_key = (api_endpoint or '', bool(api_key))
            cached = _cache.get(cache_key)
            if cached and time.time() - cached[0] < _CACHE_TTL_SECONDS:
                return self._reply(cached[1])

            models = model_catalog.fetch_models(api_endpoint, api_key)
            entries = model_catalog.eai_entries(models)
            _cache[cache_key] = (time.time(), entries)
            return self._reply(entries)
        except Exception:
            logging.exception("ai_model_choices failed; serving fallback list")
            fallback = model_catalog.fallback_models(model_catalog.PROVIDER_OPENROUTER)
            return self._reply(model_catalog.eai_entries(fallback))

    @staticmethod
    def _query_param(request, name):
        """persistconn delivers query params as a list of [key, value] pairs."""
        query = request.get('query') or []
        if isinstance(query, dict):
            return query.get(name)
        for pair in query:
            if isinstance(pair, (list, tuple)) and len(pair) == 2 and pair[0] == name:
                return pair[1]
        return None

    @staticmethod
    def _stored_settings(session_key):
        """Read the ai_configuration stanza (api_endpoint + decrypted api_key)."""
        if not session_key:
            return {}
        try:
            cfm = conf_manager.ConfManager(
                session_key,
                ADDON_NAME,
                realm=f"__REST_CREDENTIAL__#{ADDON_NAME}#configs/conf-cim-plicity_settings",
            )
            return cfm.get_conf("cim-plicity_settings").get("ai_configuration") or {}
        except Exception as e:
            logging.warning(f"ai_model_choices could not read settings: {e}")
            return {}

    @staticmethod
    def _reply(entries):
        return {
            'status': 200,
            'payload': json.dumps({'entry': entries}),
            'headers': {'Content-Type': 'application/json'},
        }

    def handleStream(self, handle, in_string):
        raise NotImplementedError("PersistentServerConnectionApplication.handleStream")

    def done(self):
        pass

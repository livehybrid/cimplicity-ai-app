# Copyright 2024 Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import re
import json
import requests
import logging
from os.path import dirname

from splunk.persistconn.application import PersistentServerConnectionApplication

# Setup paths — the app's lib/ must be on sys.path BEFORE importing solnlib
# (which is bundled there), or the import fails with ModuleNotFoundError.
ta_name = 'cim-plicity'
pattern = re.compile(r'[\\/]etc[\\/]apps[\\/][^\\/]+[\\/]bin[\\/]?$')
new_paths = [path for path in sys.path if not pattern.search(path) or ta_name in path]
new_paths.append(os.path.join(dirname(dirname(__file__)), "lib"))
new_paths.insert(0, os.path.sep.join([os.path.dirname(__file__), ta_name]))
sys.path = new_paths

# load_cim_models is a sibling module in bin/. persistconn does NOT put the
# script's own directory on sys.path, so add it explicitly or the import below
# fails with ModuleNotFoundError.
_bindir = os.path.dirname(os.path.abspath(__file__))
if _bindir not in sys.path:
    sys.path.insert(0, _bindir)

from solnlib import conf_manager
import ai_settings
import llm_client
import llm_response
import prompts
import splunk_search

ADDON_NAME = 'cim-plicity'

# llm_client.LlmError reasons -> the message the UI shows. Kept verbatim from the
# previous per-exception handlers so the front end sees no change.
_LLM_ERRORS = {
    "not_configured": "AI service is not configured.",
    "timeout": "Request to AI service timed out.",
    "transport": "Failed to communicate with AI service.",
    "bad_response": "Failed to parse LLM response",
}

# Setup logging (level set from the [logging] stanza per request, default INFO)
logfile = os.sep.join([os.environ['SPLUNK_HOME'], 'var', 'log', 'splunk', f'{ADDON_NAME}_cim_mapping.log'])
logging.basicConfig(filename=logfile, level=logging.INFO)

from load_cim_models import load_cim_fields

# Lazy-loaded so a failure cannot break module import and a handler recycle
# picks up a newly installed Splunk_SA_CIM without a full splunkd restart.
_CIM_FIELDS_CACHE = None


def _get_cim_fields():
    global _CIM_FIELDS_CACHE
    if _CIM_FIELDS_CACHE is None:
        _CIM_FIELDS_CACHE = load_cim_fields()
    return _CIM_FIELDS_CACHE


class CimMappingHandler(PersistentServerConnectionApplication):
    def __init__(self, _command_line, _command_arg):
        super(CimMappingHandler, self).__init__()

    def _read_ai_configuration(self):
        cfm = conf_manager.ConfManager(
            self.system_session_key,
            ADDON_NAME,
            realm=f"__REST_CREDENTIAL__#{ADDON_NAME}#configs/conf-cim-plicity_settings",
        )
        return cfm.get_conf("cim-plicity_settings").get("ai_configuration") or {}

    def get_ai_settings(self):
        """Return the ai_configuration stanza, retrying a transient empty read.

        cim_mapping has no local fallback, so an intermittently-empty api_key
        read on a Splunk Cloud SHC surfaces directly as "AI service is not
        configured". The retry rides through that transient miss
        (see lib/ai_settings.py).
        """
        return ai_settings.read_ai_configuration(self._read_ai_configuration)

    def apply_log_level(self):
        """Honour the [logging] log_level setting (default INFO)."""
        try:
            cfm = conf_manager.ConfManager(self.system_session_key, ADDON_NAME)
            level = cfm.get_conf("cim-plicity_settings").get("logging").get("log_level", "INFO")
            logging.getLogger().setLevel(getattr(logging, str(level).upper(), logging.INFO))
        except Exception:
            logging.getLogger().setLevel(logging.INFO)

    def _search_runner(self):
        """A oneshot-search runner for the AI Toolkit backend, or None.

        Returns None rather than raising when there is no user token: the direct
        backend does not need one, and llm_client only asks for it when the
        Toolkit backend is selected.
        """
        key = getattr(self, "user_session_key", None)
        if not key:
            return None
        try:
            return splunk_search.make_runner(key, getattr(self, "user_name", None),
                                             app=ADDON_NAME)
        except Exception as exc:  # noqa: BLE001 - absence is reported by llm_client
            logging.warning("Could not build a search runner: %s", exc)
            return None

    def _prompt_guidance(self, name):
        """The customer's prompt guidance from cim-plicity_prompts.conf, or None."""
        def read_stanza(stanza):
            cfm = conf_manager.ConfManager(self.system_session_key, ADDON_NAME)
            return cfm.get_conf("cim-plicity_prompts").get(stanza)
        return prompts.read_configured(read_stanza, name)

    def get_ai_secret(self):
        try:
            return self.get_ai_settings().get("api_key")
        except Exception as e:
            logging.error(f"Could not retrieve openrouter secret: {e}", exc_info=True)
            return None

    def call_openrouter(self, api_key, extracted_fields, cim_model):

        available_cim_fields = _get_cim_fields().get(cim_model, [])
        if not available_cim_fields:
            return {"error": f"Invalid CIM model specified: {cim_model}"}

        # The guidance half of this prompt is customer-editable
        # (default/cim-plicity_prompts.conf); the JSON output contract is not and
        # is appended by prompts.render. See lib/prompts.py.
        prompt = prompts.render(
            "cim_mapping",
            {"cim_model": cim_model,
             "available_cim_fields": json.dumps(available_cim_fields, indent=2),
             "extracted_fields": json.dumps(extracted_fields, indent=2)},
            configured=self._prompt_guidance("cim_mapping"))
        try:
            # The transport lives in lib/llm_client.py so both AI handlers share
            # one implementation (and one timeout/max_tokens policy).
            settings = dict(self.get_ai_settings() or {})
            settings["api_key"] = api_key
            logging.info(f"Requesting CIM mapping for model: {cim_model}")
            content = llm_client.complete(settings, prompt,
                                          title="Cim-plicity-CIM-Mapping",
                                          search=self._search_runner())

            # The prompt asks for a direct JSON array, but models wrap it: in a
            # markdown fence, under a single key (response_format=json_object
            # forbids a top-level array), or behind a line of preamble. Parsing
            # strictly here discarded correct mappings as unparseable.
            suggestions = llm_response.parse_json_array(content)
            if suggestions is None:
                logging.error("Failed to decode the direct response from the AI service")
                logging.debug(f"Undecodable content: {content}")
                return {"error": "Failed to parse LLM response"}
            return suggestions

        except llm_client.LlmError as e:
            # cim_mapping has no local fallback, so each failure becomes a
            # distinct user-facing message rather than a silent empty result.
            logging.error(f"CIM mapping LLM call failed ({e.reason}): {e.detail}")
            return {"error": _LLM_ERRORS.get(e.reason, "An unexpected error occurred.")}
        except Exception as e:
            logging.error(f"An unexpected error occurred during the LLM call: {e}")
            return {"error": "An unexpected error occurred."}

    def handle(self, in_string):
        logging.info("Starting CIM Mapping REST handler")
        try:
            inbound_payload = json.loads(in_string)
            self.system_session_key = inbound_payload.get('system_authtoken')
            session = inbound_payload.get('session') or {}
            self.user_name = session.get('user')
            # The AI Toolkit backend dispatches a search, and Toolkit connections
            # are per-user, so it needs the CALLER'S token, not the system one.
            self.user_session_key = session.get('authtoken')

            if not self.system_session_key:
                return {'payload': {'error': 'No session key provided'}, 'status': 401}

            self.apply_log_level()

            posted_data = json.loads(inbound_payload.get('payload', '{}'))
            extracted_fields = posted_data.get('extractedFields')
            cim_model = posted_data.get('cimModel')

            if not extracted_fields or not cim_model:
                return {'payload': {'error': 'Missing required parameters: extractedFields and cimModel'}, 'status': 400}

            api_key = self.get_ai_secret()
            if not api_key:
                return {'payload': {'error': 'AI service is not configured.'}, 'status': 500}

            results = self.call_openrouter(api_key, extracted_fields, cim_model)
            
            return {'payload': results, 'status': 200}

        except json.JSONDecodeError:
            logging.error("Invalid JSON received in request.")
            return {'payload': {'error': 'Invalid JSON in request payload'}, 'status': 400}
        except Exception as e:
            logging.error(f"Error during CIM mapping: {e}", exc_info=True)
            return {'payload': {'error': 'Internal error during CIM mapping'}, 'status': 500}

    def handleStream(self, handle, in_string):
        raise NotImplementedError("handleStream not implemented")

    def done(self):
        pass 
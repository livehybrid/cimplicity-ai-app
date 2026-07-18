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

from solnlib import conf_manager

ADDON_NAME = 'cim-plicity'

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

    def get_ai_settings(self):
        """Return the ai_configuration stanza as a dict ({} on failure)."""
        try:
            cfm = conf_manager.ConfManager(
                self.system_session_key,
                ADDON_NAME,
                realm=f"__REST_CREDENTIAL__#{ADDON_NAME}#configs/conf-cim-plicity_settings",
            )
            account_conf_file = cfm.get_conf("cim-plicity_settings")
            return account_conf_file.get("ai_configuration") or {}
        except Exception as e:
            logging.error(f"Could not read ai_configuration settings: {e}", exc_info=True)
            return {}

    def apply_log_level(self):
        """Honour the [logging] log_level setting (default INFO)."""
        try:
            cfm = conf_manager.ConfManager(self.system_session_key, ADDON_NAME)
            level = cfm.get_conf("cim-plicity_settings").get("logging").get("log_level", "INFO")
            logging.getLogger().setLevel(getattr(logging, str(level).upper(), logging.INFO))
        except Exception:
            logging.getLogger().setLevel(logging.INFO)

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

        prompt = f"""
        You are a Splunk CIM expert. Your task is to map a list of extracted fields from a log file to the standard fields of a specified Splunk Common Information Model (CIM).

        **CIM Data Model:**
        {cim_model}

        **Available CIM Fields for this model:**
        {json.dumps(available_cim_fields, indent=2)}

        **Extracted Fields from the log data:**
        {json.dumps(extracted_fields, indent=2)}

        **Your Instructions:**
        1.  Analyze the **Extracted Fields** provided. Pay attention to the field names and their sample values.
        2.  For each extracted field, find the best matching standard field from the **Available CIM Fields**.
        3.  You can map multiple extracted fields to the same CIM field if appropriate (e.g., 'ip' and 'client_ip' could both map to 'src_ip').
        4.  If an extracted field does not have a clear and logical mapping to any available CIM field, do not include it in your response.
        5.  For each successful mapping, provide a confidence score between 0.0 and 1.0, where 1.0 represents a perfect match. The score should reflect your certainty in the mapping based on field names and values.
        6.  Provide a brief "reasoning" for each mapping explaining why you chose it (e.g., "Field name 'user_ip' is a clear synonym for 'src_ip'").

        **Output Format:**
        Return your response as a single, valid JSON array of objects. Each object in the array represents a single mapping and must have the following structure:
        {{
          "field": "The name of the original extracted field",
          "cimField": "The name of the standard CIM field it maps to",
          "confidence": A float between 0.0 and 1.0,
          "reasoning": "A brief explanation for the mapping"
        }}

        Do not include any explanatory text outside of the final JSON array.
        """

        try:
            # Use the configured endpoint and model, matching ai_detection.py;
            # shipped defaults are the same OpenRouter URL and model.
            ai_conf = self.get_ai_settings()
            api_endpoint = ai_conf.get("api_endpoint") or "https://openrouter.ai/api/v1/chat/completions"
            model = ai_conf.get("model") or "google/gemini-2.0-flash-001"
            logging.info(f"Sending CIM mapping request to {api_endpoint} (model {model}) for CIM model: {cim_model}")
            response = requests.post(
                url=api_endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "X-Title": "Cim-plicity-CIM-Mapping",
                    "HTTP-Referer": "https://github.com/livehybrid/cimplicity-ai-onboarding",
                    "Content-Type": "application/json"
                },
                data=json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"}
                }),
                timeout=60
            )
            response.raise_for_status()

            # The response from the LLM might be a JSON object with a key, let's assume 'suggestions'
            content = response.json()['choices'][0]['message']['content']
            logging.info(f"Received CIM mapping response ({len(content)} chars)")
            
            # The prompt asks for a direct JSON array, but models can sometimes wrap it.
            # We will try to parse it directly, and if that fails, look for a key.
            try:
                suggestions = json.loads(content)
                if isinstance(suggestions, dict) and len(suggestions) == 1:
                    # If it's a dict with one key, assume the array is the value.
                    return list(suggestions.values())[0]
                return suggestions
            except (json.JSONDecodeError, TypeError):
                 logging.error("Failed to decode the direct response from the AI service")
                 logging.debug(f"Undecodable content: {content}")
                 return {"error": "Failed to parse LLM response"}

        except requests.exceptions.Timeout:
            logging.error("Request to OpenRouter timed out.")
            return {"error": "Request to AI service timed out."}
        except requests.exceptions.RequestException as e:
            logging.error(f"Error calling OpenRouter: {e}")
            return {"error": "Failed to communicate with AI service."}
        except Exception as e:
            logging.error(f"An unexpected error occurred during OpenRouter call: {e}")
            return {"error": "An unexpected error occurred."}

    def handle(self, in_string):
        logging.info("Starting CIM Mapping REST handler")
        try:
            inbound_payload = json.loads(in_string)
            self.system_session_key = inbound_payload.get('system_authtoken')
            
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
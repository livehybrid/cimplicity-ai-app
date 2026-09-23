# Copyright 2020 Splunk Inc.
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
from os.path import dirname

ta_name = 'cim-plicity'
pattern = re.compile(r'[\\/]etc[\\/]apps[\\/][^\\/]+[\\/]bin[\\/]?$')
new_paths = [path for path in sys.path if not pattern.search(path) or ta_name in path]
new_paths.append(os.path.join(dirname(dirname(__file__)), "lib"))
new_paths.insert(0, os.path.sep.join([os.path.dirname(__file__), ta_name]))
sys.path = new_paths

import logging
from solnlib import conf_manager
import ai_settings
import llm_client
import llm_response
import prompts
import splunk_search
import requests

from splunk.persistconn.application import PersistentServerConnectionApplication
import json

ADDON_NAME = 'cim-plicity'

# Level is set from the [logging] stanza per request, default INFO
logfile = os.sep.join([os.environ['SPLUNK_HOME'], 'var', 'log', 'splunk', f'{ADDON_NAME}.log'])
logging.basicConfig(filename=logfile,level=logging.INFO)


class AiDetection(PersistentServerConnectionApplication):
    def __init__(self, _command_line, _command_arg):
        super(PersistentServerConnectionApplication, self).__init__()

    def _read_ai_configuration(self):
        cfm = conf_manager.ConfManager(
            self.system_session_key,
            ADDON_NAME,
            realm=f"__REST_CREDENTIAL__#{ADDON_NAME}#configs/conf-cim-plicity_settings",
        )
        return cfm.get_conf("cim-plicity_settings").get("ai_configuration") or {}

    def get_ai_settings(self):
        """Return the ai_configuration stanza, retrying a transient empty read.

        The api_key is an encrypted field; on a Splunk Cloud SHC a call served by
        a lagging member reads it back empty, so a single read is not reliable
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

    def get_ai_secret(self):
        """
        Retrieves the OpenRouter API key from Splunk's credential store.
        """
        try:
            return self.get_ai_settings().get("api_key")
        except Exception as e:
            logging.error(f"Could not retrieve openrouter secret: {e}", exc_info=True)
            return None

    def _prompt_guidance(self, name):
        """The customer's prompt guidance from cim-plicity_prompts.conf, or None."""
        def read_stanza(stanza):
            cfm = conf_manager.ConfManager(self.system_session_key, ADDON_NAME)
            return cfm.get_conf("cim-plicity_prompts").get(stanza)
        return prompts.read_configured(read_stanza, name)

    def call_openrouter(self, api_key, sample_data, description=None):
        # The guidance half of this prompt is customer-editable
        # (default/cim-plicity_prompts.conf); the JSON output contract is not and
        # is appended by prompts.render. See lib/prompts.py.
        description_block = ""
        if description:
            description_block = ("Additional context provided by the user:\n%s"
                                 % description)
        prompt = prompts.render("ai_detection",
                                {"sample_data": sample_data,
                                 "description_block": description_block},
                                configured=self._prompt_guidance("ai_detection"))
        try:
            logging.info("Sending request to OpenRouter...")
            # The transport lives in lib/llm_client.py so both AI handlers share
            # one implementation (and one timeout/max_tokens policy).
            settings = dict(self.get_ai_settings() or {})
            settings["api_key"] = api_key
            content = llm_client.complete(settings, prompt, title="Cim-plicity",
                                          search=self._search_runner())
            # Models wrap the object in a markdown fence or a line of preamble
            # even when asked not to. Returning None here puts the caller on the
            # local fallback rather than raising.
            return llm_response.parse_json(content)
        except llm_client.LlmError as e:
            # Every failure mode is a fallback, not an error: ai_detection has a
            # local regex path and degrades to it rather than failing the request.
            logging.error(f"AI detection LLM call failed ({e.reason}): {e.detail}")
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred during the LLM call: {e}")
            return None

    def generate_combined_regex(self, fields, selected_field_names, sample_data):
        """
        Generate a single regex that captures selected fields and includes unselected fields as non-capture groups.
        """
        try:
            combined_pattern = ""
            field_positions = []
            for field in fields:
                if 'regex' in field:
                    try:
                        # Python re rejects PCRE (?<name>) groups: translate to
                        # (?P<name>) for positioning, leaving (?<= / (?<! lookbehinds
                        regex = re.sub(r'\(\?<(?![=!])', '(?P<', field['regex'])
                        match = re.search(regex, sample_data)
                        if match:
                            field_positions.append({
                                'field': field,
                                'start': match.start(),
                                'end': match.end()
                            })
                    except re.error as e:
                        logging.warning(f"Could not position field '{field.get('name')}' in sample: {e}")
                        continue
            if not field_positions:
                logging.warning("No fields could be positioned in the sample; skipping combined regex generation")
                return None
            field_positions.sort(key=lambda x: x['start'])
            last_end = 0
            for pos in field_positions:
                field = pos['field']
                field_name = field['name']
                if pos['start'] > last_end:
                    between_text = sample_data[last_end:pos['start']]
                    escaped_between = re.escape(between_text)
                    combined_pattern += escaped_between
                field_regex = field['regex']
                if '(?<' in field_regex:
                    pattern_match = re.search(r'\(\?<[^>]+>(.*?)\)', field_regex)
                    if pattern_match:
                        inner_pattern = pattern_match.group(1)
                        if field_name in selected_field_names:
                            combined_pattern += f"(?<{field_name}>{inner_pattern})"
                        else:
                            combined_pattern += f"(?:{inner_pattern})"
                else:
                    if field_name in selected_field_names:
                        combined_pattern += f"(?<{field_name}>{field_regex})"
                    else:
                        combined_pattern += f"(?:{field_regex})"
                last_end = pos['end']
            if last_end < len(sample_data):
                remaining_text = sample_data[last_end:]
                escaped_remaining = re.escape(remaining_text)
                combined_pattern += escaped_remaining
            return combined_pattern
        except Exception as e:
            logging.error(f"Error generating combined regex: {e}")
            return None

    def local_field_extraction(self, sample_data):
        logging.info("Performing local field extraction.")
        fields = []
        # Regex for common patterns
        patterns = {
            'timestamp': r'(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)',
            'ip_address': r'(?P<ip_address>(?:[0-9]{1,3}\.){3}[0-9]{1,3})',
            'log_level': r'(?P<log_level>INFO|WARN|WARNING|ERROR|DEBUG|FATAL|CRITICAL)',
            'email': r'(?P<email>[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        }

        for name, pattern in patterns.items():
            if re.search(pattern, sample_data):
                fields.append({'name': name, 'regex': pattern})

        # Key-value pairs
        # This regex is simplified; a more robust one might be needed for complex cases
        kv_matches = re.finditer(r'([a-zA-Z0-9_]+)=("([^"]*)"|([^\s,]+))', sample_data)
        for match in kv_matches:
            field_name = match.group(1)
            # Avoid adding duplicates from the generic patterns above
            if not any(f['name'] == field_name for f in fields):
                # A specific regex for this key
                regex = f'(?P<{field_name}>{field_name}=(?:\\"([^\\"]*)\\"|([^\\s,]+)))'
                fields.append({'name': field_name, 'regex': regex})

        # Detect timestamp format
        time_format = "CURRENT_TIME"
        time_prefix = ""
        max_lookahead = "25"
        
        # Common timestamp patterns
        timestamp_patterns = [
            (r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', '%Y-%m-%dT%H:%M:%S'),  # ISO 8601
            (r'\w{3} \d{1,2} \d{2}:\d{2}:\d{2}', '%b %d %H:%M:%S'),  # Syslog
            (r'\d{1,2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}', '%d/%b/%Y:%H:%M:%S'),  # Apache
            (r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', '%Y-%m-%d %H:%M:%S'),  # Standard
        ]
        
        for pattern, format_str in timestamp_patterns:
            if re.search(pattern, sample_data):
                time_format = format_str
                break
        
        return {
                "sourcetype": "generic_single_line",
                "fields": fields,
                "combined_regex": None,  # Local fallback doesn't generate combined regex
                "time_format": time_format,
                "time_prefix": time_prefix,
                "max_timestamp_lookahead": max_lookahead,
                "source": "local_fallback"
            }

    def normalize_ai_response(self, results):
        """
        Normalize AI response to match expected frontend format.
        Handles different response structures from AI models.
        """
        if not results:
            return results
            
        normalized = {
            'sourcetype': results.get('sourcetype', 'custom_log'),
            'fields': [],
            'combined_regex': None,
            'time_format': 'CURRENT_TIME',
            'time_prefix': '',
            'max_timestamp_lookahead': '25',
            'source': results.get('source', 'ai_detection')
        }
        
        # Handle different field structures
        if 'fields' in results:
            normalized['fields'] = results['fields']
        elif 'field_extractions' in results:
            # Convert field_extractions to fields format
            normalized['fields'] = []
            for field_extraction in results['field_extractions']:
                normalized['fields'].append({
                    'name': field_extraction.get('field', 'unknown'),
                    'regex': field_extraction.get('regex', '')
                })
        
        # Handle combined regex
        if 'combined_regex' in results:
            normalized['combined_regex'] = results['combined_regex']
        elif 'combined_extraction' in results:
            normalized['combined_regex'] = results['combined_extraction']
        
        # Handle timestamp analysis: the three flat keys are independent (the
        # prompt returns them together), with nested timestamp_analysis as a
        # fallback for models that wrap them
        if 'time_format' in results:
            normalized['time_format'] = results['time_format']
        if 'time_prefix' in results:
            normalized['time_prefix'] = results['time_prefix']
        if 'max_timestamp_lookahead' in results:
            normalized['max_timestamp_lookahead'] = str(results['max_timestamp_lookahead'])
        if 'timestamp_analysis' in results:
            timestamp_analysis = results['timestamp_analysis']
            if 'time_format' not in results:
                normalized['time_format'] = timestamp_analysis.get('TIME_FORMAT', 'CURRENT_TIME')
            if 'time_prefix' not in results:
                normalized['time_prefix'] = timestamp_analysis.get('TIME_PREFIX', '')
            if 'max_timestamp_lookahead' not in results:
                normalized['max_timestamp_lookahead'] = str(timestamp_analysis.get('MAX_TIMESTAMP_LOOKAHEAD', '25'))

        return normalized

    # Handle a syncronous from splunkd.
    def handle(self, in_string):
        """
        Called for a simple synchronous request.
        @param in_string: request data passed in
        @rtype: string or dict
        @return: String to return in response.  If a dict was passed in,
                 it will automatically be JSON encoded before being returned.
        """
        logging.info("Starting AI detection rest handler")
        try:
            inbound_payload = json.loads(in_string)
        except Exception as e:
            logging.error(f"Malformed input: {e}")
            return {'payload': {'error': 'Malformed input, must be valid JSON.'}, 'status': 400}
        self.system_session_key = inbound_payload.get('system_authtoken')
        if not self.system_session_key:
            logging.error("No session key provided")
            return {'payload': {'error': 'No session key provided'}, 'status': 401}
        session = inbound_payload.get('session') or {}
        self.user_name = session.get('user')
        # The AI Toolkit backend dispatches a search, and Toolkit connections are
        # per-user, so it needs the CALLER'S token rather than the system one.
        self.user_session_key = session.get('authtoken')
        self.apply_log_level()
        try:
            posted_data = json.loads(inbound_payload.get('payload', '{}'))
        except Exception as e:
            logging.error(f"Malformed payload: {e}")
            return {'payload': {'error': 'Malformed payload, must be valid JSON.'}, 'status': 400}
        try:
            sample_data = posted_data.get('text')
            description = posted_data.get('description', None)
            selected_fields = posted_data.get('selected_fields', None)
            if not sample_data:
                return {'payload': {'error': 'No text provided for AI detection'}, 'status': 400}
            api_key = self.get_ai_secret()
            results = None
            if api_key:
                logging.info("Using OpenRouter for AI detection.")
                results = self.call_openrouter(api_key, sample_data, description)
            else:
                logging.warning("No OpenRouter API key; proceeding with local fallback.")
            if not results:
                logging.info("OpenRouter failed or was skipped. Using local fallback.")
                results = self.local_field_extraction(sample_data)
            # --- Ensure all fields have a valid name ---
            if results and 'fields' in results:
                for idx, field in enumerate(results['fields']):
                    name = field.get('name')
                    if not name or not isinstance(name, str) or not name.strip():
                        # Try to extract name from regex (named group)
                        regex = field.get('regex', '')
                        match = re.search(r'\(\?P?<([a-zA-Z0-9_]+)>', regex)
                        if match:
                            field['name'] = match.group(1)
                        else:
                            field['name'] = f'field_{idx+1}'
            # --- End ensure field names ---
            # Normalize the results to match expected frontend format
            results = self.normalize_ai_response(results)
            
            if selected_fields and results and 'fields' in results:
                combined_regex = self.generate_combined_regex(results['fields'], selected_fields, sample_data)
                if combined_regex:
                    results['combined_regex'] = combined_regex
                    results['selected_fields'] = selected_fields
            return {'payload': results, 'status': 200}
        except Exception as e:
            logging.error(f"Error during AI detection: {e}", exc_info=True)
            return {'payload': {'error': 'Internal error during AI detection'}, 'status': 500}

    def handleStream(self, handle, in_string):
        """
        For future use
        """
        raise NotImplementedError(
            "PersistentServerConnectionApplication.handleStream")

    def done(self):
        """
        Virtual method which can be optionally overridden to receive a
        callback after the request completes.
        """
        pass

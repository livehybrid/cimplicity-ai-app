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
from splunktaucclib.splunk_aoblib.setup_util import Setup_Util
from solnlib import conf_manager
from base64 import b64encode
import splunk.entity
import splunk.Intersplunk
import splunklib.client as client
import splunklib.results as results
import requests

from splunk.persistconn.application import PersistentServerConnectionApplication
import json

ADDON_NAME = 'cim-plicity'

logfile = os.sep.join([os.environ['SPLUNK_HOME'], 'var', 'log', 'splunk', f'{ADDON_NAME}.log'])
logging.basicConfig(filename=logfile,level=logging.DEBUG)


class AiDetection(PersistentServerConnectionApplication):
    def __init__(self, _command_line, _command_arg):
        super(PersistentServerConnectionApplication, self).__init__()
        self.service = None

    def get_ai_secret(self):
        """
        Retrieves the OpenRouter API key from Splunk's credential store.
        """
        try:
            cfm = conf_manager.ConfManager(
                self.system_session_key,
                ADDON_NAME,
                realm=f"__REST_CREDENTIAL__#{ADDON_NAME}#configs/conf-cim-plicity_settings",
            )
            account_conf_file = cfm.get_conf("cim-plicity_settings")
            logging.info(f"Account conf file: {account_conf_file}")
            return account_conf_file.get("ai_configuration").get("api_key")

        except Exception as e:
            logging.error(f"Could not retrieve openrouter secret: {e}", exc_info=True)
            return None

    def call_openrouter(self, api_key, sample_data, description=None):
        base_prompt = f"""
        You are a Splunk expert tasked with analyzing a log sample to suggest field extractions.
        The log sample is:
        ---
        {sample_data}
        ---"""
        if description:
            base_prompt += f"""

        Additional context provided by the user:
        {description}
        """
        prompt = base_prompt + """
        Your instructions are:
        1.  Suggest an appropriate Splunk sourcetype for this data (e.g., 'json', 'json_no_timestamp', 'syslog', 'custom_log') or something appropriate to what you think the data is.
        2.  Identify key fields to be extracted from the log sample.
        3.  For each field, provide a robust PCRE-based regex pattern that can be used for extraction in Splunk (props.conf). The regex should use named capture groups (e.g., '(?<field_name>...)') and the regex must extract data based on the entire log line and only once!
        4.  In addition, provide a single regex pattern that can be used to extract all the fields from the log line in one go.
        5.  Analyze the log data for timestamp patterns and provide:
           - TIME_FORMAT: The Python datetime format string (e.g., '%Y-%m-%dT%H:%M:%S', '%b %d %H:%M:%S', '%d/%b/%Y:%H:%M:%S %z')
           - TIME_PREFIX: Any prefix that appears before the timestamp (e.g., '[', '(', or empty string)
           - MAX_TIMESTAMP_LOOKAHEAD: Maximum characters to look ahead for timestamp (default 25, increase if needed for complex formats)
        
        Return your response as a single, valid JSON object with the following EXACT structure:
        {
          "sourcetype": "string",
          "fields": [
            {
              "name": "field_name",
              "regex": "regex_pattern_with_named_groups"
            }
          ],
          "combined_regex": "single_regex_to_extract_all_fields",
          "time_format": "python_datetime_format_string",
          "time_prefix": "prefix_before_timestamp_or_empty",
          "max_timestamp_lookahead": "number_as_string"
        }
        
        Do not include any explanatory text outside of the JSON object.
        """
        try:
            logging.info("Sending request to OpenRouter...")
            logging.info(f"API key: {api_key}")
            # Fetch model from config (default to Claude 3.5 Sonnet)
            try:
                cfm = conf_manager.ConfManager(
                    self.system_session_key,
                    ADDON_NAME,
                    realm=f"__REST_CREDENTIAL__#{ADDON_NAME}#configs/conf-cim-plicity_settings",
                )
                account_conf_file = cfm.get_conf("cim-plicity_settings")
                logging.info(f"Account conf file: {account_conf_file}")
                model = account_conf_file.get("ai_configuration").get("model")
            except:
                model = 'anthropic/claude-3-5-sonnet-20241022'
            logging.info(f"Using model: {model}")

            response = requests.post(
                url=account_conf_file.get("ai_configuration").get("api_endpoint"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "X-Title": "Cim-plicity",
                    "HTTP-Referer": "https://github.com/livehybrid/cimplicity-ai-onboarding",
                    "Content-Type": "application/json"
                },
                data=json.dumps({
                    "model": model,  # Use the fetched model
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"}
                }),
                timeout=60
            )
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            logging.info(f"Content: {json.dumps(content, indent=4)}")
            logging.info("Received successful response from OpenRouter.")
            return json.loads(content)
        except requests.exceptions.Timeout:
            logging.error("Request to OpenRouter timed out.")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Error calling OpenRouter: {e}")
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred during OpenRouter call: {e}")
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
                        regex = field['regex']
                        match = re.search(regex, sample_data)
                        if match:
                            field_positions.append({
                                'field': field,
                                'start': match.start(),
                                'end': match.end()
                            })
                    except:
                        continue
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
        
        # Handle timestamp analysis
        if 'time_format' in results:
            normalized['time_format'] = results['time_format']
        elif 'time_prefix' in results:
            normalized['time_prefix'] = results['time_prefix']
        elif 'max_timestamp_lookahead' in results:
            normalized['max_timestamp_lookahead'] = str(results['max_timestamp_lookahead'])
        elif 'timestamp_analysis' in results:
            timestamp_analysis = results['timestamp_analysis']
            normalized['time_format'] = timestamp_analysis.get('TIME_FORMAT', 'CURRENT_TIME')
            normalized['time_prefix'] = timestamp_analysis.get('TIME_PREFIX', '')
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
        inbound_payload = json.loads(in_string)
        self.system_session_key = inbound_payload['system_authtoken']
        self.user_name = inbound_payload['session']['user']
        try:
            self.service = client.connect(token=self.system_session_key, owner="nobody", app=ta_name)
        except Exception as e:
            logging.error(f"Failed to connect to Splunk service: {e}")
            return {"payload": {"error": "Failed to connect to Splunk service"}, "status": 500}
        try:
            posted_data = json.loads(inbound_payload['payload'])
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
        except KeyError:
            logging.error("Request payload must contain a 'text' field.")
            return {'payload': {'error': "Request payload must contain a 'text' field."}, 'status': 400}
        except Exception as e:
            logging.error(f"Error during AI detection: {e}", exc_info=True)
            return {'payload': {'error': str(e)}, 'status': 500}

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

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

import splunk.entity
import splunk.Intersplunk
import splunklib.client as client
import splunklib.results as results
from splunk.persistconn.application import PersistentServerConnectionApplication
from solnlib import conf_manager

# Setup paths
ta_name = 'cim-plicity'
pattern = re.compile(r'[\\/]etc[\\/]apps[\\/][^\\/]+[\\/]bin[\\/]?$')
new_paths = [path for path in sys.path if not pattern.search(path) or ta_name in path]
new_paths.append(os.path.join(dirname(dirname(__file__)), "lib"))
new_paths.insert(0, os.path.sep.join([os.path.dirname(__file__), ta_name]))
sys.path = new_paths

ADDON_NAME = 'cim-plicity'

# Setup logging
logfile = os.sep.join([os.environ['SPLUNK_HOME'], 'var', 'log', 'splunk', f'{ADDON_NAME}_cim_mapping.log'])
logging.basicConfig(filename=logfile, level=logging.DEBUG)

# Define CIM fields statically within the script
CIM_FIELDS = {
    "authentication": [
        {"name": "user", "description": "Username or user identifier"},
        {"name": "src_ip", "description": "Source IP address"},
        {"name": "dest_ip", "description": "Destination IP address"},
        {"name": "action", "description": "Authentication action (success, failure)"},
        {"name": "app", "description": "Application name"},
        {"name": "session_id", "description": "Session identifier"}
    ],
    "network_traffic": [
        {"name": "src_ip", "description": "Source IP address"},
        {"name": "dest_ip", "description": "Destination IP address"},
        {"name": "src_port", "description": "Source port number"},
        {"name": "dest_port", "description": "Destination port number"},
        {"name": "protocol", "description": "Network protocol"},
        {"name": "bytes_in", "description": "Bytes received"},
        {"name": "bytes_out", "description": "Bytes sent"}
    ],
    "web": [
        {"name": "clientip", "description": "Client IP address"},
        {"name": "uri_path", "description": "URI path requested"},
        {"name": "status", "description": "HTTP status code"},
        {"name": "method", "description": "HTTP method"},
        {"name": "user_agent", "description": "User agent string"},
        {"name": "referer", "description": "HTTP referer"}
    ]
}

class CimMappingHandler(PersistentServerConnectionApplication):
    def __init__(self, _command_line, _command_arg):
        super(CimMappingHandler, self).__init__()
        self.service = None

    def get_ai_secret(self):
        try:
            cfm = conf_manager.ConfManager(
                self.system_session_key,
                ADDON_NAME,
                realm=f"__REST_CREDENTIAL__#{ADDON_NAME}#configs/conf-cim-plicity_settings",
            )
            account_conf_file = cfm.get_conf("cim-plicity_settings")
            return account_conf_file.get("ai_configuration").get("api_key")
        except Exception as e:
            logging.error(f"Could not retrieve openrouter secret: {e}", exc_info=True)
            return None

    def call_openrouter(self, api_key, extracted_fields, cim_model):
        
        available_cim_fields = CIM_FIELDS.get(cim_model, [])
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
            logging.info(f"Sending CIM mapping request to OpenRouter for model: {cim_model}")
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "X-Title": "Cim-plicity-CIM-Mapping",
                    "HTTP-Referer": "https://github.com/livehybrid/cimplicity-ai-onboarding",
                    "Content-Type": "application/json"
                },
                data=json.dumps({
                    "model": "google/gemini-2.0-flash-001",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"}
                }),
                timeout=60
            )
            response.raise_for_status()

            # The response from the LLM might be a JSON object with a key, let's assume 'suggestions'
            content = response.json()['choices'][0]['message']['content']
            logging.info(f"Received from OpenRouter: {content}")
            
            # The prompt asks for a direct JSON array, but models can sometimes wrap it.
            # We will try to parse it directly, and if that fails, look for a key.
            try:
                suggestions = json.loads(content)
                if isinstance(suggestions, dict) and len(suggestions) == 1:
                    # If it's a dict with one key, assume the array is the value.
                    return list(suggestions.values())[0]
                return suggestions
            except (json.JSONDecodeError, TypeError):
                 logging.error(f"Failed to decode the direct response. Content: {content}")
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
            return {'payload': {'error': str(e)}, 'status': 500}

    def handleStream(self, handle, in_string):
        raise NotImplementedError("handleStream not implemented")

    def done(self):
        pass 
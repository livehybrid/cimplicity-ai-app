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
import logging
from typing import Any, Dict, Union
import hashlib


# Ensure the app's lib directory is at the front of sys.path
lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
bin_path = os.path.abspath(os.path.join(os.path.dirname(__file__)))
# Native/binary deps (regex, numpy) are installed by ucc-gen into
# lib/3rdparty/<platform> from globalConfig os-dependentLibraries, NOT lib/.
# UCC's generated import_declare_test.py is meant to add this but has a
# "39" == "3.9" version-string bug, so add it explicitly here.
thirdparty_path = os.path.join(lib_path, '3rdparty', 'linux_lib_py39')

if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

if bin_path not in sys.path:
    sys.path.insert(0, bin_path)

if os.path.isdir(thirdparty_path) and thirdparty_path not in sys.path:
    sys.path.insert(0, thirdparty_path)

from solnlib import conf_manager

from splunk.persistconn.application import PersistentServerConnectionApplication
import json

# Import the abstracted PII detection logic
from pii_detection_logic import PiiDetectionLogic

# Level is set from the [logging] stanza per request, default INFO
logfile = os.sep.join([os.environ['SPLUNK_HOME'], 'var', 'log', 'splunk', 'cim-plicity.log'])
logging.basicConfig(filename=logfile,level=logging.INFO)

ADDON_NAME = 'cim-plicity'

class PiiDetection(PersistentServerConnectionApplication):
    """
    PersistentServerConnectionApplication for PII detection using scrubadub.
    Uses abstracted PiiDetectionLogic for core functionality.
    """

    def __init__(self, _command_line: Any, _command_arg: Any) -> None:
        super(PersistentServerConnectionApplication, self).__init__()

    def get_pii_detection_data(self, search_string: str) -> None:
        """Placeholder for future implementation."""
        pass

    def apply_log_level(self):
        """Honour the [logging] log_level setting (default INFO)."""
        try:
            cfm = conf_manager.ConfManager(self.system_session_key, ADDON_NAME)
            level = cfm.get_conf("cim-plicity_settings").get("logging").get("log_level", "INFO")
            logging.getLogger().setLevel(getattr(logging, str(level).upper(), logging.INFO))
        except Exception:
            logging.getLogger().setLevel(logging.INFO)

    def get_detectors_list(self):
        cfm = conf_manager.ConfManager(
                self.system_session_key,
                ADDON_NAME,
                realm=f"__REST_CREDENTIAL__#{ADDON_NAME}#configs/conf-cim-plicity_settings",
        )
        account_conf_file = cfm.get_conf("cim-plicity_settings")
        selected_detectors = account_conf_file.get("ai_configuration").get("pii_detectors").split('|') if account_conf_file.get("ai_configuration").get("pii_detectors") else []
        if not selected_detectors:
            selected_detectors = [
                'CredentialDetector', 'CreditCardDetector', 'DriversLicenceDetector', 'EmailDetector',
                'en_GB.NationalInsuranceNumberDetector', 'PhoneDetector', 'PostalCodeDetector',
                'en_US.SocialSecurityNumberDetector', 'en_GB.TaxReferenceNumberDetector', 'TwitterDetector',
                'UrlDetector', 'VehicleLicencePlateDetector', 'DateOfBirthDetector', 'SkypeDetector',
                'TaggedEvaluationFilthDetector', 'TextBlobNameDetector', 'UserSuppliedFilthDetector',
                'IpAddressDetector'  # Add custom IP address detector
            ]
        return selected_detectors
    
    # Handle a syncronous from splunkd.
    def handle(self, in_string: str) -> Union[str, Dict[str, Any]]:
        """
        Called for a simple synchronous request.
        Args:
            in_string (str): request data passed in
        Returns:
            str or dict: String to return in response. If a dict is returned, it will be JSON encoded.
        """
        logging.info("Starting PII detection handler")
        # Input validation
        try:
            inbound_payload = json.loads(in_string)
        except Exception as e:
            logging.error(f"Malformed input: {e}")
            return {'payload': {'error': 'Malformed input, must be valid JSON.'}, 'status': 400}
        if not isinstance(inbound_payload, dict):
            logging.error("Input is not a dictionary.")
            return {'payload': {'error': 'Input must be a JSON object.'}, 'status': 400}
        self.system_session_key = inbound_payload.get('system_authtoken')
        if not self.system_session_key:
            logging.error("No session key provided")
            return {'payload': {'error': 'No session key provided'}, 'status': 401}
        self.apply_log_level()
        logging.info(f"Payload keys: {list(inbound_payload.keys())}")
        # Mask PII in logs: only log text length and hash
        posted_data = None
        text_to_analyze = ''
        try:
            posted_data = json.loads(inbound_payload.get('payload', '{}'))
            text_to_analyze = posted_data.get('text', '')
        except Exception as e:
            logging.error(f"Malformed payload: {e}")
            return {'payload': {'error': 'Malformed payload, must be valid JSON.'}, 'status': 400}
        if not text_to_analyze:
            logging.warning("No text provided for PII detection.")
            return {'payload': {'error': 'No text provided for PII detection'}, 'status': 400}
        text_hash = hashlib.sha256(text_to_analyze.encode('utf-8')).hexdigest()
        logging.info(f"Text to analyze: length={len(text_to_analyze)}, sha256={text_hash}")
        
        # Use the abstracted PII detection logic
        try:
            selected_detectors = self.get_detectors_list()
            logging.info(f"Selected detectors: {selected_detectors}")
            
            # Extract custom patterns from the request (patterns themselves are
            # user-supplied, so log only the count)
            custom_patterns = posted_data.get('custom_patterns', [])
            logging.info(f"Custom patterns supplied: {len(custom_patterns)}")
            
            # Create PII detection logic instance with selected detectors and custom patterns
            pii_logic = PiiDetectionLogic(selected_detectors, custom_patterns)
            
            # Perform PII detection using the abstracted logic
            results = pii_logic.detect_pii(text_to_analyze)
            
            if 'error' in results:
                logging.error(f"Error during PII analysis: {results['error']}", exc_info=True)
                return {'payload': {'error': results['error']}, 'status': 500}
            
            # Return the results in the expected format
            response_payload = {
                'pii_results': results['pii_results'],
                'suggestion': results['suggestion']
            }
            return {'payload': response_payload, 'status': 200}
            
        except Exception as e:
            logging.error(f"Error during PII analysis: {e}", exc_info=True)
            return {'payload': {'error': 'Internal error during PII detection'}, 'status': 500}

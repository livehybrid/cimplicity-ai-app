#!/usr/bin/env python3
"""
Core PII detection logic abstracted from Splunk dependencies.
This module contains the shared logic that can be tested independently.
"""

import os
import sys
import re
import json
import logging
from typing import Any, Dict, List, Optional, Union
import hashlib
import importlib

# Ensure the lib directory is at the front of sys.path
lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__)))
bin_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'bin'))

if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

if bin_path not in sys.path:
    sys.path.insert(0, bin_path)

# Import scrubadub and custom detector
import scrubadub
from scrubadub.detectors import CreditCardDetector, EmailDetector, UrlDetector

# Add import for custom IP detector
try:
    from ip_address_detector import IpAddressDetector
except ImportError:
    IpAddressDetector = None

# Module-level constant for entity type regex patterns
ENTITY_TYPE_PATTERNS = {
    'EMAIL_ADDRESS': r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    'IP_ADDRESS': r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',
    'PHONE_NUMBER': r'\d{3}[-.]?\d{3}[-.]?\d{4}',
    'CREDIT_CARD': r'\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}',
    'US_SSN': r'\d{3}[-.]?\d{2}[-.]?\d{4}',
    'DATE_TIME': r'[^\]\s]+',  # For timestamps, be more flexible
    'PERSON': r'[A-Za-z\s]+',  # For names
    'URL': r'https?://[^\s"\'<>]+',  # More precise URL pattern - only full URLs with protocol
}

# Pre-compile regexes for performance
KV_REGEX = re.compile(r'(\w+)=')
JSON_REGEX = re.compile(r'"(\w+)"\s*:\s*"')
APACHE_IP_REGEX = re.compile(r'^\d+\.\d+\.\d+\.\d+')

class PiiDetectionLogic:
    """
    Core PII detection logic that can be used independently of Splunk.
    """
    
    def __init__(self, selected_detectors=None, custom_patterns=None):
        """
        Initialize the PII detection logic with optional detector list and custom patterns.
        Args:
            selected_detectors (list): List of detector names to use, or None for defaults
            custom_patterns (list): List of custom pattern dictionaries with 'name', 'regex', 'type' keys
        """
        self.selected_detectors = selected_detectors or [
            'CredentialDetector', 'CreditCardDetector', 'DriversLicenceDetector', 'EmailDetector',
            'en_GB.NationalInsuranceNumberDetector', 'PhoneDetector', 'PostalCodeDetector',
            'en_US.SocialSecurityNumberDetector', 'en_GB.TaxReferenceNumberDetector', 'TwitterDetector',
            'UrlDetector', 'VehicleLicencePlateDetector', 'DateOfBirthDetector', 'SkypeDetector',
            'TaggedEvaluationFilthDetector', 'TextBlobNameDetector', 'UserSuppliedFilthDetector',
            'IpAddressDetector'  # Add custom IP address detector
        ]
        self.custom_patterns = custom_patterns or []
    
    def load_detectors(self):
        """
        Load and return the list of detector instances.
        Returns:
            list: List of detector instances
        """
        detectors = []
        for detector_name in self.selected_detectors:
            try:
                # Handle module-prefixed detectors (e.g., en_GB.NationalInsuranceNumberDetector)
                if detector_name == 'IpAddressDetector' and IpAddressDetector is not None:
                    detectors.append(IpAddressDetector())
                elif '.' in detector_name:
                    module_path, class_name = detector_name.rsplit('.', 1)
                    module = importlib.import_module(f'scrubadub.detectors.{module_path}')
                    detector_cls = getattr(module, class_name)
                    detectors.append(detector_cls())
                else:
                    detector_cls = getattr(scrubadub.detectors, detector_name)
                    detectors.append(detector_cls())
            except Exception as e:
                print(f"Could not load detector {detector_name}: {e}")
                logging.error(f"Could not load detector {detector_name}: {e}")
        
        if not detectors:
            # fallback: add a basic detector to avoid empty list error
            print("Warning: No detectors loaded successfully, using fallback EmailDetector")
            logging.warning("No detectors loaded successfully, using fallback EmailDetector")
            detectors.append(EmailDetector())
        
        print(f"Successfully loaded {len(detectors)} detectors")
        logging.info(f"Successfully loaded {len(detectors)} detectors")
        return detectors
    
    def detect_custom_patterns(self, text: str) -> List[Dict[str, Any]]:
        """
        Detect custom patterns in the text using regex.
        Args:
            text (str): Text to analyze
        Returns:
            List of detected custom patterns with position and metadata
        """
        results = []
        
        for pattern_info in self.custom_patterns:
            try:
                pattern_name = pattern_info.get('name', 'CUSTOM_PATTERN')
                regex_pattern = pattern_info.get('regex', '')
                
                if not regex_pattern:
                    continue
                
                # Compile the regex pattern
                compiled_pattern = re.compile(regex_pattern, re.IGNORECASE)
                
                # Find all matches
                for match in compiled_pattern.finditer(text):
                    results.append({
                        'type': pattern_name.upper(),
                        'text': match.group(),
                        'start': match.start(),
                        'end': match.end(),
                        'score': 0.9,  # High confidence for custom patterns
                        'detector': 'CustomPatternDetector',
                        'name': pattern_name
                    })
                    
            except re.error as e:
                print(f"Invalid regex pattern '{regex_pattern}': {e}")
                continue
            except Exception as e:
                print(f"Error processing custom pattern '{pattern_name}': {e}")
                continue
        
        return results
    
    def detect_pii(self, text_to_analyze: str) -> Dict[str, Any]:
        """
        Detect PII in the given text.
        Args:
            text_to_analyze (str): Text to analyze for PII
        Returns:
            Dict[str, Any]: PII detection results
        """
        try:
            detectors = self.load_detectors()
            
            scrubber = scrubadub.Scrubber(detector_list=detectors)
            filth_list = list(scrubber.iter_filth(text_to_analyze))
            filtered_results = [f for f in filth_list if len(f.text.strip()) >= 3]
            
            pii_results = []
            for f in filtered_results:
                # Generate regex pattern for this PII type
                regex_pattern = self.generate_regex_for_pii(f.text, f.detector_name)
                
                pii_results.append({
                    'type': f.detector_name,
                    'text': f.text,
                    'score': 1.0,
                    'start': f.beg,
                    'end': f.end,
                    'field': self.infer_field_name(text_to_analyze, f.beg, f.end, f.detector_name),
                    'examples': [],
                    'regex_pattern': regex_pattern
                })
            
            # Add custom pattern detection
            custom_results = self.detect_custom_patterns(text_to_analyze)
            for custom_result in custom_results:
                pii_results.append({
                    'type': custom_result['type'],
                    'text': custom_result['text'],
                    'score': custom_result['score'],
                    'start': custom_result['start'],
                    'end': custom_result['end'],
                    'field': self.infer_field_name(text_to_analyze, custom_result['start'], custom_result['end'], custom_result['type']),
                    'examples': [],
                    'detector': custom_result['detector'],
                    'name': custom_result['name'],
                    'regex_pattern': custom_result.get('regex_pattern', custom_result.get('regex', ''))
                })
            
            suggestion = "No PII detected."
            if pii_results:
                pii_types = sorted(list(set([res['type'] for res in pii_results])))
                suggestion = f"Detected PII types: {', '.join(pii_types)}. Recommended action: Review and mask sensitive data before indexing."
            
            return {
                'pii_results': pii_results,
                'suggestion': suggestion,
                'total_detected': len(pii_results)
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    def infer_field_name(self, text: str, start: int, end: int, entity_type: str) -> str:
        """
        Try to infer the field name for this PII based on its context in the text.
        Args:
            text (str): The full text being analyzed.
            start (int): Start index of the PII entity.
            end (int): End index of the PII entity.
            entity_type (str): The type of PII entity.
        Returns:
            str: Inferred field name or entity type as fallback.
        """
        # Get some context around the PII
        context_start = max(0, start - 50)
        context_end = min(len(text), end + 50)
        context = text[context_start:context_end]
        pii_text = text[start:end]
        
        # Try key-value format
        kv_match = KV_REGEX.search(context)
        if kv_match:
            return kv_match.group(1)
        
        # Try JSON format
        json_match = JSON_REGEX.search(context)
        if json_match:
            return json_match.group(1)
        
        # For Apache logs, infer based on position
        if APACHE_IP_REGEX.match(text.strip()):
            if start < 20:
                return 'clientip'
            elif '[' in context and ']' in context:
                return 'timestamp'
            elif '"' in context:
                return 'request'
        
        # Fallback: use entity type as field name
        return entity_type.lower()

    def generate_regex_for_pii(self, pii_text: str, detector_name: str) -> str:
        """
        Generate a regex pattern to match and redact PII of the same type.
        Args:
            pii_text (str): The detected PII text
            detector_name (str): The detector that found this PII
        Returns:
            str: Regex pattern to match similar PII
        """
        # Escape the specific PII text for exact matching
        escaped_text = re.escape(pii_text)
        
        # Generate patterns based on detector type
        if 'IpAddressDetector' in detector_name:
            return r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'
        elif 'EmailDetector' in detector_name:
            return r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        elif 'CreditCardDetector' in detector_name:
            return r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'
        elif 'PhoneDetector' in detector_name:
            return r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
        elif 'SocialSecurityNumberDetector' in detector_name:
            return r'\b\d{3}[-.]?\d{2}[-.]?\d{4}\b'
        elif 'UrlDetector' in detector_name:
            return r'\bhttps?://[^\s"\'<>]+\b'
        else:
            # For other types, use a pattern that matches the specific text
            # but allows for variations in spacing and formatting
            return escaped_text


def generate_sedcmd_regex(text: str, start: int, end: int, entity_type: str, pii_text: str) -> Dict[str, str]:
    """
    Generate a field-specific regex pattern for SEDCMD based on the PII location and context.
    Returns a dict with 'pattern' and 'replacement' for the SEDCMD rule.
    Args:
        text (str): The full text being analyzed.
        start (int): Start index of the PII entity.
        end (int): End index of the PII entity.
        entity_type (str): The type of PII entity.
        pii_text (str): The detected PII text.
    Returns:
        Dict[str, str]: Regex pattern and replacement for SEDCMD.
    """
    # Get some context around the PII
    context_start = max(0, start - 50)
    context_end = min(len(text), end + 50)
    context = text[context_start:context_end]
    
    # Try to detect key-value format (field=value)
    kv_match = KV_REGEX.search(context)
    if kv_match:
        field_name = kv_match.group(1)
        value_pattern = get_value_pattern_for_type(entity_type)
        return {
            'pattern': f'{field_name}=({value_pattern})',
            'replacement': f'{field_name}=[REDACTED_{entity_type.upper()}]'
        }
    
    # Try to detect JSON format ("field":"value")
    json_match = JSON_REGEX.search(context)
    if json_match:
        field_name = json_match.group(1)
        value_pattern = get_value_pattern_for_type(entity_type)
        return {
            'pattern': f'"{field_name}"\\s*:\\s*"({value_pattern})"',
            'replacement': f'"{field_name}":"[REDACTED_{entity_type.upper()}]"'
        }
    
    # Try to detect Apache log format (positional)
    if APACHE_IP_REGEX.match(text.strip()):
        # This looks like an Apache log
        if start < 20:  # Likely the client IP at the beginning
            value_pattern = get_value_pattern_for_type(entity_type)
            return {
                'pattern': f'^({value_pattern})',
                'replacement': f'[REDACTED_{entity_type.upper()}]'
            }
        elif '[' in context and ']' in context:  # Likely timestamp in brackets
            value_pattern = get_value_pattern_for_type(entity_type)
            return {
                'pattern': f'\\[({value_pattern})\\]',
                'replacement': f'[[REDACTED_{entity_type.upper()}]]'
            }
        elif '"' in context:  # Likely in the quoted request field
            value_pattern = get_value_pattern_for_type(entity_type)
            return {
                'pattern': f'"([^"]*{re.escape(pii_text)}[^"]*)"',
                'replacement': f'"[REDACTED_{entity_type.upper()}]"'
            }
    
    # Fallback: use type-specific pattern without field context
    value_pattern = get_value_pattern_for_type(entity_type)
    return {
        'pattern': value_pattern,
        'replacement': f'[REDACTED_{entity_type.upper()}]'
    }


def get_value_pattern_for_type(entity_type: str) -> str:
    """
    Get a regex pattern that matches values of the given PII type.
    Args:
        entity_type (str): The type of PII entity.
    Returns:
        str: Regex pattern for the entity type.
    """
    return ENTITY_TYPE_PATTERNS.get(entity_type, r'[^\s,="]+') 
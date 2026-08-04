#!/usr/bin/env python3
"""
Standalone PII detection functionality without Splunk dependencies.
This module provides PII detection capabilities that can be tested independently.
"""

import os
import sys
import re
import json
from typing import Any, Dict, List, Optional, Union
import hashlib
import importlib

# Ensure the app's lib directory is at the front of sys.path
lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
bin_path = os.path.abspath(os.path.join(os.path.dirname(__file__)))

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

class PiiDetectionTester:
    """
    Standalone tester for PII detection functionality without requiring Splunk connection.
    """
    
    def __init__(self, selected_detectors=None):
        """
        Initialize the tester with optional detector list.
        Args:
            selected_detectors (list): List of detector names to use, or None for defaults
        """
        self.selected_detectors = selected_detectors or [
            'CredentialDetector', 'CreditCardDetector', 'DriversLicenceDetector', 'EmailDetector',
            'en_GB.NationalInsuranceNumberDetector', 'PhoneDetector', 'PostalCodeDetector',
            'en_US.SocialSecurityNumberDetector', 'en_GB.TaxReferenceNumberDetector', 'TwitterDetector',
            'UrlDetector', 'VehicleLicencePlateDetector', 'DateOfBirthDetector', 'SkypeDetector',
            'TaggedEvaluationFilthDetector', 'TextBlobNameDetector', 'UserSuppliedFilthDetector',
            'IpAddressDetector'  # Add custom IP address detector
        ]
    
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
        
        if not detectors:
            # fallback: add a basic detector to avoid empty list error
            detectors.append(EmailDetector())
        
        return detectors
    
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
            print(f"Loaded {len(detectors)} detectors: {[d.name for d in detectors]}")
            
            scrubber = scrubadub.Scrubber(detector_list=detectors)
            filth_list = list(scrubber.iter_filth(text_to_analyze))
            filtered_results = [f for f in filth_list if len(f.text.strip()) >= 3]
            
            pii_results = [{
                'type': f.detector_name,
                'text': f.text,
                'score': 1.0,
                'start': f.start,
                'end': f.end,
                'field': self.infer_field_name(text_to_analyze, f.start, f.end, f.detector_name),
                'examples': []
            } for f in filtered_results]
            
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
            print(f"Error during PII analysis: {e}")
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


def test_pii_detection_standalone():
    """
    Standalone function to test PII detection without Splunk connection.
    """
    # Test data with various PII types
    test_cases = [
        {
            'name': 'Email and IP',
            'text': 'User john.doe@example.com logged in from 192.168.1.100 at 2024-01-15 10:30:00'
        },
        {
            'name': 'Credit Card',
            'text': 'Payment processed: 4111-1111-1111-1111, amount: $99.99'
        },
        {
            'name': 'Phone Number',
            'text': 'Contact us at 555-123-4567 or support@company.com'
        },
        {
            'name': 'SSN',
            'text': 'Employee ID: 123-45-6789, Department: Engineering'
        },
        {
            'name': 'Mixed PII',
            'text': 'Customer: John Smith, Email: john.smith@email.com, Phone: (555) 123-4567, IP: 10.0.0.1'
        }
    ]
    
    # Test with default detectors
    tester = PiiDetectionTester()
    
    print("=== PII Detection Testing ===")
    print()
    
    for test_case in test_cases:
        print(f"Test: {test_case['name']}")
        print(f"Input: {test_case['text']}")
        
        results = tester.detect_pii(test_case['text'])
        
        if 'error' in results:
            print(f"ERROR: {results['error']}")
        else:
            print(f"Detected {results['total_detected']} PII items:")
            for item in results['pii_results']:
                print(f"  - {item['type']}: '{item['text']}' (position {item['start']}-{item['end']})")
            print(f"Suggestion: {results['suggestion']}")
        
        print("-" * 50)
        print()


def test_custom_ip_detector():
    """
    Test specifically the custom IP address detector.
    """
    print("=== Custom IP Detector Testing ===")
    
    # Test with only IP detector
    tester = PiiDetectionTester(['IpAddressDetector'])
    
    test_texts = [
        "Server 192.168.1.1 is responding",
        "Multiple IPs: 10.0.0.1, 172.16.0.1, and 8.8.8.8",
        "No IP addresses in this text",
        "Invalid IP: 999.999.999.999",
        "Valid IPs: 192.168.1.1, 10.0.0.1, 172.16.0.1"
    ]
    
    for i, text in enumerate(test_texts, 1):
        print(f"Test {i}: {text}")
        results = tester.detect_pii(text)
        
        if 'error' in results:
            print(f"ERROR: {results['error']}")
        else:
            print(f"Detected {results['total_detected']} IP addresses:")
            for item in results['pii_results']:
                print(f"  - {item['text']} (position {item['start']}-{item['end']})")
        
        print("-" * 30)


if __name__ == "__main__":
    """
    Main block for standalone testing.
    Usage: python pii_detection_standalone.py
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Test PII detection functionality')
    parser.add_argument('--test-all', action='store_true', help='Run all test cases')
    parser.add_argument('--test-ip', action='store_true', help='Test custom IP detector')
    parser.add_argument('--text', type=str, help='Test specific text')
    parser.add_argument('--detectors', type=str, help='Comma-separated list of detectors to test')
    
    args = parser.parse_args()
    
    if args.test_all:
        test_pii_detection_standalone()
    elif args.test_ip:
        test_custom_ip_detector()
    elif args.text:
        detectors = args.detectors.split(',') if args.detectors else None
        tester = PiiDetectionTester(detectors)
        results = tester.detect_pii(args.text)
        print(json.dumps(results, indent=2))
    else:
        print("Running default tests...")
        test_pii_detection_standalone()
        test_custom_ip_detector() 
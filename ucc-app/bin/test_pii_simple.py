#!/usr/bin/env python3
"""
Simple test script for PII detection logic without problematic dependencies.
This script tests the core logic without importing scrubadub or other heavy dependencies.
"""

import sys
import os
import json
from pathlib import Path

# Add the lib directory to the path
lib_path = Path(__file__).parent.parent / 'lib'
sys.path.insert(0, str(lib_path))

def test_pii_detection_logic():
    """Test the PII detection logic with mock data."""
    
    # Mock test data
    test_data = {
        "text": "My email is john.doe@example.com and my phone is 555-123-4567. My SSN is 123-45-6789.",
        "detectors": ["email", "phone", "ssn"],
        "expected_findings": 3
    }
    
    print("Testing PII detection logic...")
    print(f"Test text: {test_data['text']}")
    print(f"Expected detectors: {test_data['detectors']}")
    
    try:
        # Try to import the logic module
        from pii_detection_logic import detect_pii
        
        print("✓ Successfully imported pii_detection_logic")
        
        # Test the function with mock data
        result = detect_pii(
            text=test_data['text'],
            detectors=test_data['detectors'],
            sample_data=None
        )
        
        print(f"✓ Function executed successfully")
        print(f"Result type: {type(result)}")
        
        if isinstance(result, dict):
            print(f"Result keys: {list(result.keys())}")
            if 'findings' in result:
                print(f"Number of findings: {len(result['findings'])}")
                for i, finding in enumerate(result['findings']):
                    print(f"  Finding {i+1}: {finding}")
        
        return True
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False
    except Exception as e:
        print(f"✗ Execution error: {e}")
        return False

def test_ip_detector():
    """Test the custom IP address detector."""
    
    print("\nTesting IP address detector...")
    
    try:
        from ip_address_detector import IPAddressDetector
        
        detector = IPAddressDetector()
        test_text = "My server IP is 192.168.1.1 and external IP is 8.8.8.8"
        
        print(f"Test text: {test_text}")
        
        # Test the detector
        findings = list(detector.iter_filth(test_text))
        
        print(f"✓ IP detector executed successfully")
        print(f"Number of IP addresses found: {len(findings)}")
        
        for i, finding in enumerate(findings):
            print(f"  IP {i+1}: {finding.text} (position: {finding.beg}-{finding.end})")
        
        return True
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False
    except Exception as e:
        print(f"✗ Execution error: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("PII Detection Logic Test (Simple Version)")
    print("=" * 60)
    
    success_count = 0
    total_tests = 2
    
    # Test 1: Core PII detection logic
    if test_pii_detection_logic():
        success_count += 1
    
    # Test 2: IP address detector
    if test_ip_detector():
        success_count += 1
    
    print("\n" + "=" * 60)
    print(f"Test Results: {success_count}/{total_tests} tests passed")
    
    if success_count == total_tests:
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 
#!/usr/bin/env python3
"""
Simple test script for the abstracted PII detection logic.
This script demonstrates how to test PII detection without Splunk dependencies.
"""

import sys
import os

# Add the lib directory to the path so we can import our modules
lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

def test_pii_logic():
    """
    Test the abstracted PII detection logic.
    """
    print("🔍 Testing Abstracted PII Detection Logic")
    print("=" * 50)
    print()
    
    try:
        # Import the abstracted logic
        from pii_detection_logic import PiiDetectionLogic
        
        # Test 1: Basic functionality with default detectors
        print("1. Testing with default detectors...")
        logic = PiiDetectionLogic()
        
        test_text = "User john.doe@example.com logged in from 192.168.1.100"
        print(f"Input: {test_text}")
        
        results = logic.detect_pii(test_text)
        
        if 'error' in results:
            print(f"❌ Error: {results['error']}")
        else:
            print(f"✅ Detected {results['total_detected']} PII items:")
            for item in results['pii_results']:
                print(f"   - {item['type']}: '{item['text']}' (position {item['start']}-{item['end']})")
            print(f"💡 Suggestion: {results['suggestion']}")
        
        print()
        
        # Test 2: Custom IP detector only
        print("2. Testing with custom IP detector only...")
        ip_logic = PiiDetectionLogic(['IpAddressDetector'])
        
        ip_test_text = "Multiple IPs: 10.0.0.1, 172.16.0.1, and 8.8.8.8"
        print(f"Input: {ip_test_text}")
        
        ip_results = ip_logic.detect_pii(ip_test_text)
        
        if 'error' in ip_results:
            print(f"❌ Error: {ip_results['error']}")
        else:
            print(f"✅ Detected {ip_results['total_detected']} IP addresses:")
            for item in ip_results['pii_results']:
                print(f"   - {item['text']} (position {item['start']}-{item['end']})")
        
        print()
        
        # Test 3: Multiple detector types
        print("3. Testing with multiple detector types...")
        multi_logic = PiiDetectionLogic(['EmailDetector', 'IpAddressDetector', 'CreditCardDetector'])
        
        multi_test_text = "Customer: john@email.com, IP: 192.168.1.1, Card: 4111-1111-1111-1111"
        print(f"Input: {multi_test_text}")
        
        multi_results = multi_logic.detect_pii(multi_test_text)
        
        if 'error' in multi_results:
            print(f"❌ Error: {multi_results['error']}")
        else:
            print(f"✅ Detected {multi_results['total_detected']} PII items:")
            for item in multi_results['pii_results']:
                print(f"   - {item['type']}: '{item['text']}' (position {item['start']}-{item['end']})")
        
        print()
        print("🎉 Logic testing completed successfully!")
        
    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("This is expected if scrubadub is not installed in the local environment.")
        print("The logic is designed to work within the Splunk environment where dependencies are available.")
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")

if __name__ == "__main__":
    test_pii_logic() 
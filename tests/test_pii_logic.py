#!/usr/bin/env python3
"""Tests for the abstracted PII detection logic (lib/pii_detection_logic.py).

Exercises the real scrubadub detection path; skipped cleanly where scrubadub
is not installed (the packaged app ships scrubadub==2.0.1 in lib/).
"""
import pytest

pytest.importorskip("scrubadub")

from pii_detection_logic import PiiDetectionLogic


# The shipped default from default/cim-plicity_settings.conf pii_detectors.
# (The code-default list adds TextBlobNameDetector, which needs NLTK corpora
# and errors the whole scrub when they are absent, so it is not usable here.)
SETTINGS_DEFAULT_DETECTORS = [
    'CreditCardDetector', 'EmailDetector', 'UrlDetector', 'DateOfBirthDetector',
    'IpAddressDetector', 'en_US.SocialSecurityNumberDetector', 'PhoneDetector',
    'DriversLicenceDetector', 'PostalCodeDetector',
    'en_GB.NationalInsuranceNumberDetector', 'en_GB.TaxReferenceNumberDetector',
    'VehicleLicencePlateDetector',
]


def test_detects_email_and_ip_with_default_detectors():
    logic = PiiDetectionLogic(SETTINGS_DEFAULT_DETECTORS)
    text = "User john.doe@example.com logged in from 192.168.1.100"
    results = logic.detect_pii(text)
    assert 'error' not in results, results
    texts = {r['text'] for r in results['pii_results']}
    assert 'john.doe@example.com' in texts, texts
    assert '192.168.1.100' in texts, texts
    assert results['total_detected'] == len(results['pii_results']) >= 2
    assert results['suggestion'].startswith('Detected PII types')
    # every result carries position, inferred field and a redaction regex
    for r in results['pii_results']:
        assert text[r['start']:r['end']] == r['text']
        assert r['field']
        assert r['regex_pattern']


def test_custom_ip_detector_only():
    logic = PiiDetectionLogic(['IpAddressDetector'])
    results = logic.detect_pii("Multiple IPs: 10.0.0.1, 172.16.0.1, and 8.8.8.8")
    assert 'error' not in results, results
    assert {r['text'] for r in results['pii_results']} == {'10.0.0.1', '172.16.0.1', '8.8.8.8'}
    assert all(r['type'] == 'IpAddressDetector' for r in results['pii_results'])


def test_custom_patterns_supplement_detectors():
    logic = PiiDetectionLogic(
        ['EmailDetector'],
        custom_patterns=[{'name': 'ticket_id', 'regex': r'TKT-\d{5}'}])
    results = logic.detect_pii("Ref TKT-12345 raised by a.user@example.com")
    assert 'error' not in results, results
    custom = [r for r in results['pii_results'] if r['type'] == 'TICKET_ID']
    assert len(custom) == 1 and custom[0]['text'] == 'TKT-12345', results['pii_results']
    assert any(r['text'] == 'a.user@example.com' for r in results['pii_results'])


def test_invalid_custom_regex_is_skipped_not_fatal():
    logic = PiiDetectionLogic(
        ['EmailDetector'],
        custom_patterns=[{'name': 'broken', 'regex': r'([unclosed'}])
    results = logic.detect_pii("Contact a.user@example.com")
    assert 'error' not in results, results
    assert any(r['text'] == 'a.user@example.com' for r in results['pii_results'])
    assert not any(r['type'] == 'BROKEN' for r in results['pii_results'])


def test_no_pii_found_returns_empty_results():
    logic = PiiDetectionLogic(['EmailDetector'])
    results = logic.detect_pii("nothing sensitive here")
    assert 'error' not in results, results
    assert results['pii_results'] == []
    assert results['suggestion'] == 'No PII detected.'

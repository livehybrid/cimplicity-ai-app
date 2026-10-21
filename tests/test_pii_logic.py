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


# key=value text: scrubadub's own EmailDetector allows '=' in the local part
# and reports "user=alice@example.com", so a mask built from the span hides the
# key too. The expected spans below come from str.index on the test's own
# strings, never from the detector, and the mask is applied the way the UI's
# PIIDetection.jsx does it (substring on start/end), so a fix that trims .text
# but leaves .start behind still fails.
KV_CASES = [
    ("user=alice@example.com action=login", "alice@example.com",
     "user=[MASKED] action=login"),
    ("a=1&email=bob@example.co.uk status=ok", "bob@example.co.uk",
     "a=1&email=[MASKED] status=ok"),
    ("src=10.0.0.1 user=carol.smith+tag@example.org", "carol.smith+tag@example.org",
     "src=10.0.0.1 user=[MASKED]"),
]


@pytest.mark.parametrize("text,address,masked", KV_CASES)
def test_email_span_in_key_value_text_covers_the_address_only(text, address, masked):
    results = PiiDetectionLogic(SETTINGS_DEFAULT_DETECTORS).detect_pii(text)
    assert 'error' not in results, results
    emails = [r for r in results['pii_results'] if '@' in r['text']]
    assert len(emails) == 1, results['pii_results']
    want_start = text.index(address)
    assert (emails[0]['start'], emails[0]['end']) == (want_start, want_start + len(address)), emails
    assert emails[0]['text'] == address
    assert text[:emails[0]['start']] + "[MASKED]" + text[emails[0]['end']:] == masked


def test_email_in_free_text_is_unchanged():
    text = "Contact dave@example.com today"
    results = PiiDetectionLogic(['EmailDetector']).detect_pii(text)
    spans = [(r['start'], r['end']) for r in results['pii_results']]
    start = text.index("dave@")
    assert spans == [(start, start + len("dave@example.com"))]


# Field name: the key immediately preceding the value, never the first key=
# in the surrounding window. The expected names are written out by hand from
# each test string; the "wrong" key is placed where the old window search
# would find it first (earlier in the event, or after the value).
FIELD_CASES = [
    ('src=10.0.0.1 user="alice@example.com"', "alice@example.com", "user"),
    ("a=1&email=bob@example.co.uk status=ok", "bob@example.co.uk", "email"),
    ('{"src": "10.0.0.1", "user": "carol@example.org"}', "carol@example.org", "user"),
    # nothing immediately before the value: the type, not the later action= key
    ("login by dave@example.com action=login", "dave@example.com", "email"),
]


@pytest.mark.parametrize("text,address,field", FIELD_CASES)
def test_email_is_labelled_with_the_key_immediately_preceding_it(text, address, field):
    results = PiiDetectionLogic(['EmailDetector']).detect_pii(text)
    assert 'error' not in results, results
    start = text.index(address)
    hits = [r for r in results['pii_results'] if r['start'] == start]
    assert len(hits) == 1, results['pii_results']
    assert hits[0]['field'] == field, hits


def test_email_redaction_pattern_is_generic_not_the_literal_address():
    import re
    results = PiiDetectionLogic(['EmailDetector']).detect_pii("user=alice@example.com action=login")
    emails = [r for r in results['pii_results'] if '@' in r['text']]
    assert len(emails) == 1, results['pii_results']
    pattern = re.compile(emails[0]['regex_pattern'])
    # Addresses that are not in the input: a literal pattern matches none of them.
    for other in ("bob@example.co.uk", "Carol.Smith+tag@Example.ORG"):
        assert pattern.fullmatch(other), (emails[0]['regex_pattern'], other)
    # Used as a SEDCMD over key=value text, it leaves the key alone.
    assert pattern.sub("#", "user=zed@example.net action=login") == "user=# action=login"

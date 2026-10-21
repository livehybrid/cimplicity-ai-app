#!/usr/bin/env python3
"""bin/pii_detection_standalone.py (the dev script) must report the same email
span and field as the handler: the address only, labelled with its own key."""
import pytest

pytest.importorskip("scrubadub")

from pii_detection_standalone import PiiDetectionTester


def test_standalone_email_span_and_field_in_key_value_text():
    text = 'src=10.0.0.1 user=alice@example.com action=login'
    results = PiiDetectionTester(['EmailDetector']).detect_pii(text)
    assert 'error' not in results, results
    emails = [r for r in results['pii_results'] if '@' in r['text']]
    assert len(emails) == 1, results['pii_results']
    start = text.index('alice@example.com')
    assert (emails[0]['start'], emails[0]['end']) == (start, start + len('alice@example.com')), emails
    assert text[:emails[0]['start']] + '#' + text[emails[0]['end']:] == 'src=10.0.0.1 user=# action=login'
    assert emails[0]['field'] == 'user', emails


def test_standalone_fallback_detector_is_the_key_value_one():
    # No loadable detector: the script falls back to a single email detector.
    text = 'user=bob@example.org'
    results = PiiDetectionTester(['NoSuchDetector']).detect_pii(text)
    emails = [r for r in results['pii_results'] if '@' in r['text']]
    assert [(r['start'], r['end']) for r in emails] == [(len('user='), len(text))], results

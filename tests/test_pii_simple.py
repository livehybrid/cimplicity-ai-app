#!/usr/bin/env python3
"""Tests for the custom IP address detector and the SEDCMD helper functions
in lib/pii_detection_logic.py.

Both modules import scrubadub at module level, so these are skipped cleanly
where scrubadub is not installed (the packaged app ships it in lib/).
"""
import re

import pytest

pytest.importorskip("scrubadub")

from ip_address_detector import IpAddressDetector
from pii_detection_logic import generate_sedcmd_regex, get_value_pattern_for_type


def test_ip_detector_finds_all_ipv4():
    detector = IpAddressDetector()
    text = "My server IP is 192.168.1.1 and external IP is 8.8.8.8"
    findings = list(detector.iter_filth(text))
    assert [f.text for f in findings] == ['192.168.1.1', '8.8.8.8']
    for f in findings:
        # scrubadub Filth positions are beg/end (not start/end)
        assert text[f.beg:f.end] == f.text
        assert f.detector_name == 'IpAddressDetector'


def test_ip_detector_no_match_on_clean_text():
    detector = IpAddressDetector()
    assert list(detector.iter_filth("no addresses in this text")) == []


def test_get_value_pattern_known_and_fallback():
    assert get_value_pattern_for_type('IP_ADDRESS') == r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'
    # unknown types fall back to a generic value pattern
    assert get_value_pattern_for_type('NO_SUCH_TYPE') == r'[^\s,="]+'


def test_generate_sedcmd_regex_key_value_format():
    text = 'user=john.doe@example.com action=login'
    pii = 'john.doe@example.com'
    start = text.index(pii)
    rule = generate_sedcmd_regex(text, start, start + len(pii), 'EMAIL_ADDRESS', pii)
    assert rule['replacement'] == 'user=[REDACTED_EMAIL_ADDRESS]'
    match = re.search(rule['pattern'], text)
    assert match and match.group(1) == pii, rule


def test_generate_sedcmd_regex_json_format():
    text = '{"email": "john.doe@example.com", "action": "login"}'
    pii = 'john.doe@example.com'
    start = text.index(pii)
    rule = generate_sedcmd_regex(text, start, start + len(pii), 'EMAIL_ADDRESS', pii)
    assert rule['replacement'] == '"email":"[REDACTED_EMAIL_ADDRESS]"'
    match = re.search(rule['pattern'], text)
    assert match and match.group(1) == pii, rule

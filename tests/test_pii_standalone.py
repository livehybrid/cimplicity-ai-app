#!/usr/bin/env python3
"""Standalone PII pattern tests: no external dependencies.

Asserts the core regex patterns used for PII detection behave as expected and
that the app files the handlers depend on exist in the repo.
"""
import os
import re

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_file_structure():
    for rel in (
        ("ucc-app", "lib", "pii_detection_logic.py"),
        ("ucc-app", "lib", "ip_address_detector.py"),
        ("ucc-app", "bin", "pii_detection.py"),
    ):
        path = os.path.join(_REPO_ROOT, *rel)
        assert os.path.isfile(path), f"missing {os.path.join(*rel)}"


def test_ip_detection():
    matches = re.findall(
        r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        "My server IP is 192.168.1.1 and external IP is 8.8.8.8")
    assert matches == ['192.168.1.1', '8.8.8.8']


def test_email_detection():
    matches = re.findall(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "Contact me at john.doe@example.com or jane.smith@company.org")
    assert matches == ['john.doe@example.com', 'jane.smith@company.org']


def test_phone_detection():
    matches = re.findall(
        r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        "Call me at 555-123-4567 or 555.987.6543")
    assert matches == ['555-123-4567', '555.987.6543']


def test_ssn_detection():
    matches = re.findall(
        r'\b\d{3}-\d{2}-\d{4}\b',
        "SSN: 123-45-6789 and 987-65-4321")
    assert matches == ['123-45-6789', '987-65-4321']


def test_credit_card_detection():
    matches = re.findall(
        r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
        "Card: 1234-5678-9012-3456 or 1234 5678 9012 3456")
    assert matches == ['1234-5678-9012-3456', '1234 5678 9012 3456']

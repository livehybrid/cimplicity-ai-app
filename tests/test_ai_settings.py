"""Tests for lib/ai_settings.read_ai_configuration (the credential-read retry).

Pure logic: the reader and the sleep are injected, so no solnlib, no splunkd and
no real delay. Models the observed Splunk Cloud SHC behaviour where the api_key
reads back empty on some attempts and present on others.
"""
import ai_settings


def _reader(sequence):
    """A read_stanza callable that yields each dict in sequence, then repeats the last."""
    calls = {"n": 0}

    def read():
        i = min(calls["n"], len(sequence) - 1)
        calls["n"] += 1
        val = sequence[i]
        if isinstance(val, Exception):
            raise val
        return val

    read.calls = calls
    return read


def _no_sleep():
    slept = []
    return slept, (lambda d: slept.append(d))


CONFIGURED = {"api_key": "sk-or-v1-abc", "api_endpoint": "https://openrouter.ai/api/v1/chat/completions", "model": "anthropic/claude-sonnet-5"}
NO_KEY = {"api_endpoint": "https://openrouter.ai/api/v1/chat/completions", "model": "anthropic/claude-sonnet-5"}


def test_key_present_first_read_returns_immediately():
    read = _reader([CONFIGURED])
    slept, sleep = _no_sleep()
    out = ai_settings.read_ai_configuration(read, sleep=sleep)
    assert out["api_key"] == "sk-or-v1-abc"
    assert read.calls["n"] == 1          # no retry
    assert slept == []                    # never slept


def test_empty_then_present_retries_and_succeeds():
    # empty on the first two attempts, key on the third
    read = _reader([NO_KEY, NO_KEY, CONFIGURED])
    slept, sleep = _no_sleep()
    out = ai_settings.read_ai_configuration(read, attempts=4, delay=0.4, sleep=sleep)
    assert out["api_key"] == "sk-or-v1-abc"
    assert read.calls["n"] == 3
    assert slept == [0.4, 0.4]            # slept between the first three attempts


def test_never_present_returns_last_without_raising():
    read = _reader([NO_KEY])
    slept, sleep = _no_sleep()
    out = ai_settings.read_ai_configuration(read, attempts=3, sleep=sleep)
    assert "api_key" not in out or not out.get("api_key")
    assert out.get("model") == "anthropic/claude-sonnet-5"   # endpoint/model still returned
    assert read.calls["n"] == 3
    assert len(slept) == 2               # slept between attempts, not after the last


def test_read_exception_is_treated_as_a_miss_and_retried():
    read = _reader([RuntimeError("transient"), CONFIGURED])
    slept, sleep = _no_sleep()
    out = ai_settings.read_ai_configuration(read, attempts=3, sleep=sleep)
    assert out["api_key"] == "sk-or-v1-abc"
    assert read.calls["n"] == 2


def test_all_reads_raise_returns_empty_without_raising():
    read = _reader([RuntimeError("x")])
    slept, sleep = _no_sleep()
    out = ai_settings.read_ai_configuration(read, attempts=2, sleep=sleep)
    assert out == {}

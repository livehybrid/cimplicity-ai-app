"""Tests for lib/llm_response.py (tolerant parsing of LLM JSON replies).

Pure-logic tests: no network, no splunk.persistconn. Each fixture below is a
reply shape observed from a real provider, not an invented one; the fenced
array in particular is what claude-sonnet-5 returns for the cim_mapping prompt
and what the previous strict json.loads() discarded.
"""
import llm_response as lr


MAPPING = [
    {"field": "user", "cimField": "user", "confidence": 0.97, "reasoning": "identity"},
    {"field": "evt", "cimField": "action", "confidence": 0.9, "reasoning": "outcome"},
]


class TestParseJson:
    def test_bare_object(self):
        assert lr.parse_json('{"sourcetype": "kestrel_access_control"}') == {
            "sourcetype": "kestrel_access_control"
        }

    def test_fenced_object(self):
        raw = '```json\n{"sourcetype": "wms_core_transaction_log"}\n```'
        assert lr.parse_json(raw) == {"sourcetype": "wms_core_transaction_log"}

    def test_fence_without_language_hint(self):
        assert lr.parse_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_preamble_before_object(self):
        raw = 'Here is the extraction you asked for:\n{"a": 1}'
        assert lr.parse_json(raw) == {"a": 1}

    def test_trailing_prose_after_object(self):
        raw = '{"a": 1}\n\nLet me know if you want the regexes tightened.'
        assert lr.parse_json(raw) == {"a": 1}

    def test_unterminated_fence_from_truncated_completion(self):
        # finish_reason=length cuts the closing fence off.
        assert lr.parse_json('```json\n{"a": 1}') == {"a": 1}

    def test_null_content_returns_none(self):
        # A refused or truncated completion arrives as null, not a string.
        assert lr.parse_json(None) is None
        assert lr.parse_json("") is None
        assert lr.parse_json("   \n ") is None

    def test_unparseable_returns_none(self):
        assert lr.parse_json("I cannot help with that request.") is None

    def test_nested_braces_survive(self):
        raw = '```json\n{"outer": {"inner": [1, 2, 3]}}\n```'
        assert lr.parse_json(raw) == {"outer": {"inner": [1, 2, 3]}}


class TestParseJsonArray:
    def test_bare_array(self):
        # What claude-opus-5 returns.
        assert lr.parse_json_array(_dump(MAPPING)) == MAPPING

    def test_fenced_array(self):
        # What claude-sonnet-5 returns, and what used to be thrown away.
        assert lr.parse_json_array("```json\n%s\n```" % _dump(MAPPING)) == MAPPING

    def test_single_key_wrapper(self):
        # response_format=json_object forbids a top-level array, so models wrap.
        assert lr.parse_json_array('{"mappings": %s}' % _dump(MAPPING)) == MAPPING

    def test_wrapper_key_name_is_irrelevant(self):
        assert lr.parse_json_array('{"suggestions": %s}' % _dump(MAPPING)) == MAPPING

    def test_wrapper_with_sibling_key_still_finds_the_array(self):
        # The old one-key-only rule lost the payload whenever a model added a
        # commentary key alongside it.
        raw = '{"mappings": %s, "notes": "two fields were unmappable"}' % _dump(MAPPING)
        assert lr.parse_json_array(raw) == MAPPING

    def test_fenced_single_key_wrapper(self):
        raw = '```json\n{"mappings": %s}\n```' % _dump(MAPPING)
        assert lr.parse_json_array(raw) == MAPPING

    def test_empty_array_is_preserved_not_treated_as_failure(self):
        # An empty result means "nothing mapped", which is not a parse failure
        # and must not be reported to the user as one.
        assert lr.parse_json_array("[]") == []

    def test_object_with_no_array_returns_none(self):
        assert lr.parse_json_array('{"error": "no mappings"}') is None

    def test_null_content_returns_none(self):
        assert lr.parse_json_array(None) is None

    def test_unparseable_returns_none(self):
        assert lr.parse_json_array("Sorry, I need more context.") is None


def _dump(obj):
    import json

    return json.dumps(obj)

"""Tolerant parsing of a JSON reply from an LLM.

Both AI handlers used to call `json.loads()` straight on the model's message
content. That works only while the model returns bare JSON and nothing else,
which is not something a model can be relied upon to do: the commonest
deviation by far is wrapping the payload in a markdown fence, and the second
commonest is a sentence of preamble before it. `response_format={"type":
"json_object"}` reduces but does not eliminate either, and servers that do not
implement response_format at all (older Ollama and LM Studio OpenAI-compat
layers) ignore it entirely.

The cost of being strict was silent: a model could return a completely correct
mapping and the app would discard it as "Failed to parse LLM response". It bites
hardest with small local models, which fence far more readily than the frontier
hosted ones, and local models are exactly the deployment the app advertises for
air-gapped sites.

This module lives in lib/ (like model_catalog) so it is importable and testable
without splunk.persistconn on the path.
"""
import json
import re

# ```json ... ``` or ``` ... ```, non-greedy so the first fenced block wins.
_FENCE_RE = re.compile(r"```[ \t]*(?:json|JSON)?[ \t]*\r?\n(.*?)```", re.DOTALL)

# Fallback for unterminated fences (a truncated completion), where the closing
# ``` never arrived: take everything after the opening fence.
_OPEN_FENCE_RE = re.compile(r"```[ \t]*(?:json|JSON)?[ \t]*\r?\n(.*)", re.DOTALL)


def _candidates(text):
    """Yield progressively more forgiving slices of the reply to try."""
    stripped = text.strip()
    yield stripped

    for match in _FENCE_RE.finditer(stripped):
        yield match.group(1).strip()

    open_fence = _OPEN_FENCE_RE.match(stripped)
    if open_fence:
        yield open_fence.group(1).strip()

    # Prose before or after the payload: take the outermost bracketed span.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = stripped.find(opener)
        end = stripped.rfind(closer)
        if start != -1 and end > start:
            yield stripped[start:end + 1]


def parse_json(content):
    """Parse an LLM reply that is meant to be JSON.

    Returns the decoded object, or None if nothing in the reply parses. None is
    also returned for a null or blank content, which is what a model emits when
    a completion is refused or truncated before any text is produced.
    """
    if not isinstance(content, str) or not content.strip():
        return None

    for candidate in _candidates(content):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    return None


def parse_json_array(content):
    """Parse a reply that should be a JSON array of objects.

    `response_format={"type": "json_object"}` requires a top-level object, so a
    model asked for an array commonly returns it wrapped under a single key
    ({"mappings": [...]}). Some also add a sibling key such as "notes", which is
    why unwrapping cannot simply require a one-key dict.

    Returns a list, or None if the reply yields no array.
    """
    parsed = parse_json(content)
    if parsed is None:
        return None
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        # Single key: the array is the value, whatever the key is called.
        if len(parsed) == 1:
            only = list(parsed.values())[0]
            return only if isinstance(only, list) else None
        # Several keys: take the first value that is a list of objects, so an
        # accompanying "notes" or "summary" key does not lose the payload.
        for value in parsed.values():
            if isinstance(value, list) and all(isinstance(i, dict) for i in value):
                return value
    return None

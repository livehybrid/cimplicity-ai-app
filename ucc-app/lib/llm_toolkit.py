"""The Splunk AI Toolkit backend: reach an LLM by dispatching `| ai`.

The alternative to our own HTTPS call (lib/llm_client.py). The customer
configures one LLM connection in the AI Toolkit and CIMPlicity borrows it, so
there is no second API key to manage, and on Splunk Cloud it can reach Splunk
Hosted Models where there is no key at all.

Everything here was learned the hard way against AI Toolkit 6.1; see
docs/AI-TOOLKIT-INTEGRATION-PLAN.md §2b.

THE PROMPT IS `str.format()`-ED. `| ai` runs the prompt through Python's
`str.format()` against the event's fields before sending it. So a prompt
containing a literal `{` is a fatal `KeyError`, which surfaces as
`Error in 'ai' command: 'ok'` and reads like a server fault. Both CIMPlicity
prompts show the model a JSON schema and `ai_detection` interpolates the
customer's raw event, so every one of our calls would die on this.

`build_spl` doubles every brace, which `str.format()` collapses back, so the
model receives exactly the prompt we wrote. That also makes customer data safe:
a log line containing `{"zone":"secure"}` survives intact.

THE RESULT FIELD IS `ai_result_1`, not `result_1` (that is `| aiagent`).

THE PARAMETER SURFACE IS ONLY `prompt`, `connection`, `provider`, `model`.
There is no `max_tokens`, `temperature`, `response_format` or `timeout`; every
other name is rejected with `Param name <x> is not allowed`. So the reply is
bounded by the *connection's* `llm_params.max_tokens` (2000 on every connection
seen in the wild), which only the customer can raise, and JSON fidelity rests
entirely on prompt discipline plus lib/llm_response.py.

A CONNECTION IS PER-USER. Connections carry `default_users`, and the default
mapping is per-user too, so a connection one user can see may be invisible to
another and the caller needs a real user's session key rather than the system
one. Hence `search` is injected rather than built here.
"""
import json
import logging

# The AI Toolkit's own failure strings, which arrive as search messages rather
# than as HTTP errors, so they have to be recognised by text.
NOT_CONFIGURED = ("no default llm configuration", "no configuration found for llm connection")
UNKNOWN_COMMAND = "unknown search command"

RESULT_FIELD = "ai_result_1"

# THE TRAP THAT COSTS YOU A SILENT WRONG ANSWER: `| ai` reports LLM-level
# failures by putting the error message in ai_result_1 and returning a
# successful search. Nothing is flagged; the row looks exactly like an answer.
# Parse it and you get "the model returned nothing useful" instead of "the call
# failed", and in ai_detection's case a silent fall back to local regexes.
#
# Lifted verbatim from the AI Toolkit's own LLM_EXCEPTION_LIST
# (bin/ai_commander/constants.py, 6.1.0), which is the list it checks against
# internally. Observed live: a prompt that made gpt-5-mini spend its whole
# 2000-token budget reasoning came back as "Empty response content received
# from the server."
TOOLKIT_ERROR_CONTENT = {
    "Authentication failed: Incorrect API key provided. Please check your API key.":
        "not_configured",
    "The specified model is either unavailable or not supported for the selected "
    "API version or method. Please verify the model name and your API version.":
        "not_configured",
    "The provided model is not accessible by the bedrock account": "not_configured",
    "On-demand usage isn't supported for the selected model. Please choose a "
    "supported model.": "not_configured",
    "You exceeded your current quota, please check your plan and billing details.":
        "not_configured",
    "Request to the LLM has failed. Please check the provided Connection "
    "Management configuration settings.": "not_configured",
    "Prompt length too long. Please reduce the length of the prompt.": "bad_response",
    "Empty response content received from the server.": "bad_response",
    "TimeoutError - Request timed out": "timeout",
}


class ToolkitError(Exception):
    """Mirrors llm_client.LlmError's shape so callers map one set of reasons."""

    def __init__(self, reason, detail=""):
        super().__init__("%s: %s" % (reason, detail) if detail else reason)
        self.reason = reason
        self.detail = detail


def escape_prompt(prompt):
    """Double every brace so `| ai`'s str.format() pass restores the original.

    Must happen before SPL quoting, not after.
    """
    return prompt.replace("{", "{{").replace("}", "}}")


def spl_quote(value):
    """Escape a value for an SPL double-quoted literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_spl(prompt, connection=None, provider=None, model=None):
    """The search that runs one completion.

    `provider` and `model` must be given together or `| ai` rejects the call;
    passing neither uses the connection's own model.
    """
    spl = '| makeresults | ai prompt="%s"' % spl_quote(escape_prompt(prompt))
    if connection:
        spl += ' connection="%s"' % spl_quote(connection)
    if provider and model:
        spl += ' provider="%s" model="%s"' % (spl_quote(provider), spl_quote(model))
    return spl


def _classify(messages):
    """Turn the AI Toolkit's search messages into a reason tag."""
    joined = " ".join(messages).lower()
    if any(s in joined for s in NOT_CONFIGURED):
        return "not_configured"
    if UNKNOWN_COMMAND in joined:
        return "unavailable"
    return "transport"


def complete(settings, prompt, search):
    """Run one completion through `| ai` and return the reply content.

    settings: the ai_configuration stanza. `toolkit_connection` names a specific
        AI Toolkit connection; omitted, the caller's default connection is used.
    search: `search(spl) -> (rows, messages)`, injected so this module needs no
        splunkd import and is testable. `rows` is a list of result dicts,
        `messages` a list of error/fatal message strings.

    Raises ToolkitError; never returns an empty answer as success.
    """
    settings = settings or {}
    spl = build_spl(prompt,
                    connection=settings.get("toolkit_connection") or None,
                    provider=settings.get("toolkit_provider") or None,
                    model=settings.get("toolkit_model") or None)
    logging.info("AI Toolkit request via | ai (prompt %d chars, SPL %d chars)",
                 len(prompt), len(spl))

    try:
        rows, messages = search(spl)
    except Exception as exc:  # noqa: BLE001 - dispatch failure is a transport failure
        raise ToolkitError("transport", "search dispatch failed: %s" % exc)

    if messages:
        reason = _classify(messages)
        raise ToolkitError(reason, "; ".join(messages)[:300])

    if not rows:
        # A failed | ai run can return DONE with no rows, so absence of results
        # is a failure, not an empty answer.
        raise ToolkitError("bad_response", "no results from | ai")

    content = (rows[0] or {}).get(RESULT_FIELD)
    if not isinstance(content, str) or not content.strip():
        raise ToolkitError("bad_response",
                           "no %s in result (keys: %s)"
                           % (RESULT_FIELD, sorted((rows[0] or {}).keys())))

    # The successful-looking failure. Must be checked before the content is
    # handed back, or the caller parses an error message as an answer.
    reason = TOOLKIT_ERROR_CONTENT.get(content.strip())
    if reason:
        raise ToolkitError(reason, "| ai returned an error as its result: %s"
                           % content.strip())

    logging.info("AI Toolkit reply received (%d chars)", len(content))
    return content

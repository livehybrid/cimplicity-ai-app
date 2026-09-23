"""One place that talks to an LLM.

`ai_detection` and `cim_mapping` each carried their own near-identical
`requests.post`, differing only in the X-Title header and what they did with a
failure. That duplication is why the markdown-fence parsing bug had to be fixed
twice, and it is why the two known defects below survived as long as they did.
Both call sites now come through `complete()`.

It is also the seam the AI Toolkit work needs. Swapping the transport for a
dispatched `| ai` search (see docs/AI-TOOLKIT-INTEGRATION-PLAN.md §3A) means
adding a second implementation behind this function rather than editing two
handlers, and the choice can then become a setting.

Two defects fixed here that the duplicated call sites both had:

* **The timeout was not a total.** `requests`' scalar `timeout=60` is a
  *per-socket-operation* deadline, not a cap on the call: a server that dribbles
  a byte every 59 seconds holds the handler open indefinitely. It is now an
  explicit (connect, read) tuple, which is still not a wall-clock cap (requests
  offers none) but at least says what it is. The real bound on a slow completion
  is max_tokens below.
* **There was no max_tokens.** A model that failed to stop could return until it
  hit the provider's own ceiling, billed to the customer, with the handler
  waiting. Now capped, and overridable from the settings stanza.

Parsing stays with the callers: they want different shapes (`parse_json` vs
`parse_json_array`) and have different fallbacks. This returns the raw content
string and raises `LlmError` on anything else, so each caller keeps its own
failure behaviour.
"""
import json
import logging

import requests

import llm_toolkit

DEFAULT_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-sonnet-5"

# (connect, read). Connect should be quick or the endpoint is wrong; read is
# generous because a large structured reply on a reasoning model is genuinely slow.
DEFAULT_TIMEOUT = (10, 120)

# Comfortably above the largest real reply observed (a 44-field CIM mapping came
# back at ~1.7 KB, roughly 450 tokens) while still bounding a runaway completion.
DEFAULT_MAX_TOKENS = 4000

REFERER = "https://github.com/livehybrid/cimplicity-ai-onboarding"

# ai_configuration.backend. "direct" keeps today's behaviour and is the default,
# so an existing install is untouched by the Toolkit work landing.
BACKEND_DIRECT = "direct"
BACKEND_TOOLKIT = "splunk_ai_toolkit"


class LlmError(Exception):
    """A call that did not produce usable content.

    `reason` is a short machine-ish tag the caller can map to its own message:
    "not_configured", "timeout", "transport", "bad_response".
    """

    def __init__(self, reason, detail=""):
        super().__init__("%s: %s" % (reason, detail) if detail else reason)
        self.reason = reason
        self.detail = detail


def _int_or(value, default):
    try:
        out = int(value)
    except (TypeError, ValueError):
        return default
    return out if out > 0 else default


def complete(settings, prompt, title, timeout=DEFAULT_TIMEOUT,
             max_tokens=None, post=None, search=None):
    """Send a single-turn completion and return the reply content as a string.

    settings: the ai_configuration stanza (api_key, api_endpoint, model, and
        optionally max_tokens and backend). For the direct backend only api_key
        is required; the rest have defaults matching what the handlers shipped.
    title: the X-Title sent to the provider, so usage is attributable per caller.
    post: injected for tests; defaults to requests.post.
    search: `search(spl) -> (rows, messages)`, required only by the AI Toolkit
        backend. Injected because it needs the CALLER'S session key: Toolkit
        connections are per-user and the system key cannot see them.

    Raises LlmError rather than returning a sentinel, so a caller cannot mistake
    a failure for an empty answer.
    """
    post = post or requests.post
    settings = settings or {}

    backend = (settings.get("backend") or BACKEND_DIRECT).strip().lower()
    if backend == BACKEND_TOOLKIT:
        return _complete_via_toolkit(settings, prompt, search)

    api_key = settings.get("api_key")
    if not api_key:
        raise LlmError("not_configured", "no api_key in ai_configuration")

    endpoint = settings.get("api_endpoint") or DEFAULT_ENDPOINT
    model = settings.get("model") or DEFAULT_MODEL
    if max_tokens is None:
        max_tokens = _int_or(settings.get("max_tokens"), DEFAULT_MAX_TOKENS)

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
    }
    logging.info("LLM request to %s (model %s, max_tokens %s, prompt %d chars)",
                 endpoint, model, max_tokens, len(prompt))

    try:
        response = post(
            url=endpoint,
            headers={"Authorization": "Bearer %s" % api_key,
                     "X-Title": title,
                     "HTTP-Referer": REFERER,
                     "Content-Type": "application/json"},
            data=json.dumps(body),
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.Timeout as exc:
        raise LlmError("timeout", str(exc))
    except requests.exceptions.RequestException as exc:
        raise LlmError("transport", str(exc))
    except ValueError as exc:  # json() on a non-JSON body
        raise LlmError("bad_response", "response was not JSON: %s" % exc)

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmError("bad_response", "unexpected response shape: %s" % exc)

    # A refused or truncated completion arrives as null content, which is not an
    # HTTP error but is not an answer either. Surface it as a failure so the
    # caller takes its fallback rather than parsing None.
    if not isinstance(content, str) or not content.strip():
        finish = ""
        try:
            finish = payload["choices"][0].get("finish_reason") or ""
        except (KeyError, IndexError, TypeError):
            pass
        raise LlmError("bad_response", "empty content (finish_reason=%r)" % finish)

    logging.info("LLM reply received (%d chars)", len(content))
    return content


def _complete_via_toolkit(settings, prompt, search):
    """Delegate to lib/llm_toolkit, remapping its errors onto LlmError.

    Kept behind the same function so the handlers have exactly one call site and
    one set of failure reasons whichever backend is selected.
    """
    if search is None:
        raise LlmError("not_configured",
                       "the Splunk AI Toolkit backend needs a search runner")
    try:
        return llm_toolkit.complete(settings, prompt, search)
    except llm_toolkit.ToolkitError as exc:
        raise LlmError(exc.reason, exc.detail)

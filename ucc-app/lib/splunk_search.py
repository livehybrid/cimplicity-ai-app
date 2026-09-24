"""Run a oneshot Splunk search from a REST handler, for the AI Toolkit backend.

`| ai` is a search command, so reaching it from a persistent handler means
dispatching a search. Two things make this less obvious than it looks.

**Use `exec_mode=oneshot`, never `search/jobs/export`.** export returns an empty
HTTP 200 when the search FAILS, so an `| ai` failure is indistinguishable from a
successful run that produced nothing. oneshot returns `results` and `messages`
in one synchronous document, so a failure can be seen and reported.

**Use the CALLER'S session key, not the system one.** AI Toolkit connections
carry `default_users` and the default-connection mapping is per user, so a
connection is not necessarily visible to another user; and the whole AI Toolkit
REST surface refuses `splunk-system-user` outright. persistconn hands the
handler both tokens, and this path needs `session.authtoken`.

Kept in lib/ with a guarded import so the module loads outside splunkd and the
tests can drive `make_runner` with an injected transport.
"""
import json
import logging

try:
    import splunk.rest as rest
except Exception:  # pragma: no cover - only importable inside splunkd
    rest = None

# An LLM call inside a search: the AI Toolkit's own connections default to a
# 200s request_timeout, so allow for that plus search overhead.
DEFAULT_TIMEOUT = 300


def parse_response(body):
    """Split a oneshot search's JSON body into (rows, messages).

    messages holds only ERROR/FATAL text; INFO ones (such as "this is a slow
    search") are noise and would otherwise be read as failures.
    """
    try:
        doc = json.loads(body) if isinstance(body, (str, bytes)) else body
    except (TypeError, ValueError) as exc:
        return [], ["unparseable search response: %s" % exc]
    if not isinstance(doc, dict):
        return [], ["unexpected search response type: %s" % type(doc).__name__]
    messages = [str(m.get("text", "")) for m in (doc.get("messages") or [])
                if str(m.get("type", "")).upper() in ("ERROR", "FATAL")]
    rows = [r for r in (doc.get("results") or []) if isinstance(r, dict)]
    return rows, messages


def make_runner(session_key, username, app="search", timeout=DEFAULT_TIMEOUT,
                request=None):
    """Return `search(spl) -> (rows, messages)` bound to one user's session.

    request: injected for tests; defaults to splunk.rest.simpleRequest.
    """
    call = request or (rest.simpleRequest if rest is not None else None)
    if call is None:
        raise RuntimeError("splunk.rest is unavailable outside splunkd")

    # The user namespace matters: a oneshot dispatched as `nobody` does not see
    # the caller's default AI Toolkit connection.
    url = "/servicesNS/%s/%s/search/jobs" % (username or "nobody", app)

    def search(spl):
        args = {"search": spl, "exec_mode": "oneshot", "output_mode": "json"}
        kwargs = {"sessionKey": session_key, "method": "POST",
                  "postargs": args, "raiseAllErrors": False}
        try:
            resp, content = call(url, timeout=timeout, **kwargs)
        except TypeError:
            # Older splunk.rest.simpleRequest has no timeout parameter.
            resp, content = call(url, **kwargs)
        status = int(getattr(resp, "status", 0) or 0)
        if isinstance(content, bytes):
            content = content.decode("utf-8", "replace")
        if status >= 400:
            return [], ["search dispatch returned HTTP %s: %s" % (status, str(content)[:200])]
        rows, messages = parse_response(content)
        if messages:
            logging.warning("search reported %d error message(s)", len(messages))
        return rows, messages

    return search

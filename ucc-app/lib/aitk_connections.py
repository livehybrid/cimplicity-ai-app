"""List the AI Toolkit LLM connections the caller can actually use.

Feeds the Configuration page's "AI Toolkit connection" dropdown. Before this it
was a free-text box, so a typo surfaced only when a call failed with
`No configuration found for llm connection: <typo>`, which reads like the
connection is broken rather than misspelled.

TWO THINGS MAKE THIS LESS OBVIOUS THAN "LIST THE COLLECTION".

**Connections are per-user.** Each row carries `default_users`, and a row not
shared with the caller cannot be used by them even though it is plainly visible
in the KV collection. Listing everything would offer choices that fail at call
time, so rows are filtered to what the caller can use: `['*']` (shared with
everyone) or a list containing them.

**The collection lives in the `nobody` namespace**, not the caller's, because
the AI Toolkit writes everything with `namespace="app"`. Reading it as the
caller returns an empty list. The READ must still be done with the caller's
token, though, or nothing is resolvable per-user.

No AI Toolkit, or no readable connections, is an empty list and never an error:
a dropdown must not break the Configuration page, and the field stays typeable
so an unlisted name is never a blocker.
"""
import json
import logging

KV_PATH = ("/servicesNS/nobody/Splunk_ML_Toolkit/storage/collections/data/"
           "aitk_llm_connection")


def usable_by(row, username):
    """Whether `username` can select this connection.

    Mirrors what `| ai connection=<name>` accepts. A row with an empty
    default_users is owner-only, and offering it to anyone else produces a
    confusing runtime failure.
    """
    users = row.get("default_users")
    if not isinstance(users, list):
        return False
    if "*" in users:
        return True
    return bool(username) and username in users


def describe(row):
    """A label that makes the choice obvious in a dropdown.

    "OpenAIDefault (OpenAI, gpt-5-mini)" beats a bare name when several
    connections differ only by model.
    """
    name = row.get("name") or ""
    provider = (row.get("provider") or "").strip()
    model = (row.get("model") or "").strip()
    detail = ", ".join(p for p in (provider, model) if p)
    return "%s (%s)" % (name, detail) if detail else name


def to_entries(rows, username):
    """The EAI-shaped entries UCC's singleSelect expects, deduped and sorted.

    { "entry": [ { "name": "<value>", "content": { "label": "..." } } ] }
    """
    seen, entries = set(), []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not name or name in seen or not usable_by(row, username):
            continue
        seen.add(name)
        entries.append({"name": name, "content": {"label": describe(row)}})
    entries.sort(key=lambda e: e["name"].lower())
    return entries


def list_connections(request, username):
    """Fetch and shape the connections. Never raises.

    request: `request(path) -> (status, body)`, injected so this module needs no
        splunkd import and the tests need no Toolkit.
    """
    try:
        status, body = request(KV_PATH)
    except Exception as exc:  # noqa: BLE001 - a dropdown must not break the page
        logging.warning("Could not read AI Toolkit connections: %s", exc)
        return []
    if status == 404:
        logging.info("No AI Toolkit connections: the collection is absent "
                     "(the AI Toolkit is probably not installed)")
        return []
    if status >= 400:
        logging.warning("Reading AI Toolkit connections returned HTTP %s", status)
        return []
    try:
        rows = json.loads(body) if isinstance(body, (str, bytes)) else body
    except (TypeError, ValueError) as exc:
        logging.warning("AI Toolkit connections did not parse: %s", exc)
        return []
    if not isinstance(rows, list):
        return []
    entries = to_entries(rows, username)
    logging.info("Offering %d of %d AI Toolkit connection(s) to %s",
                 len(entries), len(rows), username or "(unknown user)")
    return entries

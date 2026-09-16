"""Read the AI configuration resiliently.

The api_key is an encrypted (REST_CREDENTIAL) field. On a Splunk Cloud search
head cluster a credential saved on one member is not always immediately
readable on another: a call served by a member that has not yet caught up gets
the ai_configuration stanza back WITHOUT the key, and the handler reports
"AI service is not configured" even though the key is set. Observed live
2026-09-16: identical calls succeeded ~50% of the time, alternating over time
rather than failing outright, which is the signature of a transient read race
rather than a permanent gap.

A single read is therefore not reliable. `read_ai_configuration` retries a few
times with a short delay and returns as soon as the key is present. This rides
through a transient miss (a cache still warming, replication a beat behind); it
cannot conjure a key a member has genuinely never received, which is an infra
concern, but on the observed stack the key does become readable within a
retry window.

Kept in lib/ (like llm_response and model_catalog) so both AI handlers share one
implementation and it is testable without splunk.persistconn on the path.
"""
import logging
import time

# 4 attempts over ~1.2s: long enough to clear a transient miss, short enough not
# to stall the request noticeably when the key genuinely is not there.
DEFAULT_ATTEMPTS = 4
DEFAULT_DELAY = 0.4


def read_ai_configuration(read_stanza, attempts=DEFAULT_ATTEMPTS,
                          delay=DEFAULT_DELAY, sleep=time.sleep):
    """Return the ai_configuration stanza, retrying until the api_key is present.

    read_stanza: a zero-arg callable returning the ai_configuration dict (or {}).
        It is called afresh each attempt so a per-object cache cannot pin a stale
        empty read. Exceptions from it are swallowed and treated as an empty read.

    Returns the first read whose "api_key" is truthy; otherwise the last read
    obtained (so callers still see api_endpoint/model even when the key is
    missing). Never raises.
    """
    last = {}
    for attempt in range(attempts):
        try:
            settings = read_stanza() or {}
        except Exception as exc:  # noqa: BLE001 - a read error is just a miss to retry
            logging.warning("ai_configuration read failed (attempt %d/%d): %s",
                            attempt + 1, attempts, exc)
            settings = {}
        if settings.get("api_key"):
            if attempt:
                logging.info("ai_configuration api_key read on attempt %d/%d",
                             attempt + 1, attempts)
            return settings
        last = settings or last
        if attempt < attempts - 1:
            sleep(delay)
    logging.warning("ai_configuration api_key still empty after %d attempts; "
                    "on a Splunk Cloud SHC this can be credential-replication lag",
                    attempts)
    return last

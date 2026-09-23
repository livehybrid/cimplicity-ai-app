"""Register CIMPlicity's onboarding know-how as Splunk AI Toolkit *skills*.

WHY THIS EXISTS
A Launchpad agent that has CIMPlicity's MCP tools attached still has to be told
how to use them well: which regex dialect Splunk wants, that a CIM mapping needs
a confidence and a reason, what order to do things in. That guidance is exactly
what an AI Toolkit "skill" is for, and skills are the one part of the Toolkit an
app can write. So the app ships its own skills and registers them on install,
the same way it already registers its MCP tools (see autoregister.py).

THE THREE THINGS THAT MAKE THIS WORK, none of them obvious
1. **Namespace.** Every skills route runs `validate_and_add_user_info`, which
   compares the URL's namespace user against the user the token resolves to and
   raises on a mismatch (the handler flattens that into a bare 500). With a
   system token the ONLY namespace that works is `splunk-system-user`:
     /servicesNS/admin/...              -> 500, splunk-system-user != admin
     /servicesNS/nobody/...             -> 403, validation is skipped for
                                          'nobody' so capabilities never load
                                          and the edit_agent_connections check
                                          fails
     /servicesNS/splunk-system-user/... -> 201
2. **The ACL, or the skill is invisible.** `SkillManager.create_skill`
   hard-codes `acl = {sharing: "owner", owner: <caller>, perms: {read: [],
   write: []}}` and IGNORES any acl in the POST body. `list_skills` then filters
   every row through `is_user_eligible_by_role`, which returns False outright
   when `sharing == "owner"` and the caller is not the owner. A skill created by
   splunk-system-user is therefore invisible to every real user until a second
   call widens the acl. `acl` is in the handler's UPDATABLE_FIELDS, so a PUT
   does it. Keep `owner` as splunk-system-user or the next upgrade cannot rewrite
   its own skill.
3. **The cold-hit artefact.** The Toolkit's REST handler intermittently answers
   `bad character (49) in reply size`, a chunked-encoding artefact, typically on
   the first request after a splunkd restart. It is not a real error and it is
   not specific to any one route, so every call retries.

Verified end to end against AI Toolkit 6.1.0 on Splunk Enterprise 10.4 with no
Splunk Cloud Connect, so this works on-premises as well as on Cloud.

Pure stdlib and side-effect free on import, so the tests exercise it without
splunkd by injecting `request`.
"""
import json

# The only namespace a system token can use; see note 1 in the module docstring.
SKILLS_URL = "/servicesNS/splunk-system-user/Splunk_ML_Toolkit/mltk/agent_skills"

# Widens the hard-coded private acl so real users can actually see the skill.
# owner MUST stay splunk-system-user: is_user_eligible_by_role short-circuits on
# `user_name == acl['owner']`, which is what lets a later upgrade rewrite it.
OPEN_ACL = {
    "sharing": "global",
    "app": "SPLUNK_ML_TOOLKIT",
    "owner": "splunk-system-user",
    "perms": {"read": ["*"], "write": ["admin"]},
}

CHUNKED_ARTEFACT = "bad character"
ATTEMPTS = 3

# Skill bodies are deliberately Launchpad-sized. Splunk's own managed skills run
# 2.7 KB to 4.2 KB, and skill text is resent on every agent turn, so a long skill
# is a direct and repeated token cost. Keep each one under ~4 KB.
SKILLS = [
    {
        "name": "CIMPlicityFieldExtraction",
        "category": "platform",
        "description": "How to propose Splunk field extractions that actually work in props.conf.",
        "skill_text": (
            "When proposing field extractions for a raw event, use the cim_plicity "
            "ai_detection tool rather than writing regexes by hand, then check its "
            "output against these rules before presenting it.\n\n"
            "Regex dialect. Splunk uses PCRE with named capture groups written "
            "(?<name>...). Python syntax (?P<name>...) is NOT valid in props.conf and "
            "is the single most common mistake. Reject any regex that uses it.\n\n"
            "Each regex must match the whole log line and capture its field exactly "
            "once. A pattern that can match repeatedly produces multi-value fields "
            "the user did not ask for.\n\n"
            "Prefer anchoring to stable surrounding text (a key name, a delimiter) "
            "over position. Position-based extraction breaks on the first event with "
            "an optional field missing.\n\n"
            "Field names must be lowercase with underscores, and should match the CIM "
            "field they will map to where one obviously applies (src_ip, not "
            "sourceIP). Renaming later means rewriting the props stanza.\n\n"
            "Timestamps. Always return TIME_FORMAT as a Python datetime format string, "
            "TIME_PREFIX for any character that precedes the timestamp (often '[' ), "
            "and MAX_TIMESTAMP_LOOKAHEAD, raising it above the default 25 when the "
            "timestamp sits late in the line. Getting these wrong is what causes "
            "events to index under the wrong time, which is far more damaging than a "
            "missing field and much harder to notice later.\n\n"
            "Before presenting extractions, ask for a second and third sample event. "
            "A regex derived from one line is a guess. Events that differ in optional "
            "fields, in quoting, or in whether a value can be empty are where "
            "extractions break."
        ),
    },
    {
        "name": "CIMPlicityCIMMapping",
        "category": "platform",
        "description": "How to map extracted fields onto a Splunk CIM data model, and when not to.",
        "skill_text": (
            "Use the cim_plicity cim_mapping tool to map extracted fields onto a CIM "
            "data model. cimModel is a lowercase_underscore key such as "
            "authentication, network_traffic or web.\n\n"
            "Pick the data model from what the events MEAN, not from the fields they "
            "happen to carry. A door-access log with a badge id and an allow/deny "
            "decision is Authentication, even though nothing in it looks like a login. "
            "Say which model you chose and why before showing any mapping.\n\n"
            "Every mapping needs a confidence between 0.0 and 1.0 and a one-line "
            "reason. Present anything below about 0.6 as a question for the user "
            "rather than as a result: a plausible-looking wrong mapping is worse than "
            "an absent one, because it silently corrupts every downstream dashboard "
            "and correlation search that trusts the model.\n\n"
            "Several extracted fields may legitimately map to the same CIM field. Do "
            "not force a one-to-one mapping.\n\n"
            "Leave genuinely unmappable fields out of the mapping rather than "
            "stretching for a CIM field that nearly fits. They remain available as "
            "extracted fields. Tell the user which ones you dropped and why, because "
            "that list is often the most useful part of the answer: it is where the "
            "data source does something the model does not anticipate.\n\n"
            "CIM compliance also needs the event tagged and the sourcetype associated "
            "with the model via eventtypes and tags. A field mapping alone does not "
            "make the data appear in a data model search, and a user who thinks it "
            "does will conclude the mapping failed."
        ),
    },
    {
        "name": "CIMPlicityOnboardingWorkflow",
        "category": "platform",
        "description": "The order to onboard an unfamiliar data source with the CIMPlicity tools.",
        "skill_text": (
            "Onboarding an unfamiliar source with the cim_plicity tools. Work in this "
            "order; each step depends on the one before it.\n\n"
            "1. Call cim_plicity_ping first to confirm the app is reachable and see "
            "which tools are registered. If it fails, stop and say so rather than "
            "guessing at the others.\n\n"
            "2. Get real events. Ask for several, from different times of day if the "
            "source is bursty. Never design an extraction from a single line.\n\n"
            "3. Run pii_detection BEFORE anything leaves the platform or is written "
            "into a summary. If it reports hits, say what was found and ask how the "
            "user wants it handled. Do not quote the matched values back in full.\n\n"
            "4. Run ai_detection on a representative event to get a sourcetype, field "
            "extractions and timestamp settings. Apply the field-extraction rules "
            "before presenting anything.\n\n"
            "5. Check the proposed extractions against the OTHER samples from step 2 "
            "and report which fields failed on which events. This is the step most "
            "often skipped and it is where the real defects surface.\n\n"
            "6. Only then run cim_mapping, using the field names as extracted.\n\n"
            "7. Present props.conf and transforms.conf stanzas the user can paste, "
            "with the sourcetype, EXTRACT or REPORT entries, and the TIME_FORMAT, "
            "TIME_PREFIX and MAX_TIMESTAMP_LOOKAHEAD settings together in one block.\n\n"
            "Say plainly which parts are verified against real events and which are "
            "the model's suggestion. The user is going to put this into a production "
            "props.conf, where a wrong timestamp setting misfiles data permanently and "
            "is not obvious until someone searches for it weeks later."
        ),
    },
]


def build_skill_docs(skills=None):
    """The POST bodies, one per skill. Separated out so a test can assert the
    shipped content without touching the transport."""
    out = []
    for s in (SKILLS if skills is None else skills):
        out.append({"name": s["name"], "category": s["category"],
                    "description": s["description"], "skill_text": s["skill_text"]})
    return out


def _call(request, method, url, body=None):
    """One call, retried past the chunked-encoding artefact (note 3 above).

    `request(method, url, body) -> (status, text)`; any exception is a failed
    attempt, never a raise out of here.
    """
    status, text = 0, ""
    for _ in range(ATTEMPTS):
        try:
            status, text = request(method, url, body)
        except Exception as exc:  # noqa: BLE001 - an exception is just a failed attempt
            status, text = 0, "%s: %s" % (type(exc).__name__, exc)
            continue
        if CHUNKED_ARTEFACT not in (text or ""):
            return status, text
    return status, text


def toolkit_present(request):
    """True when the AI Toolkit's skills route answers at all.

    A GET is used rather than reading app state because the app can be installed
    but too old to carry Agent Launchpad; what matters is whether the route is
    there. 404 means no Toolkit (or a version without skills).
    """
    status, _ = _call(request, "GET", SKILLS_URL)
    return status == 200


def register_skills(request, skills=None):
    """Create-or-update every shipped skill, and make it visible.

    Idempotent by design, because the app.conf [triggers] reload fires this on
    every install, enable and upgrade:
      POST  -> 201 created, or 409 when it already exists (both fine)
      PUT   -> rewrites description/category/skill_text AND widens the acl, so an
               upgrade ships new wording and a first install becomes visible

    Returns a per-skill result list. Never raises: this runs from a reload
    trigger, where an exception would surface as a broken app install.
    """
    results = []
    for doc in build_skill_docs(skills):
        name = doc["name"]
        created, created_body = _call(request, "POST", SKILLS_URL, doc)
        # PUT carries `name` (the handler requires it in the body and rejects it
        # as an update field) plus the acl, so one call both refreshes the text
        # on upgrade and makes a newly created skill visible.
        update = dict(doc)
        update["acl"] = OPEN_ACL
        updated, updated_body = _call(request, "PUT", "%s/%s" % (SKILLS_URL, name), update)
        results.append({
            "name": name,
            "created": created,
            "updated": updated,
            "ok": updated == 200 or created == 201,
            "error": None if updated == 200 else (updated_body or created_body or "")[:200],
        })
    return results

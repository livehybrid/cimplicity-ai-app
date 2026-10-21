"""Tests for lib/aitk_skills.py, the AI Toolkit skill self-registration.

The transport is injected, so these run with no splunkd and no AI Toolkit. What
they pin down is the set of non-obvious rules the live 6.1 handler enforces,
each of which cost a probe round to find (see the module docstring):

  * the ONLY namespace a system token may use is splunk-system-user
  * create_skill ignores an inline acl, so a PUT must follow or the skill is
    invisible to every real user
  * acl.owner must stay splunk-system-user or the next upgrade cannot rewrite
    its own skill
  * a chunked-encoding artefact ("bad character (49) in reply size") must be
    retried, not reported
  * this runs from a reload trigger, so it must never raise
"""
import json

import aitk_skills


class FakeToolkit:
    """Stands in for the AI Toolkit's agent_skills route.

    Models the behaviour that matters: POST creates once then 409s, PUT needs the
    skill to exist, and an optional prefix of responses can be forced (to
    simulate the cold-hit artefact or an outage).
    """

    def __init__(self, present=True, forced=None):
        self.present = present
        self.forced = list(forced or [])
        self.store = {}
        self.calls = []

    def __call__(self, method, url, body=None):
        self.calls.append((method, url, body))
        if self.forced:
            return self.forced.pop(0)
        if not self.present:
            return 404, json.dumps({"payload": "Unknown REST endpoint: agent_skills"})
        if method == "GET":
            return 200, json.dumps({"skills": list(self.store.values()),
                                    "count": len(self.store)})
        if method == "POST":
            name = body["name"]
            if name in self.store:
                return 409, json.dumps(
                    {"error_message": "A skill with name '%s' already exists." % name})
            # The live handler HARD-CODES this acl and ignores any acl supplied.
            doc = dict(body)
            doc["acl"] = {"sharing": "owner", "app": "SPLUNK_ML_TOOLKIT",
                          "owner": "splunk-system-user",
                          "perms": {"read": [], "write": []}}
            self.store[name] = doc
            return 201, json.dumps(doc)
        if method == "PUT":
            name = (body or {}).get("name")
            if not name:
                return 400, json.dumps(
                    {"error_message": "Field 'name' is required in the payload."})
            if name not in self.store:
                return 404, json.dumps({"error_message": "Skill '%s' not found." % name})
            updates = {k: v for k, v in body.items() if k != "name"}
            unknown = set(updates) - {"description", "category", "skill_text", "acl"}
            if unknown:
                return 400, json.dumps({"error_message": "Unknown or non-updatable fields."})
            self.store[name].update(updates)
            return 200, json.dumps(self.store[name])
        return 405, "Unsupported method: %s" % method


def _visible(doc):
    """Mirrors is_user_eligible_by_role for a caller who is not the owner."""
    acl = doc.get("acl") or {}
    if acl.get("sharing") == "owner":
        return False
    return "*" in (acl.get("perms", {}).get("read") or [])


# --- shipped content -------------------------------------------------------

def test_three_skills_ship_with_the_required_fields():
    docs = aitk_skills.build_skill_docs()
    assert len(docs) == 3
    for d in docs:
        # REQUIRED_FIELDS in the live handler; a miss is a 400 at install time.
        assert set(d) == {"name", "category", "description", "skill_text"}
        assert all(isinstance(v, str) and v.strip() for v in d.values())


def test_skill_text_stays_launchpad_sized():
    # Skill text is resent on every agent turn, so length is a recurring token
    # cost. Splunk's own managed skills run 2.7-4.2 KB.
    for d in aitk_skills.build_skill_docs():
        assert len(d["skill_text"]) <= 4096, d["name"]


def test_field_extraction_skill_names_the_regex_dialect_trap():
    text = next(d["skill_text"] for d in aitk_skills.build_skill_docs()
                if d["name"] == "CIMPlicityFieldExtraction")
    assert "(?<name>...)" in text and "(?P<name>...)" in text


# --- the namespace rule ----------------------------------------------------

def test_requests_go_to_the_splunk_system_user_namespace_only():
    # admin -> 500 and nobody -> 403 with a system token; this is the one that works.
    assert aitk_skills.SKILLS_URL.startswith("/servicesNS/splunk-system-user/")
    fake = FakeToolkit()
    aitk_skills.register_skills(fake)
    assert all(url.startswith(aitk_skills.SKILLS_URL) for _, url, _ in fake.calls)


# --- create then widen -----------------------------------------------------

def test_a_fresh_install_creates_and_then_makes_visible():
    fake = FakeToolkit()
    results = aitk_skills.register_skills(fake)

    assert [r["created"] for r in results] == [201, 201, 201]
    assert [r["updated"] for r in results] == [200, 200, 200]
    assert all(r["ok"] for r in results)
    # The whole point: without the PUT these are invisible to every real user.
    assert all(_visible(doc) for doc in fake.store.values())


def test_the_put_keeps_owner_as_system_so_upgrades_can_rewrite():
    # is_user_eligible_by_role short-circuits on user == acl['owner']; change the
    # owner and the next upgrade's PUT is refused.
    assert aitk_skills.OPEN_ACL["owner"] == "splunk-system-user"
    fake = FakeToolkit()
    aitk_skills.register_skills(fake)
    assert all(d["acl"]["owner"] == "splunk-system-user" for d in fake.store.values())


def test_rerun_is_idempotent_and_refreshes_the_text():
    fake = FakeToolkit()
    aitk_skills.register_skills(fake)
    before = len(fake.store)

    # Simulate an upgrade shipping new wording for one skill.
    changed = [dict(s) for s in aitk_skills.SKILLS]
    changed[0] = dict(changed[0], skill_text="rewritten on upgrade")
    results = aitk_skills.register_skills(fake, skills=changed)

    assert len(fake.store) == before                 # no duplicates
    assert [r["created"] for r in results] == [409, 409, 409]   # already existed
    assert all(r["ok"] for r in results)             # 409 on POST is not a failure
    assert fake.store["CIMPlicityFieldExtraction"]["skill_text"] == "rewritten on upgrade"


# --- resilience ------------------------------------------------------------

def test_the_chunked_artefact_is_retried_not_reported():
    artefact = (500, "<msg type=\"ERROR\">bad character (49) in reply size</msg>")
    fake = FakeToolkit(forced=[artefact])            # bites the first call only
    assert aitk_skills.toolkit_present(fake) is True


def test_a_persistently_broken_route_is_reported_not_retried_forever():
    artefact = (500, "bad character (49) in reply size")
    fake = FakeToolkit(forced=[artefact] * 20)
    assert aitk_skills.toolkit_present(fake) is False
    assert len(fake.calls) == aitk_skills.ATTEMPTS


def test_no_toolkit_is_detected_rather_than_attempted():
    fake = FakeToolkit(present=False)
    assert aitk_skills.toolkit_present(fake) is False


def test_a_raising_transport_never_escapes():
    def boom(method, url, body=None):
        raise RuntimeError("splunkd said no")

    assert aitk_skills.toolkit_present(boom) is False
    results = aitk_skills.register_skills(boom)      # must not raise
    assert len(results) == 3
    assert not any(r["ok"] for r in results)
    assert all("splunkd said no" in r["error"] for r in results)


def test_a_failed_skill_is_reported_with_the_reason():
    denied = (403, json.dumps({"error_message": "User is not authorized to manage "
                                                "agent skills. Missing required "
                                                "capabilities."}))
    fake = FakeToolkit(forced=[denied] * 20)
    results = aitk_skills.register_skills(fake)
    assert not any(r["ok"] for r in results)
    assert "Missing required capabilities" in results[0]["error"]

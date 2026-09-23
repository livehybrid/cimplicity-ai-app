# AI Toolkit skills

CIMPlicity registers three **skills** with the Splunk AI Toolkit (`Splunk_ML_Toolkit`)
on install. A Launchpad agent that has CIMPlicity's [MCP tools](MCP_TOOLS.md) attached
still needs telling how to use them well, and a skill is where the Toolkit expects that
guidance to live.

This is the one part of the AI Toolkit an app can write. Agents, LLM connections and MCP
connections are all UI-only (an agent's runtime is provisioned cloud-side, and writing
the KV row by hand produces one that invokes as `Agent Does not exist.`). Skills have no
side registration, so the row *is* the skill.

## The three skills

| Name | What it covers |
|---|---|
| `CIMPlicityFieldExtraction` | Splunk's regex dialect (`(?<name>)`, never `(?P<name>)`), whole-line single-capture matching, field naming, and why the timestamp settings matter more than the fields |
| `CIMPlicityCIMMapping` | Choosing a data model from what events mean, confidence thresholds, many-to-one mappings, and that a field mapping alone does not make data appear in a data model |
| `CIMPlicityOnboardingWorkflow` | The order to drive the tools in: ping, sample, PII scan, extract, re-check against other samples, map, emit props/transforms |

They are deliberately small. Splunk's own managed skills run 2.7 KB to 4.2 KB, and skill
text is resent on **every** agent turn, so length is a recurring token cost. A test caps
each at 4 KB.

The content lives in `SKILLS` in `ucc-app/lib/aitk_skills.py`, next to the code that
ships it, mirroring how `TOOLS` works in `autoregister.py`.

## How registration works

It rides the existing trigger. `app.conf [triggers] reload.tools = http_post
/cim-plicity/autoregister` already fires on every app-state change, and
`autoregister.py` now does both halves: the MCP tool registration and the skills. Unlike
the MCP KV upsert, **skills registration runs on Cloud and Enterprise alike**, and
no-ops quietly when the AI Toolkit is not installed.

To re-run just the skills, which is the path that matters when a customer installs the
AI Toolkit *after* this app:

```
curl -k -u admin:changeme -X POST https://localhost:8089/services/cim-plicity/register_skills
```

```json
{"ok": true,
 "skills": {"action": "registered",
            "results": [{"name": "CIMPlicityFieldExtraction",
                         "created": 201, "updated": 200, "ok": true, "error": null}]}}
```

`action` is `registered`, or `skipped` with a reason when there is no Toolkit.

## Three things that are not obvious

Each of these cost a probe round to find, and any one of them silently breaks
registration. They are pinned by tests in `tests/test_aitk_skills.py`.

**1. Only the `splunk-system-user` namespace works.** Every skills route calls
`validate_and_add_user_info`, which compares the URL's namespace user against the user
the token resolves to and raises on a mismatch. The handler flattens that into a bare
500, so it reads like a privilege problem and is not:

| URL | Result with a system token |
|---|---|
| `/servicesNS/admin/…` | 500, `splunk-system-user != admin` |
| `/servicesNS/nobody/…` | 403, validation is skipped for `nobody` so capabilities never load and the `edit_agent_connections` check fails |
| `/servicesNS/splunk-system-user/…` | **201** |

**2. Creating a skill is not enough: it is invisible.** `SkillManager.create_skill`
hard-codes `acl = {sharing: "owner", owner: <caller>, perms: {read: [], write: []}}` and
**ignores any `acl` in the POST body**. `list_skills` then filters every row through
`is_user_eligible_by_role`, which returns `False` outright when `sharing == "owner"` and
the caller is not the owner. So a skill created by `splunk-system-user` sits in KV where
no real user can list, read or delete it. A follow-up `PUT` widens the ACL to
`sharing: "global"` with `perms.read: ["*"]`.

The `PUT` must keep `owner` as `splunk-system-user`: `is_user_eligible_by_role`
short-circuits on `user == acl["owner"]`, and that is what lets the next upgrade rewrite
its own skill. It also requires `name` in the body (the handler rejects `name` as an
*update* field but demands it as an identifier).

**3. The Toolkit's REST handler intermittently answers `bad character (49) in reply
size`.** Usually on the first request after a splunkd restart, and not route-specific,
so every call retries past it rather than reporting it.

Worth knowing what that string actually means, because it is easy to misread: it is
splunkd failing to parse a **persistent handler's reply**, ie the handler did not
produce a valid chunked response. A *persistent* occurrence means the handler errored at
startup, almost always a failed import. A *transient* one means it was not ready yet.
Only the transient kind is worth retrying, and a handler that returns it on every call
needs its own log read, not another attempt.

## Idempotency

`POST` then `PUT` on every run: `POST` returns 201 on a fresh install and 409 once the
skill exists (both fine), and the `PUT` refreshes `description`, `category` and
`skill_text` so an upgrade ships new wording, while also setting the ACL so a
first install becomes visible. Re-running produces no duplicates.

## Verified

End to end against **AI Toolkit 6.1.0 on Splunk Enterprise 10.4.0 with no Splunk Cloud
Connect**, so this works on-premises as well as on Cloud: three skills created (201),
made visible (200), listed by a real user with `sharing: global`, and a re-run returning
409/200 with the count unchanged.

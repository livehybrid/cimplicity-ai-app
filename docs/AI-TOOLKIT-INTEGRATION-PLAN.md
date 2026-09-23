# AI Toolkit integration + prompt externalisation — investigation and plan

**Status:** investigation complete; **Phases 0, 1 and 2 built and verified**. Skill
self-registration ships (§3F, [AI_TOOLKIT_SKILLS.md](AI_TOOLKIT_SKILLS.md)), the LLM call is behind
one seam (`lib/llm_client.py`), and the AI Toolkit is a selectable backend **defaulting to direct**,
so nothing changes for an existing install. What remains open is whether to ever make it the
default, and §7 below is the evidence against.
**Date:** 2026-09-21, updated 2026-09-24.

Two questions were asked:

1. Can CIMPlicity use the Splunk **AI Toolkit** (the app formerly known as MLTK) for its LLM
   access, instead of carrying its own API-key/endpoint/model configuration page? There is an
   `ai` search command, are there also endpoints or library access?
2. Can the **prompts be lifted out of the code** so a customer can configure them, from the
   settings page or a macro?

Everything in sections 1, 2, 2b and 3 was checked against live Splunk instances or published
package metadata, not assumed.

**Answers in one line each.** No REST inference endpoint exists (§2). The `splunklib.ai` library is
gated on Python 3.13 and drags in langchain, and would still need a customer API key (§3C). `| ai`
does work as a chat completion and is the only route to key-free Splunk Hosted Models, at roughly
10x the latency (§2b, §3A). An app cannot register itself as an agent, though it can register
skills (§3E). Shipping CIMPlicity *as* agents is the most interesting end state and the one with
the worst prerequisite chain, so it belongs as a second surface rather than a backend (§3F).

---

## 1. What was verified

| Fact | Evidence |
|---|---|
| **AI Toolkit == `Splunk_ML_Toolkit`** | app id is unchanged; 6.x is the "AI Toolkit" branding |
| Two instances differ materially | `.222` (Will's Enterprise) = **5.6.4**; SplunkTrust Cloud = **6.1.0** |
| `ai` command exists on **both** | `conf-commands` on both instances; `ai` → `ai.py`, chunked, python3 |
| `aiagent` + `agentstatus` are **6.x only** | present on SplunkTrust, **ABSENT on .222** |
| `ai` needs a configured model | running it on .222 fails: `FATAL Error in 'ai' command: No default model was found.` |
| LLM connections live in **KV**, not conf | `aitk_llm_connection` collection on 6.1; **no `aitk_*` collections on .222** |
| `mlspl.conf` `ai:*` stanzas are tuning only | `ai:LLMIntegrations`, `ai:AgentIntegrations`, `ai:AllowedDomains` hold retries/timeouts/limits, no credentials |
| **A REST handler exists, but exposes no inference route** | `btool restmap list --app=Splunk_ML_Toolkit --debug` shows `[script:mltk]`; its route table serves agent, skill and vector-store management only (see §2) |
| `\| ai` **works as a chat completion**, result in `ai_result_1` | `\| makeresults \| ai prompt="say OK"` → `ai_result_1="OK"` on the 6.1 stack |
| Its parameters are **only** `prompt`, `connection`, `provider`, `model` | every other name rejected with `Param name <x> is not allowed` (§2b) |
| The prompt is **`str.format()`-ed against the event's fields** | `{ok}` → `FATAL 'ok'`; `{{ok}}` and `{_raw}` both work (§2b) |
| **`splunklib.ai` needs Python 3.13 and langchain** | `splunk-sdk` 3.0.1 `[ai]` extra, `requires_python >=3.13`, hard `ImportError` in `splunklib/ai/__init__.py` (§3C) |
| **Agents cannot be created by an app**, skills can | `POST /mltk/agents` → 500; KV row invokes as `Agent Does not exist.`; `POST /mltk/agent_skills` → 200 (§3E) |

### What a connection looks like (`aitk_llm_connection`)

```json
{ "name": "OpenAI_GPTOSS_120B", "provider": "Splunk Hosted Models",
  "model": "OpenAI GPT-OSS 120B", "is_custom": false,
  "connection_details": { "request_timeout": 200, "model_id": "..." },
  "default_users": ["*"],
  "llm_params": { "max_tokens": 2000, "reasoning_effort": "MEDIUM",
                  "response_variability": 0, "maximum_result_rows": 10 },
  "acl": { "sharing": "private", "app": "SPLUNK_ML_TOOLKIT", "owner": "..." } }
```

Providers actually configured on the 6.1 stack:

- **`Splunk Hosted Models`** → `OpenAI GPT-OSS 120B` — **no customer API key involved at all**.
- **`OpenAI`** → `anthropic/claude-sonnet-5`, `anthropic/claude-opus-5`, `gpt-5`, `splunk-aios`.
  Note this provider is an *OpenAI-compatible* one and is already carrying OpenRouter-style model
  ids. **That is exactly what CIMPlicity does today**, so our current setup maps onto an AITK
  connection one-for-one.

### What else the Toolkit brings

- **Governance we currently have none of**: `ai_access_profiles`, `ai_access_assignments`,
  `ai_quotas`, `ai_usage`, `ai_key_lifecycle`. Central key lifecycle, per-user quotas and usage
  accounting. This is the strongest non-obvious argument for delegating.
- **Agents** (`aitk_agent_collection`): each version carries a `system_prompt` and `task_prompt`,
  plus attached MCP servers, edited in Agent Launchpad.
- **MCP** (`aitk_mcp_collection`): the Toolkit already consumes MCP servers. CIMPlicity already
  *publishes* MCP tools, so an AITK agent can call our tools — the two halves meet.
- **Local models are supported**: the `ai` command's own example is
  `ai provider=local_ollama;model::llama8b prompt="..."`, which also answers the recurring
  "can we use a local LLM" question.

### Command surface

```
| ai [provider=<p>;model::<m>] [prompt="... {field} ..."]     # default prompt: "Explain and summarize this data: {_raw}"
| aiagent agent_name='myAgent' prompt="... {_raw}"            # 6.x only
| agentstatus agent_name='myAgent' action='create'            # 6.x only
```

---

## 2. The REST surface — corrected

An earlier pass concluded "there is no REST API at all". **That was wrong**, and `btool` proved it.
`| btool restmap list --app=Splunk_ML_Toolkit --debug` returns a real handler:

```ini
[script:mltk]
match            = /mltk
script           = util/rest_handler.py
scripttype       = persist
output_modes     = json
passPayload      = true
passSystemAuth   = true
requireAuthentication = true
python.required  = 3.13
```

The earlier `/services/mltk → 500` was a live handler rejecting an empty request, not an absent one.
(The `admin/restmap` ACL view had reported zero MLTK-owned stanzas, which is why the first pass
missed it — btool reading the conf files on disk is the reliable check.)

**However, the route table is agent, skill and vector-store *management*, not inference.** The
handler answers `Unknown REST endpoint: <name>` for invalid routes, so the table can be mapped
exactly. Two call conventions are required or every route looks broken:

1. the **user namespace**, `/servicesNS/<user>/Splunk_ML_Toolkit/mltk/...`, not `/services/` and not
   `nobody`
2. **`--http1.1`**, or the GET dies with `bad character (49) in reply size`, a chunked-encoding
   artefact that reads like a server error and is not

| Route | Result |
|---|---|
| `/mltk/agents?agent_type=aitk` | **GET 200**, lists agents (reads `aitk_agent_collection`) |
| `/mltk/agents` | POST → 500 for every payload shape; DELETE accepted |
| `/mltk/agent_skills` | **GET and POST 200**, skills are creatable over the API |
| `/mltk/agent_templates` | **GET 200**, returns the templates Splunk ships |
| `/mltk/vector_stores` | exists |
| `llm`, `llm_connections`, `connections`, `models`, `chat`, `completions`, `inference`, `tools`, `prompts`, `usage`, `quotas` | `Unknown REST endpoint` |

An earlier probe reported 405s on `agents`; that was the missing namespace and `--http1.1`, not the
route. The conclusion is unchanged and now rests on a correct measurement: **there is no REST
inference or chat-completion endpoint.** LLM access is reachable only through the `ai` / `aiagent`
search commands, so "use the AI Toolkit" means dispatching a search from our REST handler and
parsing the result, which is a different shape from our current direct HTTPS call.

One useful detail falls out of the handler definition: `python.required = 3.13` is on *their*
handler. Calling `/mltk` over HTTP from our py3.9 handler would have been fine. It does not help
here only because no inference route exists, not because of a Python constraint.

### LLM connections are not creatable over REST either

`aitk_llm_connection` is a KV collection with no REST route in front of it. The Launchpad UI writes
it directly. Seven connections exist on the 6.1 stack, all with `llm_params.max_tokens = 2000` and
`maximum_result_rows = 10`. Since `| ai` takes no `max_tokens` argument (see §2b), **a connection's
`max_tokens` is a hard ceiling on any reply CIMPlicity can get through the Toolkit**, and only the
customer can raise it, in the Toolkit UI.

---

## 2b. The `| ai` contract, measured

Run against the 6.1 stack on 2026-09-21. This is the part that was previously assumed.

**The complete parameter allowlist is `prompt`, `connection`, `provider`, `model`.** Everything else
is rejected with `Param name <x> is not allowed`: no `max_tokens`, no `temperature`, no
`system_prompt`, no `response_format`, no `timeout`, no output-field control. `model` and `provider`
must be given together. Result lands in **`ai_result_1`**.

**The prompt is run through Python `str.format()` against the event's fields.** This is the single
finding that decides how the integration has to be built:

| Prompt | Outcome |
|---|---|
| `"reply with exactly {ok}"` | **FATAL** `Error in 'ai' command: 'ok'` (a `KeyError`) |
| `"reply with exactly {{ok}}"` | works, model receives `{ok}` |
| `... \| eval widget="ZEBRA" \| ai prompt="repeat: {widget}"` | works, returns `ZEBRA` |
| `... \| eval _raw="badge=BK-88412 ..." \| ai prompt="name the badge in: {_raw}"` | works, returns `BK-88412` |
| `"repeat: {nosuchfield}"` | **FATAL** `'nosuchfield'` |
| a value containing braces, substituted via `{field}` | **safe**, substituted values are not re-scanned |

So every literal brace in a prompt is a landmine, and both CIMPlicity prompts are full of them: they
show the model a JSON schema. Worse, `ai_detection` injects the **customer's raw event** into the
prompt, and any event containing `{` would have killed the search.

**Both problems are solved by the same move: pass data as fields, not inside the prompt literal.**
Static template text doubles its braces; every variable goes in via `| eval` and is referenced as
`{field}`. Because substituted values are not re-formatted, a customer's JSON log is then safe by
construction. The command's own default prompt (`"Explain and summarize this data: {_raw}"`) shows
this was the intended usage all along.

### Phase 0 spike: PASSED

Both real prompts were rebuilt in that shape and run end to end, and both replies parsed with the
app's existing tolerant parser (`lib/llm_response.py`), unchanged:

| Case | Data in | Reply | Parsed |
|---|---|---|---|
| `cim_mapping` (Authentication, 44 CIM fields, 12 extracted fields) | 1205 chars over 3 fields | 1734 chars | **10 mappings** |
| `ai_detection` (raw event containing a literal `{"zone":"secure"}`) | 216 chars | 1174 chars | **13 fields**, correct `(?<name>)` syntax |

Strict JSON round-trips through `| ai`. **Option A is viable.**

### The cost is latency

| Call | `runDuration` |
|---|---|
| `\| makeresults \| ai prompt="say OK"` | **~16 s** |
| `cim_mapping`, default connection (Splunk Hosted, GPT-OSS 120B, reasoning MEDIUM) | **84.6 s** |
| `cim_mapping`, `connection="livehybridsonnet"` (OpenAI-compatible, claude-sonnet-5) | **29.4 s** |
| `cim_mapping`, our current direct HTTPS call on claude-sonnet-5 | **~3 s** |

A trivial prompt costs ~16 s, so that is fixed overhead: search dispatch plus a chunked py3.13
command start plus connection lookup, before any token is generated. Same model, same prompt, the
Toolkit path is **roughly 10x slower** than the direct call. For a UI that already felt slow enough
to warrant an event picker, that is the material objection to option A, not JSON fidelity.

Also worth knowing: `| ai connection=<name>` only resolves connections shared with the caller.
`OpenAI_GPTOSS_120B` (`default_users: []`) failed with `No configuration found for llm connection`
while `livehybridsonnet` worked, so connection visibility is a per-user concern the app must
degrade around.

---

## 2c. Where the AI Toolkit stores what

Traced through the 6.1 source on .222 and confirmed empirically. **Nothing the REST API accepts is
written to a `.conf` file.** It is all KV store documents plus `storage/passwords` entries.

### The dispatch path

`restmap.conf [script:mltk]` points at one generic dispatcher, `bin/util/rest_handler.py`. It takes
the first path segment, imports `rest_handlers.<segment>` and calls the title-cased class:

```
POST /servicesNS/<user>/Splunk_ML_Toolkit/mltk/agent_skills
  -> rest_handlers/agent_skills.py                      class AgentSkills.handle_post
  -> util/searchinfo_util.searchinfo_from_request(with_admin_token=True, validate_token=True)
  -> ai_commander.AICommanderUtil.check_capabilities_eligibility (edit_agent_connections)
  -> connection_config_manager/skills/skill_manager.py   SkillManager.create_skill
  -> util/ai_commander_util.upsert_single_document_into_kv_store
  -> util/rest_url_util.make_kvstore_url(namespace="app")
  -> POST /servicesNS/nobody/Splunk_ML_Toolkit/storage/collections/data/aitk_agent_skills
```

`namespace="app"` resolves the user to the literal `nobody`, so **every AI Toolkit object lands in
the app namespace, not the caller's**. The write itself uses the caller's `session_key`
(`with_admin_token` defaults to `False`), which is why identity matters throughout.

### The map

| What | Where | Notes |
|---|---|---|
| Skills | KV `aitk_agent_skills` | the row IS the skill, no side registration |
| Agents | KV `aitk_agent_collection` | row alone is inert, runtime is cloud-provisioned |
| LLM connections | KV `aitk_llm_connection` | row alone is inert |
| LLM secrets | `storage/passwords` realm **`aitk_llm_secrets`**, id `aitk_llm_secrets:<connection name>` | `handle_secrets()` default realm is `mltk_llm_tokens` |
| Knowledge-base secrets | `storage/passwords` realm `aitk_vector_db_creds` | |
| MCP connections | KV `aitk_mcp_collection` | secret held by reference, eg `mcp_token:<name>` |
| Vector stores | KV `aitk_vector_store_collection` | |
| Managed skills (Splunk's own) | KV `aitk_managed_skills` + `aitk_managed_skills_sync_state` | synced from a cloud catalogue via SCC |
| Chat threads, templates, tiers | `aitk_agent_chat_threads`, `aitk_agent_templates`, `aitk_agent_template_manifest`, `aitk_ai_tier_settings` | |

All thirteen are declared in `default/collections.conf` as **bare stanzas with no field
definitions**, so they are schemaless.

### Two consequences worth holding on to

1. **None of this is deployable as an app.** It is not in `etc/apps/*/local`, so it cannot be
   shipped in a package, pushed by a deployment server, or captured by a conf backup. On a search
   head cluster it travels by **KV store replication**, not conf replication. Anything CIMPlicity
   wants present has to be *written at runtime* through one of the paths above.
2. **The `acl` field is data, not enforcement.** The collections live in the `nobody` namespace, so
   the `acl` object inside each document is applied only by the handler's own
   `is_user_eligible_by_role` check. Anyone who can read the KV collection directly bypasses it
   entirely: `GET /servicesNS/nobody/Splunk_ML_Toolkit/storage/collections/data/aitk_agent_skills`
   returns every skill regardless of ownership. Do not treat AI Toolkit ACLs as a security boundary.

### Confirmed empirically

```
POST /servicesNS/admin/Splunk_ML_Toolkit/mltk/agent_skills   -> 201
GET  /servicesNS/nobody/…/storage/collections/data/aitk_agent_skills
     -> 1 row, _user=nobody, _key=6ab30079fb3021fdc903608b
        created_by=admin, acl.owner=admin, acl.sharing=owner
GET  /servicesNS/admin/…/storage/collections/data/aitk_agent_skills   -> 0 rows
GET  /servicesNS/nobody/search/storage/collections/data/aitk_agent_skills
     -> 404, the collection is scoped to the Splunk_ML_Toolkit app
```

---

## 3. Options

### A. `| ai` via a dispatched search  — *recommended path*

Handler builds the prompt, dispatches a oneshot search through `| ai`, reads `ai_result_1`.

- Works on **5.6.4 and 6.x**, so it does not strand .222.
- Uses the AITK connection, so **the customer's key (or no key at all) is managed in one place**.
- Unlocks **Splunk Hosted Models**, ie no customer API key, which is a genuinely better story for
  a Splunkbase app than "bring your own OpenRouter key". This is the **only** one of the four
  options that reaches hosted models.
- No Python-version change.
- **Proven** (§2b): strict JSON round-trips, and customer data containing braces is safe provided
  it is passed as a field rather than inlined in the prompt.
- Residual risks, now quantified: **~16 s of fixed overhead per call** and roughly 10x the latency
  of the direct call on the same model; the connection's `llm_params.max_tokens` (2000 on every
  connection seen) is an unraisable ceiling from our side; connection visibility is per-user.

### B. `| aiagent`

- **6.x only**, so .222 must be upgraded first.
- Prompts live in the agent (`system_prompt` / `task_prompt`) and are edited in Agent Launchpad,
  which solves question 2 almost for free.
- Agents can carry MCP tools, including ours.
- Heavier: agentic runtime, per-customer agent provisioning, async status polling.

See **§3F**, which takes this much further: shipping CIMPlicity *as* a set of agents.

### C. `splunklib.ai` SDK in the handler

Native Python, no SPL marshalling. Checked properly this time, against the published package.

**What it actually is.** `splunklib.ai` ships in **`splunk-sdk` 3.0.1** under the `[ai]` extra. We
currently pin `splunk-sdk==2.1.1`, which does **not** contain it. The package metadata is decisive:

```
requires_python: >=3.13
[ai]        httpx==0.28.1, langchain>=1.3.15, mcp>=1.28.1,<2.0.0, pydantic>=2.13.4
[openai]    + langchain-openai>=1.5.1        [anthropic] + langchain-anthropic>=1.5.6
[google]    + langchain-google-genai==4.3.4, google-auth>=2.56.3
```

and `splunklib/ai/__init__.py` opens with a hard gate:

```python
if sys.version_info < (3, 13):
    raise ImportError("Python 3.13 or newer is required to use this module")
```

**Is the Python version the blocker? Partly, and it is smaller than it looks.** `python.required`
is set **per stanza** in `restmap.conf`, not per app, and only `pii_detection` genuinely needs 3.9:
it is the one that imports `scrubadub` and so drags in `nltk` / `scipy` / `scikit-learn`.
`ai_detection`, `cim_mapping`, `ai_model_choices`, `autoregister` and the settings handler import
nothing beyond `solnlib`, `requests` and the stdlib; their 3.9 pin is inherited by convention, not
by dependency. UCC already supports splitting libraries by interpreter and **this app already does
it**: `globalConfig.json` carries `os-dependentLibraries` with `python_version: "3.9"` and
`target: "3rdparty/linux_lib_py39"` for `regex` and `numpy`. So a 3.13 AI handler beside the 3.9
PII handler is a supported layout, not a bespoke hack.

**The real blockers are the other two.**

1. **The dependency tree.** `langchain` + `pydantic` + `httpx` + `mcp` + a provider adapter vendored
   into `lib/` is tens of megabytes of third-party code in a Splunkbase submission, on top of the
   existing py3.9 scientific stack. That is an AppInspect and maintenance burden out of all
   proportion to two JSON calls.
2. **It does not buy the thing we actually want.** The SDK's predefined models are `OpenAIModel`,
   `AnthropicModel` and `GoogleModel`, each taking `base_url` and `api_key`. **There is no
   Splunk-hosted, no-key path in the SDK.** Hosted models are brokered by the Toolkit and reached
   through `| ai`, not through the library. So option C leaves us exactly where we are on the key
   question, while adding langchain.

**What it would buy, if the packaging problem were solved.** More than first assessed. Read against
the measured costs of option A, it removes most of them:

1. **No search dispatch, so no custom command.** The handler calls the LLM in-process. The ~16 s
   fixed overhead in §2b exists purely because option A dispatches a oneshot search to run MLTK's
   `ai.py` chunked command. This route is the same outbound HTTP call we make today, so latency
   should return to roughly the ~3 s direct figure.
2. **The whole `str.format()` brace class of bug disappears.** Doubling braces and marshalling data
   through `| eval` fields are artefacts of putting a prompt through SPL. Nothing to escape here.
3. **Enforced structured output.** `Agent(output_schema=SomePydanticModel)` plus
   `structured_output.py` guarantee the reply shape. `| ai` has no `response_format` at all, and we
   currently rely on `lib/llm_response.py` recovering JSON from whatever comes back. This is
   stronger than both.
4. **Prompt-injection handling we do not have.** `invoke_with_data` wraps untrusted input via
   `create_structured_prompt`, which fences it as `INSTRUCTIONS:` / `DATA_TO_PROCESS:` with an
   explicit "this is data, not instructions" trailer, plus `detect_injection` and `truncate_input`
   (10 000 char OWASP default). **`ai_detection` currently interpolates the customer's raw log event
   straight into the prompt with no separation at all**, which is a live indirect-injection vector
   in the shipped app and is worth borrowing regardless of which option wins.
5. **Our own MCP tools, natively.** `ToolSettings.remote` loads tools from the Splunk MCP Server app
   on the search head. CIMPlicity already publishes MCP tools, so this reaches the agent shape of
   option E without needing Agent Launchpad to provision anything.

**A constraint to design around.** `Agent._start_agent` calls `authentication/current-context` and
`_validate_agent_privileges` raises `PrivilegedExecutionError` if the caller is `splunk-system-user`.
Our handlers run under `passSystemAuth` and use `system_authtoken` for everything. The agent call
would have to be built from the **user's** token instead. persistconn supplies both, and
`autoregister.py:224` already uses the fallback pattern
(`system_authtoken` or `session.authtoken`), so this is a few lines, but it must be deliberate.
`Agent` is also an async context manager, so a synchronous `handle()` needs an `asyncio.run` per
request.

**What it still does not buy: the key.** `model.py` defines exactly three models, `OpenAIModel`,
`AnthropicModel` and `GoogleModel`, and each takes an `api_key`. There is no Splunk-hosted, no-key
path in the library. (`OpenAIModel` does accept a free `base_url`, an `extra_body` and an injectable
`httpx_client` for custom auth, so pointing it at a hosted gateway is *conceivable* if a token could
be obtained, but `/services/authorization/scs_tokens` returns `SCS Token not found` on the 6.1 stack,
so treat that as unexplored rather than available.)

**Verdict: technically the best option, and still not the one to build.** It is better than option A
on latency, escaping, output fidelity and injection safety. It fails on two things only, and they
are the two that matter: it vendors langchain, pydantic, mcp and httpx into a Splunkbase package
on top of the existing py3.9 scientific stack, and **it does not remove the customer API key, which
was the entire reason for looking at the AI Toolkit**. Keep it on the table if that motivation
changes, or if Splunk later publishes a hosted-model backend for the SDK.

### D. Borrow the connection's credentials, keep our direct HTTPS call

Read `aitk_llm_connection` and reuse provider/model, keeping our own HTTP client.

- Tempting and cheap, **but it cannot reach `Splunk Hosted Models`**, which is the main prize:
  there is no key to borrow, the Toolkit brokers that access itself. It also bypasses the quota
  and usage accounting. Worth it only as a transitional nicety, not as the destination.

### E. Register CIMPlicity itself as an AITK agent

Attractive in principle: the agent owns the prompts, the model and the key, and CIMPlicity supplies
the tools. It fails on one fact and then becomes something else.

**An app cannot create an agent.** Verified two ways on the 6.1 stack:

- `POST /mltk/agents` returns **500 `Failed to create agent`** for every payload shape tried, under
  both token and session-key auth, so it is not a permissions problem.
- Writing a well-formed row straight into `aitk_agent_collection` **succeeds** and the agent then
  appears in listings, but invoking it returns `status="error"`,
  `result_1="Agent Does not exist."`

The reason is in the record: `runtime_type` is `AWS_AGENT_CORE` with a server-provisioned
`runtime_params.runtime_id` and `memory_params.memory_id`. The runtime is provisioned cloud-side by
Splunk, not by the KV row. **Agent creation is a UI action in Agent Launchpad**, so a Splunkbase app
can neither ship an agent nor create one on install.

**What an app *can* register is a skill.** `GET`/`POST /mltk/agent_skills` both return 200, and
skills take `{name, category, skill_text, description}`. Combined with the MCP side, that gives a
real but *inverted* integration:

> CIMPlicity ships its onboarding know-how as AITK **skills**, and exposes `ai_detection` and
> `cim_mapping` as **MCP tools** (which it already does). A customer builds an agent in Launchpad,
> attaches our skills and our MCP tools, and the agent does data onboarding conversationally.

That is a good product story and it composes with work already finished. It is **not** a substitute
for options A to D, because the direction of the call is reversed: the agent calls us. It does
nothing for the Data Input page, which needs a synchronous answer from a button press. Treat it as a
separate feature, not as the LLM-access decision.

---

### F. Ship CIMPlicity *as* agents (skills + MCP tools + a customer connection)

The Buildathon shape: rather than CIMPlicity calling an LLM, CIMPlicity becomes skills and tools,
and an agent orchestrates them. Invoked from SPL with `| aiagent agent_name=... prompt=...`.

**The shape is real and already running on the 6.1 stack.** `KillChainSweep` is exactly this:

```json
{ "agent_name": "KillChainSweep", "state": "Available", "agent_timeout": 450,
  "llm": { "provider": "Splunk Hosted Models", "model": "OpenAI GPT-OSS 120B",
           "connection_name": "SplunkLLMGPTOSS120B", "max_tokens": 50000,
           "response_variability": 0, "reasoning_effort": "LOW" },
  "skills": ["SecurityDataFingerprint", "KillChainInstrumentSPL",
             "EvidenceAndReportingContract", "BudgetAndHygiene"],
  "tools": { "mcps": [ { "name": "splunktrust",
                         "tools": ["splunk_run_query", "splunk_run_saved_search", ...] } ] },
  "system_prompt": "<4992 chars>", "task_prompt": "<76 chars>" }
```

**Four things it fixes that no other option does.**

1. **The 2000-token ceiling is gone.** Every agent on the stack carries `max_tokens: 50000` at the
   *agent* level, overriding the connection's 2000. Risk 3 disappears outright, and only here.
2. **Skills answer the prompt-externalisation question better than a conf file.** They are
   API-creatable (`POST /mltk/agent_skills`, verified 200), they are the right size (Splunk's own
   managed skills run 2.7 KB to 4.2 KB), and the customer edits them in a supported Splunk UI
   instead of a CIMPlicity settings page we would have to build and document. §5's mechanism
   becomes a fallback for non-Toolkit installs rather than the primary.
3. **No API key in CIMPlicity at all.** The connection is the customer's. This is the original
   motivation for the whole investigation, and F satisfies it as fully as A does.
4. **`tools.knowledge_bases[]` can hold the CIM models.** Today every `cim_mapping` call inlines the
   full field list for the chosen data model (44 fields for Authentication, far more for Network
   Traffic). As a knowledge base that becomes retrieval instead of prompt bulk.

**What stops it being the primary architecture.**

1. **The agent cannot be shipped, and the prerequisite chain is brutal.** Agents are UI-only (§3E).
   For an **on-premises** customer, Agent Launchpad additionally requires the **Splunk Cloud Connect
   app plus a Splunk-managed tenant created and onboarded through SCC**, after which the AI Toolkit
   is activated for that tenant. So the full chain before CIMPlicity does anything is: AI Toolkit
   6.x → Splunk Cloud Connect → SCC tenant onboarded → LLM connection → MCP connection with a token
   → agent assembled by hand with our skills attached and our tools allowlisted. That is six manual
   steps in front of an app whose entire proposition is that onboarding should be easy.
2. **It is not air-gapped.** SCC onboarding requires outbound connectivity to Splunk-hosted
   services. That removes regulated and isolated on-premises customers completely, and they are a
   meaningful part of the Splunkbase audience.
3. **Latency goes the wrong way.** `| ai` already costs 29 s (§2b). An agent adds tool-calling
   rounds and resends skill text every turn; `agent_timeout` is 450 s on every agent here and
   `commands.conf` sets `maxwait = 1500` for `aiagent`. That is a batch-job shape, not a
   button-press shape.
4. **Failures are silent.** A failed agent run returns `dispatchState: DONE`, `resultCount: 1` and
   `status="error"`, so the search looks entirely successful. Every call site must gate on
   `status="success"` before parsing.
5. **Our two calls are not agentic problems.** Field extraction and CIM mapping are single-turn
   deterministic transformations: no planning, no tool selection, no iteration. Wrapping them in an
   agent buys non-determinism (`response_variability`), a tool loop and a timeout, to solve
   something that is one HTTP request. We want the same regex twice for the same event.

**Where it genuinely wins: the job CIMPlicity does not do today.** "Onboard this source end to end"
is a real agentic problem: sample the index, propose a sourcetype, extract fields, check them
against CIM, write `props`/`transforms`, validate against live data, iterate. That is planning plus
tools plus iteration, and **we already publish the MCP tools it would need**. It is a materially
bigger product claim than the current app makes.

**Verdict: a second product surface, not a backend swap.** Keep the Data Input page synchronous on
A or on today's direct call, and offer the agent as the "onboard a whole source" mode for customers
who already have the Toolkit. Steal one thing from it immediately and unconditionally: **skills as
the prompt store** (see §5).

### F, tested on-premises — AI Toolkit 6.1 on .222, 2026-09-22

Both open questions are now answered. `.222` was upgraded from AI Toolkit 5.6.4 to **6.1.0** on
Splunk Enterprise 10.4.0, with **no Splunk Cloud Connect and no SCC tenant**.

**Q: are skills available on-premises without SCC? YES.** All thirteen `aitk_*` KV collections are
created on a bare Enterprise install (`aitk_agent_skills`, `aitk_agent_collection`,
`aitk_llm_connection`, `aitk_mcp_collection`, `aitk_vector_store_collection`, …), and the routes
answer:

| Route | On-prem, no SCC |
|---|---|
| `GET /mltk/agent_skills` | 200 `{"skills":[],"count":0}` |
| `POST /mltk/agent_skills` | **201 created** |
| `DELETE /mltk/agent_skills/<name>` | 200 deleted |
| `GET /mltk/agents` | 200, empty |
| `GET /mltk/agent_templates` | 200, **empty** (Cloud has 2, so templates sync cloud-side) |
| `GET /mltk/vector_stores` | 200, empty |

So the skills surface is **local**, and §5's "skills as the prompt store" idea is available to
on-premises customers. That was the more important of the two questions and it came back the way we
wanted.

**Q: can an app register skills at install time, under `system_authtoken`? YES, with two
non-obvious requirements.** An earlier pass here concluded "no". That was wrong: it only tried the
`nobody` and `admin` namespaces, and the `admin` one fails for a reason that has nothing to do with
the token's privileges.

The gate is `util/searchinfo_util.validate_and_add_user_info`, which every skills route calls. It
compares the **URL's namespace user** against the user the token resolves to and raises on a
mismatch, which the handler turns into a generic 500:

```python
if username == 'nobody':          # validation skipped entirely
    return
...
if token_username != username:
    raise RuntimeError(f"Token validation failed: token belongs to user '{token_username}' "
                       f"but searchinfo specifies user '{username}'")
```

That explains all three outcomes exactly, with the system token:

| Namespace | GET | POST | Why |
|---|---|---|---|
| `/servicesNS/admin/…` | 500 | 500 | `splunk-system-user != admin`, so validation raises |
| `/servicesNS/nobody/…` | 200 | **403** `Missing required capabilities` | validation skipped, so `searchinfo['capabilities']` is never populated and the `edit_agent_connections` check fails |
| `/servicesNS/splunk-system-user/…` | 200 | **201 created** | namespace user matches the token user, capabilities load, check passes |

`handle_get` performs no capability check at all and still failed on the `admin` namespace, which is
what isolates this to token validation rather than privilege.

**But creating it is not enough: the skill is invisible.** `create_skill` hard-codes the ACL and
**ignores any `acl` supplied in the POST body**:

```python
"acl": {"sharing": "owner", "app": "SPLUNK_ML_TOOLKIT", "owner": self.username,
        "perms": {"read": [], "write": []}}
```

and `SkillManager.list_skills` filters every row through
`CommonUtils.is_user_eligible_by_role(skill["acl"], "read")`, which returns `False` outright when
`sharing == "owner"` and the caller is not the owner. So a skill created by `splunk-system-user`
sits in KV and **no real user can list, read or delete it**. Verified: admin saw `count: 0` while
the row was plainly present in the collection.

**Both ways of fixing the ACL work, and either completes the recipe:**

| Route | Result |
|---|---|
| **A (supported)** `POST /servicesNS/splunk-system-user/…/agent_skills`, then `PUT …/agent_skills/<name>` with `{"name": …, "acl": {"sharing": "global", "perms": {"read": ["*"]}}}` | 201 then 200, then **visible to admin** |
| **B (direct)** `POST /servicesNS/nobody/…/storage/collections/data/aitk_agent_skills` with the open ACL inline | 201, **visible to admin** |

Route B works because, unlike agents and LLM connections, **a skill has no side registration**: the
handler reads the KV collection directly, so the row *is* the skill. `acl` is also in the handler's
`UPDATABLE_FIELDS`, which is why route A's `PUT` is allowed (note it requires `name` in the body).

**Consequence for F: install-time registration is viable after all.** An `app.conf [triggers]` hook
in the `autoregister.py` mould can publish CIMPlicity's skills on install, exactly like the MCP tool
registration we already do. It must use the `splunk-system-user` namespace and must set a
non-`owner` ACL, or the skills exist but are invisible.

**BUILT, 2026-09-23.** `ucc-app/lib/aitk_skills.py` plus a second leaf on `autoregister.py`, riding
the existing `reload.tools` trigger so no new wiring was needed, with
`POST /services/cim-plicity/register_skills` as the re-run path for a customer who installs the
Toolkit after the app. Three skills ship: `CIMPlicityFieldExtraction`, `CIMPlicityCIMMapping`,
`CIMPlicityOnboardingWorkflow`. Verified end to end on .222 (201 created, 200 made visible, listed
by a real user, re-run 409/200 with no duplicates). 12 tests in `tests/test_aitk_skills.py`.
Details in [AI_TOOLKIT_SKILLS.md](AI_TOOLKIT_SKILLS.md).

**Two further findings while it was installed.**

1. **`| ai` and `| aiagent` both dispatch on-prem without SCC.** They fail on *missing configuration*,
   not on entitlement: `No default LLM configuration found` and `Agent 'nope' not found`. So the
   command layer is not gated behind tenant onboarding; only Splunk Hosted Models and (per Splunk's
   docs) the Agent Launchpad UI are.
2. **A hand-written `aitk_llm_connection` KV row is not enough.** Inserting one returns 201 and the
   row is readable, but `| ai connection=probe_dummy` still answers
   `No configuration found for llm connection`. Exactly the trap already known for agents: the
   Toolkit registers a connection through its own path (which also stores the secret in
   `storage/passwords` under realm `aitk_llm_secrets`, see §2c), and the KV record alone is inert.
   **Skills are the exception**: they have no side registration, so a direct KV write does work.
3. **Installing 6.1 on-prem starts a recurring error loop in `mlspl.log`.** A modular input tries to
   sync Splunk's managed-skills catalogue every ~12 minutes, retries six times with backoff and
   gives up with `Managed Skills synchronization failed after 6 attempts: Splunk Cloud Connect app
   is not installed or endpoint not found`. It is harmless (it logs
   `the existing KV Store catalog is retained`) but it is permanent log noise on any on-premises
   install without SCC, and worth knowing before recommending the Toolkit to a customer.

**ANSWERED 2026-09-23: yes.** A bring-your-own-key `OpenAI` connection can be created and tested on
Splunk Enterprise 10.4.0 with AI Toolkit 6.1 and **no Splunk Cloud Connect**. `mlspl.log` on .222:

```
INFO [mlspl.connection_config_manager.llm.config_manager] [test_llm_connection]
  Connection test succeeded for connection='OpenAI', provider='OpenAI', model='gpt-4o'.
```

So **option A is available to on-premises customers with their own key**, not Cloud-only. Only
Splunk Hosted Models and the Agent Launchpad UI need SCC.

### The GPT-5 trap on the way there

`gpt-5` and `gpt-5-mini` both **fail** the connection test:

```
litellm.BadRequestError: OpenAIException - Unsupported parameter: 'max_tokens' is not
supported with this model. Use 'max_completion_tokens' instead.
```

This is a stale pinned dependency, not an OpenAI surprise. LiteLLM does **not** ship inside the AI
Toolkit; it comes from **PSC** (`Splunk_SA_Scientific_Python_linux_x86_64`), at version **1.73.6,
released 2025-06-28**, which predates GPT-5 by weeks. The current LiteLLM is 1.102.1.

The rename is gated on a hardcoded prefix list, so a registry refresh alone would not fix it:

```python
def is_model_o_series_model(self, model: str) -> bool:
    model = model.split("/")[-1]
    return model in litellm.open_ai_chat_completion_models and any(
        model.startswith(pfx) for pfx in ("o1", "o3", "o4")
    )
```

`gpt-5` fails **both** halves: it is absent from the shipped 1140-model registry (which does carry
`gpt-4.1`, `gpt-4.5-preview` and `o3-pro`), and it does not start with `o1`/`o3`/`o4`. So the
`max_completion_tokens` rename never runs, `max_tokens` goes out as-is, and OpenAI rejects it.
Every `aitk_llm_connection` carries `llm_params.max_tokens`, so there is no way to avoid sending it.

**What to use instead:** `gpt-4o` (verified working), an o-series model such as `o3` or `o4-mini`
(in the registry *and* matched by the prefix list, so the rename fires correctly), or an
OpenAI-compatible `base_url` such as OpenRouter, where `max_tokens` is accepted as-is. This is what
the `livehybridsonnet` connection on the Trust stack does, and it is the one benchmarked at 29.4 s
in §2b.

**Implication for CIMPlicity:** if we ever recommend the Toolkit to a customer, the model choice is
constrained by whatever LiteLLM version their PSC ships, which they do not control and which lags
well behind the model providers. That is a real argument for keeping the direct-HTTPS backend as
the default. Two
minutes of clicking, and worth doing before any commitment to A.

---

## 4. Proposed plan

**Phase 0 — spike. DONE 2026-09-21, PASSED.** Both real prompts round-trip through `| ai` as strict
JSON against both a `Splunk Hosted Models` connection and an `OpenAI`-compatible one, parsed by the
existing `lib/llm_response.py` (§2b). Two things had to be got right and neither was obvious: the
prompt is `str.format()`-ed, so static braces must be doubled, and all variable data must be passed
as `| eval` fields so that customer data containing braces cannot break the search.

The spike also moved the decision. JSON fidelity was expected to be the risk and it is not.
**Latency is:** ~16 s of fixed overhead per call, and ~10x the direct call on the same model. That
is the number the Toolkit route has to justify, and it is why Phase 2 below makes the backend a
setting rather than a replacement.

**Phase 1 — make the call site swappable (no behaviour change).** Extract the LLM call behind a
small interface (`lib/llm_client.py`) with one implementation being today's direct HTTPS call.
Both handlers already share `lib/ai_settings.py` and `lib/llm_response.py`, so this follows the
established shape. This is worth doing regardless of which backend wins.

**Phase 2 — add the AITK backend.** Second implementation dispatching `| ai`. Selection becomes a
setting: `Direct (API key)` or `Splunk AI Toolkit`, defaulting to direct so existing installs are
untouched. Degrade honestly when the Toolkit is absent or has no default model, exactly as we
already do when no API key is set.

**Phase 3 — agents, later.** Once .222 is on 6.1 and the MCP tool story is being demoed anyway,
evaluate `| aiagent` with CIMPlicity's own MCP tools attached. This is the most interesting
end-state but it is not the first step.

### Prerequisite

**.222 needs MLTK 6.1** to develop or test anything beyond bare `| ai`. It is on 5.6.4 with no
`aitk_*` collections, so Agent Launchpad, connections and `aiagent` simply are not there.

---

## 5. Prompt externalisation

### Current state

Prompts are inline f-strings and are **templates, not static text**:

- `ai_detection.call_openrouter` — assembled from three parts: a base with `{sample_data}`, an
  optional `{description}` block, then a static instruction + JSON-schema block.
- `cim_mapping.call_openrouter` — one block with `{cim_model}`, `{available_cim_fields}` and
  `{extracted_fields}`.

### The design point that matters

Each prompt ends with an **output contract** ("return a single valid JSON object with this exact
structure"). If a customer edits that away, every downstream parser breaks and the app looks
broken rather than misconfigured.

So the prompt must be split in two:

- **Guidance** — the domain instructions. Customer-editable. This is the part worth exposing.
- **Contract** — the required JSON shape and "no text outside the JSON". **Not** customer-editable;
  stays in code and is always appended.

Externalising the whole prompt as one blob would be the easy implementation and the wrong one.

### Mechanism — recommended: a dedicated conf file

`default/cim-plicity_prompts.conf`, overridden by `local/`:

```ini
[ai_detection]
guidance = You are a Splunk expert analysing a log sample to suggest field extractions. \
    The log sample is: {sample_data} ...

[cim_mapping]
guidance = You are a Splunk CIM expert mapping extracted fields onto {cim_model} ...
```

Why this over the alternatives:

- **Proper Splunk layering.** `default/` ships our version, `local/` holds the customer's, and an
  app upgrade does not clobber it. Neither a settings-page value nor a macro gives that as cleanly.
- **Multi-line text is native** (backslash continuation), and these are long.
- Read with the same `conf_manager` path the settings already use — and it inherits the retry
  in `lib/ai_settings.py`, which we added for the Cloud SHC credential race.

**Requirements this carries** (both learned the hard way on `tools.conf`):

- a `README/cim-plicity_prompts.conf.spec`, or AppInspect flags an undocumented custom conf;
- a `[triggers] reload.cim-plicity_prompts = simple` entry in `app.conf`, or edits need a restart.

Placeholders should be validated on read: if a customer's template is missing `{sample_data}`,
fall back to the shipped default and log loudly, rather than sending a prompt with no data in it.

### Alternatives considered

- **UCC settings page (textarea).** Nice discoverability and it is where the AI config already
  lives. But globalConfig text fields carry length validators tuned for short values, conf-stored
  multi-line text is awkward through that path, and there is no default/local layering. Good as a
  *later* addition on top of the conf file, not as the storage mechanism.
- **Macro.** `macros.conf` is customer-editable and upgrade-safe, but macros exist to hold SPL, not
  prose; multi-line prompt text with braces and quotes in a macro definition is a hack. Worth using
  for the *search wrapper* if option A is chosen (a macro that wraps the `| ai` invocation), not
  for the prompt body.
- **AITK agent prompts.** If we ever go to `| aiagent`, `system_prompt`/`task_prompt` live in the
  agent and are edited in Agent Launchpad — customer-configurable for free. That is an argument for
  phase 3, but it only helps on 6.x.

### Sequencing

Prompt externalisation is **independent of the AI Toolkit decision** and lower risk. It can ship
first and benefits the current direct-HTTPS path immediately.

---

## 6. Risks and open questions

1. ~~**JSON fidelity through SPL**~~ — **CLOSED, passed** (§2b). Both prompts round-trip as strict
   JSON once braces are doubled and data is passed as fields.
2. **Latency** — **MEASURED and now the main objection.** ~16 s fixed overhead per call; 29.4 s
   versus ~3 s for the same prompt on the same model direct. This is a UI-blocking call.
3. **Truncation** — **CONFIRMED as a real constraint.** Every connection on the 6.1 stack carries
   `llm_params.max_tokens = 2000` and `maximum_result_rows = 10`, and `| ai` accepts no `max_tokens`
   argument, so the ceiling is the customer's to raise in the Toolkit UI and ours only to detect.
   The `cim_mapping` reply came back at 1734 chars against a 44-field model; a wider model such as
   Network Traffic will be closer to the limit.
4. ~~**.222 is on 5.6.4**~~ — **CLOSED. Upgraded to AI Toolkit 6.1.0 on 2026-09-22**, so `aiagent`,
   `agentstatus` and the whole `aitk_*` surface are now available for development. The 5.6.4 app and
   a tarball of it are kept on .222 under `/tmp` for rollback.
5. **Splunkbase dependency question** — making the AI Toolkit *required* adds a dependency for
   every customer. It should stay optional, with direct-HTTPS as the default.
5b. **The customer's LiteLLM version constrains the model list** — new, 2026-09-23. LiteLLM comes
   from PSC, not the Toolkit; .222's PSC 4.2.4 ships 1.73.6 (2025-06-28) against a current 1.102.1,
   and `gpt-5` fails outright on it (§3F). A customer cannot pick a model newer than their PSC
   knows about, and they do not control that independently of the Toolkit. Argues for keeping
   direct-HTTPS as the default backend.
6. **Who owns the connection** — still open, and §2b sharpened it. `| ai connection=<name>` resolved
   `livehybridsonnet` (`default_users: ['*']` on the working ones) but failed with
   `No configuration found for llm connection` for `OpenAI_GPTOSS_120B` (`default_users: []`).
   Our handlers run under `passSystemAuth`; whether that context resolves a user-scoped default
   connection is unverified and needs checking before phase 2.
7. **Which connection is the default** — bare `| ai` works on the 6.1 stack with no `connection`
   argument, so a default exists, but nothing in `aitk_llm_connection` carries an `is_default` flag.
   How the default is chosen (and what happens when a customer has none) needs pinning down, since
   it determines what CIMPlicity shows when the Toolkit is installed but unconfigured.
8. **Prompt injection, ours today** — surfaced while reading the SDK (§3C) and **not conditional on
   any of this**. `ai_detection` interpolates the customer's raw log event directly into the prompt
   with no separation between instruction and data. A crafted log line can therefore steer the
   model. The SDK's `create_structured_prompt` fence is about fifteen lines to reimplement and
   should be adopted whichever backend wins. Worth raising as its own issue.

---

## 7. Phase 2 as built, and what running it taught

`ai_configuration.backend` selects `direct` (default) or `splunk_ai_toolkit`.
`lib/llm_client.complete()` is the single call site; `lib/llm_toolkit.py` builds and reads the
`| ai` call and `lib/splunk_search.py` runs it as a oneshot search.

### Measured end to end through the app's own endpoints, on .222

Same events, same handlers, only the backend changed.

| Endpoint | Direct (`claude-opus-5`) | AI Toolkit (`\| ai` → `gpt-5-mini`) |
|---|---|---|
| `cim_mapping` | **15.5 s**, 4 mappings | **98.8 s**, 4 mappings |
| `ai_detection` | **59.7 s**, 8 fields from the LLM | **179.6 s**, and it FAILED (fell back to local regexes) |

The Toolkit route is roughly **6x slower** on the call that worked. Some of that is gpt-5-mini
being a reasoning model rather than the transport, but the fixed cost of dispatching a search is
real and was ~16 s on the Cloud stack (§2b).

**SPL length is not a constraint.** The `cim_mapping` prompt produced an **11,832-character search
string** and ran fine, so brace-doubling the whole prompt and inlining it is viable at our sizes;
the field-passing trick from §2b is not required, though it remains the tidier option.

### The failure mode that matters most

**`| ai` reports LLM-level failures by putting the error message in `ai_result_1` and returning a
successful search.** Nothing is flagged: the row looks exactly like an answer. Parse it and you get
an error string where JSON should be.

Found live. `ai_detection` silently fell back to local regexes, and the reply turned out to be:

```
Empty response content received from the server.
```

which is the AI Toolkit's own wording for *the model returned nothing*. Cause: the connection's
`llm_params.max_tokens = 2000` is shared between gpt-5-mini's reasoning tokens and its output, and
the extraction task exhausts it. The bigger `cim_mapping` prompt succeeded, so this is an output
budget problem, not a prompt-size one.

`lib/llm_toolkit.py` now rejects the Toolkit's own `LLM_EXCEPTION_LIST` (lifted verbatim from
`bin/ai_commander/constants.py`) before returning content. **Any caller of `| ai` needs this**, and
nothing in the Toolkit's documentation says so.

### Why direct stays the default

1. **Roughly 6x the latency** on an interactive call, measured.
2. **`max_tokens` is the customer's to set and easy to get wrong.** 2000 is the default on every
   connection seen, `| ai` cannot override it, and on a reasoning model it silently yields an empty
   reply rather than an error.
3. **Connections are per-user.** `default_users` gates visibility and the default-connection mapping
   is per user, so the feature works only for users who personally have one. Our handlers must
   dispatch as the invoking user, which they now do.
4. **The model list is capped by the customer's PSC**, not by them (§3F risk 5b).

None of that argues against *offering* it: a customer who wants one managed key, or Splunk Hosted
Models on Cloud, can now have it, and the seam cost almost nothing. It argues against defaulting to
it.

### Still untested

`| aiagent` and option F's agent half, which need Agent Launchpad and therefore SCC on-premises.
Whether raising a connection's `max_tokens` past 2000 makes `ai_detection` succeed through `| ai`
is the obvious next check and needs a connection edit in the Toolkit UI.

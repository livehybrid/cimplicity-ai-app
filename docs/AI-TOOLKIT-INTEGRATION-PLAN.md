# AI Toolkit integration + prompt externalisation — investigation and plan

**Status:** investigation complete, plan proposed. Nothing implemented.
**Date:** 2026-09-21.

Two questions were asked:

1. Can CIMPlicity use the Splunk **AI Toolkit** (the app formerly known as MLTK) for its LLM
   access, instead of carrying its own API-key/endpoint/model configuration page? There is an
   `ai` search command — are there also endpoints or library access?
2. Can the **prompts be lifted out of the code** so a customer can configure them, from the
   settings page or a macro?

Everything in section 1 was checked against live Splunk instances, not assumed.

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
| **No usable REST inference API** | `/services/mltk` → 500, `/services/aitk` and app-scoped LLM paths → 404; no MLTK-owned `restmap` stanzas |

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

## 2. The uncomfortable finding

**There is no REST or Python inference API.** The Toolkit's LLM access is reachable only through
its **search commands**. So "use the AI Toolkit" concretely means "run a search from our REST
handler and parse the result", which is a different shape from our current direct HTTPS call.

That matters because our two calls are not chat-style summarisation. They send a multi-KB prompt
and demand a **strict JSON document** back. Pushing that through SPL means quoting a prompt that
itself contains `{`, `}`, quotes and regex backslashes, then recovering a JSON blob out of a result
field. That is the main engineering risk and it should be proven before anything is committed to.

---

## 3. Options

### A. `| ai` via a dispatched search  — *recommended path*

Handler builds the prompt, dispatches a oneshot search through `| ai`, reads the result field.

- Works on **5.6.4 and 6.x**, so it does not strand .222.
- Uses the AITK connection, so **the customer's key (or no key at all) is managed in one place**.
- Unlocks **Splunk Hosted Models** — no customer API key, which is a genuinely better story for
  a Splunkbase app than "bring your own OpenRouter key".
- No Python-version change.
- Risks: SPL quoting/escaping of a large prompt; latency and search overhead per call;
  `llm_params.max_tokens` / `maximum_result_rows` truncating a long JSON reply.

### B. `| aiagent`

- **6.x only**, so .222 must be upgraded first.
- Prompts live in the agent (`system_prompt` / `task_prompt`) and are edited in Agent Launchpad,
  which solves question 2 almost for free.
- Agents can carry MCP tools, including ours.
- Heavier: agentic runtime, per-customer agent provisioning, async status polling.

### C. `splunklib.ai` SDK in the handler

- The cleanest technically — native Python, no SPL marshalling, ideal for strict JSON.
- **Blocked today.** The SDK's agent invocation needs **Python 3.13**, and our handlers are
  deliberately `python.required = 3.9` because the shipped runtime libs are pinned to their last
  py3.9 releases (`nltk 3.9.2`, `scipy 1.13.1`, `scikit-learn 1.6.1`, `scrubadub 2.0.1`). Moving
  the handlers to 3.13 would invalidate that whole pin set. Only viable as a **separate 3.13
  handler** alongside the existing 3.9 ones, which is a real piece of work.

### D. Borrow the connection's credentials, keep our direct HTTPS call

Read `aitk_llm_connection` and reuse provider/model, keeping our own HTTP client.

- Tempting and cheap, **but it cannot reach `Splunk Hosted Models`**, which is the main prize:
  there is no key to borrow, the Toolkit brokers that access itself. It also bypasses the quota
  and usage accounting. Worth it only as a transitional nicety, not as the destination.

---

## 4. Proposed plan

**Phase 0 — spike, go/no-go (half a day).** Before committing: prove that a realistic
CIMPlicity prompt (~2 KB, containing braces, quotes and regex backslashes) plus a raw log sample
can be pushed through `| ai` and a **valid strict JSON document** recovered. Test against both a
`Splunk Hosted Models` connection and an `OpenAI`-compatible one. If JSON fidelity cannot be made
reliable, option A dies and the answer is C behind a 3.13 handler.

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

1. **JSON fidelity through SPL** — the phase 0 go/no-go. Everything in option A rests on it.
2. **Latency** — a dispatched search per call versus a direct HTTPS request. Needs measuring against
   the current ~7–20 s; the demo already suffers when calls are slow.
3. **Truncation** — `llm_params.max_tokens` (2000 on the sampled connection) may be below what our
   CIM-mapping reply needs. Our extraction replies have run to ~1.9 KB already.
4. **.222 is on 5.6.4** — upgrade to 6.1 needed for anything past bare `| ai`.
5. **Splunkbase dependency question** — making the AI Toolkit *required* adds a dependency for
   every customer. It should stay optional, with direct-HTTPS as the default.
6. **Who owns the connection** — `aitk_llm_connection` rows carry an ACL and `default_users`.
   Our handlers run under `passSystemAuth`; whether that context can resolve a user-scoped default
   connection is unverified and needs checking before phase 2.

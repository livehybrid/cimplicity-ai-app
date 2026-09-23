# LLM backends

CIMPlicity can reach an LLM two ways. The choice is `ai_configuration.backend` on the
Configuration page.

| | **Direct** (default) | **Splunk AI Toolkit** |
|---|---|---|
| How | HTTPS to any OpenAI-compatible API | dispatches `\| ai` as a search |
| Key | yours, stored encrypted in the app | the customer's AI Toolkit connection |
| Speed | fast | **~6x slower**, measured |
| Reply size | `max_tokens` is ours to set | the connection's, which we cannot override |
| Needs | an API key | AI Toolkit 6.x and a connection the caller can see |
| Splunk Hosted Models | no | **yes**, on Cloud, with no key at all |

Both go through `lib/llm_client.complete()`, which is the only place either handler calls an
LLM. Adding a third backend means a third branch there and nothing else.

## Direct

Today's behaviour and the default, so an existing install is unaffected by the Toolkit
work existing. Set **LLM API Endpoint**, **API key** and **Model**. Anything
OpenAI-compatible works, which includes OpenRouter, OpenAI, Anthropic and a local
Ollama.

`lib/llm_client.py` owns the transport. Two things worth knowing: the timeout is an
explicit `(connect, read)` pair rather than a scalar (a scalar in `requests` is
per-socket-operation, not a cap on the call), and `max_tokens` defaults to 4000 and is
overridable from the settings stanza.

## Splunk AI Toolkit

Set **LLM Backend** to *Splunk AI Toolkit*, and optionally name a connection in **AI
Toolkit connection**; blank uses the caller's default. No API key needed.

Worth choosing when the customer wants one managed key with the Toolkit's quota and
usage accounting, or on Splunk Cloud where it can reach Splunk Hosted Models with no
key at all. Worth avoiding for interactive use because of the latency.

### Four things that will bite you

**1. `| ai` runs the prompt through `str.format()`.** A literal `{` is a `KeyError` that
surfaces as `Error in 'ai' command: 'ok'` and reads like a server fault. Both our prompts
show the model a JSON schema, and `ai_detection` interpolates the customer's raw event,
so a JSON log line would kill the search. `llm_toolkit.escape_prompt` doubles every brace
before SPL quoting, which `str.format()` collapses back, so the model sees exactly what
we wrote and customer data survives intact.

**2. Errors come back as a successful search.** This is the one that costs a silent wrong
answer:

```
| ai returns:  ai_result_1 = "Empty response content received from the server."
               dispatchState = DONE, no error messages
```

Parse that and you get an error string where JSON should be. `llm_toolkit` rejects the
Toolkit's own `LLM_EXCEPTION_LIST` before returning content. Observed live when
gpt-5-mini spent its entire 2000-token connection budget reasoning and returned nothing.

**3. The connection's `max_tokens` is a hard ceiling.** `| ai` takes only
`prompt`, `connection`, `provider` and `model`: no `max_tokens`, no `temperature`, no
`response_format`. Every connection seen in the wild defaults to 2000, shared between
reasoning and output on a reasoning model. If replies come back empty, that is the first
thing to raise, and only the customer can do it, in the Toolkit UI.

**4. Connections are per-user.** `default_users` gates who can see one, and the
default-connection mapping is per user too. The search therefore runs with the *caller's*
session key in the *caller's* namespace, never the system one, which the AI Toolkit
refuses outright. A connection that is not shared with the user gets
`No configuration found for llm connection`.

## Measured

Same events, same handlers, only the backend changed, on Splunk Enterprise 10.4 with AI
Toolkit 6.1.

| Endpoint | Direct (`claude-opus-5`) | Toolkit (`gpt-5-mini`) |
|---|---|---|
| `cim_mapping` | 15.5 s, 4 mappings | 98.8 s, 4 mappings |
| `ai_detection` | 59.7 s, 8 fields | 179.6 s, failed on the 2000-token budget |

SPL length is not a constraint: the `cim_mapping` call produced an 11,832-character
search string and ran fine.

## Failure handling

Both backends raise `llm_client.LlmError` with one of four reasons, so the handlers map
one vocabulary either way:

| reason | meaning |
|---|---|
| `not_configured` | no API key, or no usable AI Toolkit connection |
| `timeout` | the call did not return in time |
| `transport` | HTTP or search dispatch failure |
| `bad_response` | a reply that is not usable content |
| `unavailable` | Toolkit only: `\| ai` does not exist on this instance |

`ai_detection` treats every reason as "take the local regex fallback". `cim_mapping` has
no fallback, so each maps to the user-facing message it already showed.

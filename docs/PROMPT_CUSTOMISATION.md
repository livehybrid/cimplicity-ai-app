# Customising the prompts

CIMPlicity's LLM prompts are **guidance + contract**. The guidance is yours to change;
the contract is not.

```
guidance   the domain instructions      default/cim-plicity_prompts.conf, override in local/
contract   the exact JSON shape         in the app's code, always appended, not configurable
```

The contract is excluded deliberately. Every parser downstream depends on that exact
shape, so editing it away would break the app rather than reconfigure it, and the failure
would look like a bug rather than a setting.

## Changing a prompt

Create `local/cim-plicity_prompts.conf` in the app directory. Splunk layers `local/` over
`default/`, so your edits survive an app upgrade. Do not edit `default/`; it is replaced
on upgrade.

```ini
[ai_detection]
guidance = You are a Splunk expert analysing a log sample to suggest field extractions. \
    The log sample is: {sample_data} \
    {description_block} \
    House rules for this deployment: \
    1. The sourcetype MUST begin with "acme:" followed by a short name. \
    2. Use Splunk named capture groups (?<name>...), never Python (?P<name>...). \
    3. Name the badge field "acme_badge_id", whatever the raw event calls it. \
    4. Provide a combined regex, TIME_FORMAT, TIME_PREFIX and MAX_TIMESTAMP_LOOKAHEAD.
```

Values continue across lines with a trailing backslash. No restart is needed: `app.conf`
`[triggers]` reloads this conf, and the handlers read it per request.

That example is not hypothetical. Run against a door-access event it produces
`sourcetype = acme:badgeaccess` and a field called `acme_badge_id`.

## Placeholders

Your data is injected at these. **Keep them.**

| Stanza | Required | Optional |
|---|---|---|
| `ai_detection` | `{sample_data}` | `{description_block}`, the user's own "additional context" note |
| `cim_mapping` | `{cim_model}`, `{available_cim_fields}`, `{extracted_fields}` | |

Every other brace is left alone, so example JSON can be pasted into your guidance
safely.

**A template missing a required placeholder is ignored.** The app falls back to the
shipped prompt and logs which placeholder is missing:

```
ERROR Configured 'ai_detection' prompt guidance is missing required placeholder(s)
{sample_data}; falling back to the shipped default.
```

That is deliberate: a prompt with no data in it does not fail, it returns confident
nonsense, which is far worse than an obvious error. Check `cim-plicity.log` after editing.

## What is worth putting in

Things the model cannot know from one sample event:

- **Naming conventions.** "Field names must be snake_case and prefixed `acme_`."
- **Facts about the source.** "`device_id` is always a MAC address, never a hostname."
- **Things to ignore.** "The trailing 16-character token is a correlation id; do not
  extract it."
- **House CIM preferences.** "Map operator identities to `user`, never `src_user`."
- **Sourcetype conventions.** "Use `vendor:product:dataset`."

Things not worth putting in: the JSON shape (it is appended for you), and anything
that contradicts it.

## Files

| Path | What |
|---|---|
| `default/cim-plicity_prompts.conf` | the shipped guidance. Read it first, then copy what you want to change |
| `local/cim-plicity_prompts.conf` | your overrides |
| `README/cim-plicity_prompts.conf.spec` | the settings reference |
| `lib/prompts.py` | the contracts, the placeholder validation, and the in-code fallback |

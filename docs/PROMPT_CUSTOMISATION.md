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

Two places, tried in this order. The first usable value wins.

| | Where | Best for |
|---|---|---|
| 1 | **Configuration → Prompts** in the app UI | trying something out, one-off tweaks |
| 2 | `local/cim-plicity_prompts.conf` | anything deployed by configuration management |
| 3 | the shipped default | when both are blank |

Each level is validated on its own, and an unusable value **falls through to the next
rather than being sent**, so a bad edit in the UI cannot mask a good prompt in the conf
file. `cim-plicity.log` says which place a rejected value came from.

### 1. In the UI

**Configuration → Prompts**, two boxes: *Field extraction guidance* and *CIM mapping
guidance*. They arrive **pre-filled with the prompts the app actually uses**, so you can
read what it does today and edit from there rather than starting at an empty box.

Saved values land in `local/cim-plicity_settings.conf` under `[prompts]` and take effect
on the next call, with no restart or reload.

### Going back to the shipped prompt

Clearing the box and saving **restores the behaviour but not the text**, and the
difference matters. Saving writes to `local/`, and `local` overrides `default`, so an
empty box becomes an empty *override*: the app falls back to the shipped prompt (the
handler treats empty as "use the default"), but the box stays blank the next time you
open it, which looks like the prompt has been lost.

To get the shipped text back in front of you, either copy it from
`default/cim-plicity_settings.conf` under `[prompts]`, or remove the key from
`local/cim-plicity_settings.conf` so the default shows through again:

```ini
# local/cim-plicity_settings.conf -- delete the whole [prompts] stanza, or just
# the one key you want to reset, then reload:
#   POST /servicesNS/nobody/cim-plicity/configs/conf-cim-plicity_settings/_reload
```

A proper *Restore to default* button on the tab is the obvious fix and is not yet
built.

This is the easier route and the one to reach for first. It also **takes effect
immediately**: UCC saves through a REST handler, which updates splunkd's in-memory conf,
so there is nothing to reload. The file route below does need a reload.

### 2. In the conf file

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

Values continue across lines with a trailing backslash.

**No restart is needed, but a conf reload is.** Editing through Splunk Web or the REST
config endpoints reloads automatically. Editing the file on disk does **not**: splunkd
serves the conf from memory, so your change is invisible until you reload it.

```
curl -k -u admin:changeme -X POST \
  https://localhost:8089/servicesNS/nobody/cim-plicity/configs/conf-cim-plicity_prompts/_reload
```

Verified on a live instance: after a direct file edit the app still used the old prompt,
and after that one POST it used the new one, with no restart. The `[triggers]` entry in
`app.conf` declares *how* to reload, not that a file edit triggers it.

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
| Configuration → Prompts (UI) | the first place checked; stored in `local/cim-plicity_settings.conf` `[prompts]` |
| `default/cim-plicity_prompts.conf` | the shipped guidance. Read it first, then copy what you want to change |
| `local/cim-plicity_prompts.conf` | your file-based overrides |
| `README/cim-plicity_prompts.conf.spec` | the settings reference |
| `lib/prompts.py` | the contracts, the placeholder validation, the precedence, and the in-code fallback |

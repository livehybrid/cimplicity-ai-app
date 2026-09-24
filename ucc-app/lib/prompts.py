"""Customer-editable prompt guidance, with the output contract kept in code.

Prompts were inline f-strings in the two handlers, so a customer who wanted the
model to know something about their data ("device_id is always a MAC", "ignore
the trailing correlation token") had no way to say so without forking the app.
Now the *guidance* half lives in `cim-plicity_prompts.conf` and layers the
normal Splunk way: `default/` ships ours, `local/` holds theirs, an upgrade does
not clobber it.

THE SPLIT IS THE WHOLE POINT. Each prompt ends with an output contract, the
required JSON shape plus "no text outside the JSON". Externalising the prompt as
one blob would be the easy implementation and the wrong one: a customer who
edits the contract away breaks every downstream parser, and the app looks broken
rather than misconfigured. So:

  guidance  the domain instructions      customer-editable, from conf
  contract  the JSON shape and "no prose"  NOT editable, lives here, always appended

WHY NOT str.format(). The contract and the guidance both contain literal JSON
braces. Running `.format()` over them raises KeyError on the first `{"`, which
is the same trap `| ai` falls into (see lib/llm_toolkit.py). Substitution here
replaces only the known placeholders by name and leaves every other brace alone,
so a customer can paste JSON into their guidance without breaking anything.

VALIDATION. A guidance template that has lost `{sample_data}` would send the
model an instruction with no data in it and get confident nonsense back. Missing
placeholders therefore fall back to the shipped default and log loudly, rather
than rendering a prompt that looks fine and is not.
"""
import logging
import re

# Placeholders each guidance template MUST carry, or the model gets no data.
REQUIRED_PLACEHOLDERS = {
    "ai_detection": ("sample_data",),
    "cim_mapping": ("cim_model", "available_cim_fields", "extracted_fields"),
}

# Never customer-editable: every downstream parser depends on these exactly.
CONTRACTS = {
    "ai_detection": """
        Return your response as a single, valid JSON object with the following EXACT structure:
        {
          "sourcetype": "string",
          "fields": [
            {
              "name": "field_name",
              "regex": "regex_pattern_with_named_groups"
            }
          ],
          "combined_regex": "single_regex_to_extract_all_fields",
          "time_format": "python_datetime_format_string",
          "time_prefix": "prefix_before_timestamp_or_empty",
          "max_timestamp_lookahead": "number_as_string"
        }

        Do not include any explanatory text outside of the JSON object.
        """,
    "cim_mapping": """
        Return your response as a single, valid JSON array of objects. Each object in the array
        represents a single mapping and must have the following structure:
        {
          "field": "The name of the original extracted field",
          "cimField": "The name of the standard CIM field it maps to",
          "confidence": A float between 0.0 and 1.0,
          "reasoning": "A brief explanation for the mapping"
        }

        Do not include any explanatory text outside of the final JSON array.
        """,
}

# The shipped guidance. Also the fallback when a customer's edit is unusable, so
# it must stay in lockstep with default/cim-plicity_prompts.conf; a test asserts
# that it does.
DEFAULT_GUIDANCE = {
    "ai_detection": """
        You are a Splunk expert tasked with analyzing a log sample to suggest field extractions.
        The log sample is:
        ---
        {sample_data}
        ---
        {description_block}
        Your instructions are:
        1.  Suggest an appropriate Splunk sourcetype for this data (e.g. 'json', 'syslog',
            'custom_log') or something appropriate to what you think the data is.
        2.  Identify key fields to be extracted from the log sample.
        3.  For each field, provide a robust PCRE-based regex pattern usable in props.conf. The
            regex must use named capture groups, in Splunk syntax (?<field_name>...) and NOT
            Python syntax (?P<field_name>...), must match against the entire log line, and must
            capture its field only once.
        4.  In addition, provide a single regex pattern that extracts all the fields in one go.
        5.  Analyse the log data for timestamp patterns and provide TIME_FORMAT (a Python
            datetime format string), TIME_PREFIX (any prefix appearing before the timestamp, or
            an empty string) and MAX_TIMESTAMP_LOOKAHEAD (characters to look ahead, default 25,
            raised when the timestamp sits late in the line).
        """,
    "cim_mapping": """
        You are a Splunk CIM expert. Your task is to map a list of extracted fields from a log
        file to the standard fields of a specified Splunk Common Information Model (CIM).

        CIM Data Model: {cim_model}

        Available CIM fields for this model:
        {available_cim_fields}

        Extracted fields from the log data:
        {extracted_fields}

        Your instructions are:
        1.  Analyse the extracted fields. Pay attention to the field names and their sample values.
        2.  For each extracted field, find the best matching standard field from the available
            CIM fields.
        3.  You may map multiple extracted fields to the same CIM field where appropriate (for
            example 'ip' and 'client_ip' could both map to 'src_ip').
        4.  If an extracted field has no clear and logical mapping, omit it from your response
            rather than stretching for a CIM field that nearly fits.
        5.  For each mapping give a confidence between 0.0 and 1.0 reflecting your certainty
            based on the field names and values.
        6.  For each mapping give a brief "reasoning" explaining the choice (for example "field
            name 'user_ip' is a clear synonym for 'src_ip'").
        """,
}

_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def substitute(template, values):
    """Replace only the known `{placeholder}` tokens, leaving other braces alone.

    Deliberately not str.format(): both the guidance and the contract contain
    literal JSON braces, which .format() would treat as fields and reject.
    """
    def repl(match):
        key = match.group(1)
        return str(values[key]) if key in values else match.group(0)
    return _PLACEHOLDER_RE.sub(repl, template)


def missing_placeholders(name, guidance):
    """Which required placeholders a guidance template has lost."""
    present = set(_PLACEHOLDER_RE.findall(guidance or ""))
    return tuple(p for p in REQUIRED_PLACEHOLDERS.get(name, ()) if p not in present)


def resolve_guidance(name, configured):
    """The guidance to use: the customer's if usable, otherwise the shipped one."""
    default = DEFAULT_GUIDANCE[name]
    if not configured or not configured.strip():
        return default
    missing = missing_placeholders(name, configured)
    if missing:
        logging.error(
            "Configured '%s' prompt guidance is missing required placeholder(s) %s; "
            "falling back to the shipped default. Edit [%s] guidance in "
            "cim-plicity_prompts.conf and put them back.",
            name, ", ".join("{%s}" % m for m in missing), name)
        return default
    return configured


def render(name, values, configured=None):
    """The full prompt: resolved guidance, substituted, plus the fixed contract."""
    guidance = resolve_guidance(name, configured)
    return "%s\n%s" % (substitute(guidance, values).rstrip(), CONTRACTS[name])


def read_configured(read_stanza, name):
    """One guidance string from cim-plicity_prompts.conf, or None.

    read_stanza: a callable taking the stanza name and returning its dict.
        Injected so this module needs no solnlib and is testable. Any failure is
        treated as "not configured" rather than raised: a broken prompts conf
        must not take the app down, it must fall back to the shipped prompt.
    """
    try:
        stanza = read_stanza(name) or {}
        value = stanza.get("guidance")
        return value if value and value.strip() else None
    except Exception as exc:  # noqa: BLE001 - absence is the safe outcome
        logging.warning("Could not read '%s' prompt guidance (%s); using the shipped default",
                        name, exc)
        return None

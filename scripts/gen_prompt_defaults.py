#!/usr/bin/env python3
"""Generate the [prompts] stanza of default/cim-plicity_settings.conf.

`lib/prompts.DEFAULT_GUIDANCE` is the single authored copy of the shipped
prompt guidance. This writes it into the settings conf so the Configuration
page's Prompts tab shows the real prompt instead of an empty box, which is what
anyone opening that tab expects to find.

Run after editing DEFAULT_GUIDANCE. tests/test_prompts.py asserts the two stay
in lockstep, so a forgotten run fails the build rather than shipping a tab whose
contents do not match the prompt actually used.

    python3 scripts/gen_prompt_defaults.py
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "ucc-app", "lib"))
import prompts  # noqa: E402

CONF = os.path.join(REPO, "ucc-app", "default", "cim-plicity_settings.conf")

HEADER = """
# Prompt guidance, edited on the Configuration page's Prompts tab.
#
# This stanza MUST exist: ucc-gen generates a tab's conf spec but not its
# stanza, and the UCC settings REST handler 404s on a stanza it cannot find, so
# every save from the UI would fail with "Could not find object id=prompts".
#
# The values below are the shipped prompts, generated from
# lib/prompts.DEFAULT_GUIDANCE by scripts/gen_prompt_defaults.py. Do not edit
# them here: this file is replaced on upgrade. Edit on the Prompts tab, which
# writes to local/, or clear a box to go back to the shipped prompt.
#
# Only the GUIDANCE is here. The JSON output contract is appended by the app and
# is deliberately not configurable, because every parser downstream depends on
# that exact shape.
"""


def as_conf_value(text):
    """Render a guidance template as one Splunk conf value.

    Splunk continues a value while the line ends with a backslash and strips
    leading whitespace on continuations, so the prompt is emitted one logical
    line per source line rather than trying to preserve indentation.
    """
    lines = [l.strip() for l in text.strip("\n").split("\n")]
    return " \\\n    ".join(lines)


def build_stanza():
    out = [HEADER.strip(), "", "[%s]" % prompts.SETTINGS_STANZA]
    for name in sorted(prompts.DEFAULT_GUIDANCE):
        out.append("%s = %s" % (prompts.SETTINGS_FIELD % name,
                                as_conf_value(prompts.DEFAULT_GUIDANCE[name])))
    return "\n".join(out) + "\n"


def main():
    s = open(CONF).read()
    stanza = build_stanza()
    marker = "[%s]" % prompts.SETTINGS_STANZA
    if marker in s:
        # Replace from the generated header (or the stanza) to end of file.
        start = s.find("\n# Prompt guidance, edited on the Configuration page")
        if start == -1:
            start = s.find(marker)
        s = s[:start].rstrip("\n") + "\n\n" + stanza
    else:
        s = s.rstrip("\n") + "\n\n" + stanza
    open(CONF, "w").write(s)
    print("wrote [%s] with %d field(s) to %s"
          % (prompts.SETTINGS_STANZA, len(prompts.DEFAULT_GUIDANCE),
             os.path.relpath(CONF, REPO)))


if __name__ == "__main__":
    main()

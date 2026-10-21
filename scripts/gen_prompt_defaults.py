#!/usr/bin/env python3
"""Generate every shipped copy of the prompt guidance from one source.

`lib/prompts.DEFAULT_GUIDANCE` is the single authored copy. It is shipped in two
conf files, and BOTH are generated here so they cannot drift:

  default/cim-plicity_settings.conf  [prompts]   the Configuration page's tab
  default/cim-plicity_prompts.conf   [<name>]    the file-based override layer

Writing only one of them is exactly the mistake this script exists to prevent:
the tab would show one prompt while the conf offered another.

Run after editing DEFAULT_GUIDANCE. tests/test_prompts.py asserts all three stay
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

SETTINGS_CONF = os.path.join(REPO, "ucc-app", "default", "cim-plicity_settings.conf")
PROMPTS_CONF = os.path.join(REPO, "ucc-app", "default", "cim-plicity_prompts.conf")

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
    leading whitespace on continuations. prompts.as_shipped does the
    normalisation so the conf and the prompt_defaults endpoint agree exactly,
    which is what lets "Restore to default" reproduce the shipped value.
    """
    return " \\\n    ".join(prompts.as_shipped(text).split("\n"))


def build_stanza():
    out = [HEADER.strip(), "", "[%s]" % prompts.SETTINGS_STANZA]
    for name in sorted(prompts.DEFAULT_GUIDANCE):
        out.append("%s = %s" % (prompts.SETTINGS_FIELD % name,
                                as_conf_value(prompts.DEFAULT_GUIDANCE[name])))
    return "\n".join(out) + "\n"


def rewrite_prompts_conf():
    """Rewrite the guidance values in default/cim-plicity_prompts.conf.

    Keeps the file's comment header (it documents the placeholders and the
    reload requirement) and replaces everything from the first stanza on.
    """
    s = open(PROMPTS_CONF).read()
    first = s.find("[")
    header = s[:first].rstrip("\n") if first > 0 else ""
    out = [header, ""]
    for name in sorted(prompts.DEFAULT_GUIDANCE):
        out.append("[%s]" % name)
        out.append("guidance = %s" % as_conf_value(prompts.DEFAULT_GUIDANCE[name]))
        out.append("")
    open(PROMPTS_CONF, "w").write("\n".join(out).rstrip("\n") + "\n")
    print("wrote %d stanza(s) to %s"
          % (len(prompts.DEFAULT_GUIDANCE), os.path.relpath(PROMPTS_CONF, REPO)))


def main():
    s = open(SETTINGS_CONF).read()
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
    open(SETTINGS_CONF, "w").write(s)
    print("wrote [%s] with %d field(s) to %s"
          % (prompts.SETTINGS_STANZA, len(prompts.DEFAULT_GUIDANCE),
             os.path.relpath(SETTINGS_CONF, REPO)))
    rewrite_prompts_conf()


if __name__ == "__main__":
    main()

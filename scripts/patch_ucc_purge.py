#!/usr/bin/env python3
"""Make ucc-gen 6.x package purging tolerate missing RECORD entries.

ucc-gen >= 6.0 removes cleanup packages (numpy, setuptools, ...) from lib/ by
deleting every path listed in each package's RECORD file with a bare
os.remove(). numpy's RECORD lists console scripts (bin/f2py and friends) that
pip never creates under a --target install, so a transitive numpy (pulled by
scipy/scikit-learn via scrubadub) kills the whole build with
FileNotFoundError. Confirmed on 6.5.3 (2026-07-30); 5.x used rmtree-based
purging and was immune, which is why this repo was pinned to 5.69.1 until now.

Run straight after `pip install -r build-requirements.txt` (CI and local
builds). Idempotent. Fails loudly if the upstream code changes shape so the
workaround gets re-evaluated rather than silently rotting. Delete this script
once upstream guards the removal
(https://github.com/splunk/addonfactory-ucc-generator).
"""
import pathlib
import sys

import splunk_add_on_ucc_framework as ucc

TARGET = pathlib.Path(ucc.__file__).parent / "install_python_libraries.py"
ANCHOR = "            os.remove(os.path.join(installation_path, path))\n"
GUARDED = (
    "            try:\n"
    "                os.remove(os.path.join(installation_path, path))\n"
    "            except FileNotFoundError:\n"
    "                pass  # RECORD may list script files pip never created\n"
)

src = TARGET.read_text()
if GUARDED in src:
    print(f"patch_ucc_purge: already patched: {TARGET}")
    sys.exit(0)
if ANCHOR not in src:
    sys.exit(
        f"patch_ucc_purge: anchor not found in {TARGET} - ucc-gen changed; "
        "check whether the upstream bug is fixed (then delete this script) "
        "or update the anchor."
    )
TARGET.write_text(src.replace(ANCHOR, GUARDED))
print(f"patch_ucc_purge: guarded RECORD removal in {TARGET}")

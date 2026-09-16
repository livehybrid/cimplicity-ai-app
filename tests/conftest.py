"""Pytest path setup: make the app's bin/ and lib/ modules importable."""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for _rel in (("ucc-app", "bin"), ("ucc-app", "lib")):
    _path = os.path.join(_REPO_ROOT, *_rel)
    if _path not in sys.path:
        sys.path.insert(0, _path)

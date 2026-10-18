"""Guards for lib/cim_plicity_logging.py: every handler logs to one file,
$SPLUNK_HOME/var/log/splunk/cim-plicity.log, whatever configured logging first.

splunkd hosts all persistent handlers of a Python version in one shared
appserver process. The old per-script logging.basicConfig(filename=...) was a
no-op for every script after the first, so the first import decided the file
for everyone (cim_mapping first -> everything in cim-plicity_cim_mapping.log,
no cim-plicity.log at all). These tests reproduce that ordering: the root
logger is configured to another file BEFORE the app's logger is set up.

The log file is located from SPLUNK_HOME by the test itself and read back from
disk, never via the module's log_file_path() or its handler objects.
"""
import importlib
import logging
import re

import pytest

STAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} ")


def _drop_handlers(name):
    logger = logging.getLogger(name)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()


@pytest.fixture
def splunk_home(tmp_path, monkeypatch):
    (tmp_path / "var" / "log" / "splunk").mkdir(parents=True)
    monkeypatch.setenv("SPLUNK_HOME", str(tmp_path))
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    _drop_handlers("cim-plicity")
    # Another handler script (or another app) got to the shared root logger first.
    for h in list(root.handlers):
        root.removeHandler(h)
    logging.basicConfig(filename=str(tmp_path / "other.log"), level=logging.INFO)
    yield tmp_path
    _drop_handlers("cim-plicity")
    _drop_handlers("")
    for h in saved[0]:
        root.addHandler(h)
    root.setLevel(saved[1])


def _fresh_module():
    import cim_plicity_logging
    return importlib.reload(cim_plicity_logging)


def _flush():
    for h in logging.getLogger("cim-plicity").handlers + logging.getLogger().handlers:
        h.flush()


def _read(path):
    return path.read_text() if path.exists() else ""


def test_every_handler_lands_in_cim_plicity_log_after_root_was_configured(splunk_home):
    mod = _fresh_module()
    # Two handler scripts importing the module in the same process.
    mod.get_logger("cim_mapping").info("marker-from-cim-mapping")
    _fresh_module().get_logger("pii_detection").warning("marker-from-pii")
    _flush()

    ours = _read(splunk_home / "var" / "log" / "splunk" / "cim-plicity.log")
    other = _read(splunk_home / "other.log")
    assert ours.count("marker-from-cim-mapping") == 1, ours
    assert ours.count("marker-from-pii") == 1, ours
    assert "marker-from" not in other, other
    lines = [ln for ln in ours.splitlines() if ln]
    assert lines and all(STAMP.match(ln) for ln in lines), lines


def test_lib_module_lines_land_in_the_same_file(splunk_home):
    pytest.importorskip("scrubadub")
    _fresh_module().get_logger("pii_detection")
    from pii_detection_logic import PiiDetectionLogic
    PiiDetectionLogic(["IpAddressDetector"]).load_detectors()
    _flush()
    ours = _read(splunk_home / "var" / "log" / "splunk" / "cim-plicity.log")
    assert "Successfully loaded 1 detectors" in ours, ours
    assert "Successfully loaded" not in _read(splunk_home / "other.log")


def test_set_level_filters_and_restores(splunk_home):
    mod = _fresh_module()
    log = mod.get_logger("pii_detection")
    mod.set_level("ERROR")
    log.info("suppressed-at-error")
    mod.set_level("INFO")
    log.info("visible-at-info")  # positive control: the same path does write
    _flush()
    ours = _read(splunk_home / "var" / "log" / "splunk" / "cim-plicity.log")
    assert "visible-at-info" in ours, ours
    assert "suppressed-at-error" not in ours, ours

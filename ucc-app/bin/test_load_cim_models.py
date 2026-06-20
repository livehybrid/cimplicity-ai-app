#!/usr/bin/env python3
"""Tests for load_cim_models.load_cim_fields().

Runnable standalone (`python3 test_load_cim_models.py`) or under pytest.
Builds a fake $SPLUNK_HOME/etc/apps/Splunk_SA_CIM/.../models tree mirroring the
real CIM data-model JSON shape (flat objects[] with parentName, plus calculations).
"""
import os
import sys
import json
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import load_cim_models as L


def _make_fixture():
    tmp = tempfile.mkdtemp()
    models = os.path.join(
        tmp, "etc", "apps", "Splunk_SA_CIM", "appserver", "static", "data", "models"
    )
    os.makedirs(models)
    auth = {
        "modelName": "Authentication", "displayName": "Authentication",
        "objects": [
            {"objectName": "Authentication", "parentName": "BaseEvent", "fields": [
                {"fieldName": "action", "type": "string",
                 "comment": "The action performed (success/failure)."},
                {"fieldName": "app", "type": "string", "comment": "The application involved."},
                {"fieldName": "src", "type": "string"},
                {"fieldName": "user", "type": "string"},
             ], "calculations": [
                {"outputFields": [{"fieldName": "is_Privileged_Authentication", "type": "number"}]}
             ]},
            {"objectName": "Failed_Authentication", "parentName": "Authentication", "fields": [
                {"fieldName": "reason", "type": "string", "comment": "Reason auth failed."},
                {"fieldName": "user", "type": "string"},  # duplicate -> must dedup
             ]},
        ],
    }
    net = {"modelName": "Network Traffic", "objects": [
        {"objectName": "All_Traffic", "fields": [
            {"fieldName": "src_ip"}, {"fieldName": "dest_ip"}, {"fieldName": "bytes"}]}]}
    mal = {"modelName": "Malware", "objects": [
        {"objectName": "Malware_Attacks", "fields": [
            {"fieldName": "signature"}, {"fieldName": "file_hash"}]}]}
    junk = {"foo": "bar"}  # no modelName -> skipped
    for name, obj in [("Authentication.json", auth), ("Network_Traffic.json", net),
                      ("Malware.json", mal), ("Empty.json", junk)]:
        with open(os.path.join(models, name), "w") as f:
            json.dump(obj, f)
    return tmp


def test_discovers_all_models_and_aggregates_fields():
    tmp = _make_fixture()
    try:
        os.environ["SPLUNK_HOME"] = tmp
        fields = L.load_cim_fields()
        # every valid model file is discovered; junk skipped
        assert set(fields) == {"authentication", "network_traffic", "malware"}, set(fields)
        # model name with a space is normalised to a key
        assert "network_traffic" in fields
        names = {f["name"] for f in fields["authentication"]}
        # fields aggregated across parent AND child objects
        assert "action" in names and "reason" in names, names
        # calculated/derived output fields captured
        assert "is_Privileged_Authentication" in names, names
        # duplicate fieldName de-duplicated
        assert sum(1 for f in fields["authentication"] if f["name"] == "user") == 1
        # description carried from 'comment'
        action = next(f for f in fields["authentication"] if f["name"] == "action")
        assert action["description"] == "The action performed (success/failure)."
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_falls_back_when_cim_app_absent():
    os.environ["SPLUNK_HOME"] = os.path.join(tempfile.gettempdir(), "no_such_splunk_home_xyz")
    fb = L.load_cim_fields()
    assert set(fb) == {"authentication", "network_traffic", "web"}, set(fb)


if __name__ == "__main__":
    failures = 0
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            try:
                _fn()
                print(f"  PASS {_name}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {_name}: {exc}")
    print("ALL GREEN" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)

"""
Live tests for CIM-plicity against a real Splunk (integration/docker-compose.yml)
with the packaged app mounted. Stdlib urllib only, so the suite needs just pytest.

Environment (defaults suit the docker harness):
  SPLUNK_MGMT_URL   https://127.0.0.1:8089
  SPLUNK_USER       admin
  SPLUNK_PASSWORD   Changeme1!
  SPLUNK_CONTAINER  cimplicity_splunk (docker exec target for on-disk checks)
  APP_STAGE         integration/stage/cim-plicity (the extracted package)
"""
from __future__ import annotations

import base64
import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

MGMT = os.environ.get("SPLUNK_MGMT_URL", "https://127.0.0.1:8089").rstrip("/")
USER = os.environ.get("SPLUNK_USER", "admin")
PW = os.environ.get("SPLUNK_PASSWORD", "Changeme1!")
APP = "cim-plicity"
CONTAINER = os.environ.get("SPLUNK_CONTAINER", "cimplicity_splunk")
APP_STAGE = os.environ.get(
    "APP_STAGE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "stage", APP))

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_AUTH = "Basic " + base64.b64encode(f"{USER}:{PW}".encode()).decode()


class Splunk:
    def request(self, method, path, body=None, params=None, content_type=None):
        url = MGMT + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", _AUTH)
        if content_type:
            req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, context=_CTX, timeout=120) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    def get(self, path, **params):
        params.setdefault("output_mode", "json")
        return self.request("GET", path, params=params)

    def post_json(self, path, obj):
        return self.request("POST", path, body=json.dumps(obj).encode(), content_type="application/json")

    def post_form(self, path, fields):
        body = urllib.parse.urlencode({"output_mode": "json", **fields}).encode()
        return self.request("POST", path, body=body, content_type="application/x-www-form-urlencoded")

    def remove(self, path):
        return self.request("DELETE", path, params={"output_mode": "json"})

    def oneshot(self, spl, **params):
        body = urllib.parse.urlencode({"search": spl, "exec_mode": "oneshot", "output_mode": "json",
                                       "count": 0, **params}).encode()
        status, text = self.request("POST", "/services/search/jobs", body=body,
                                    content_type="application/x-www-form-urlencoded")
        assert status == 200, text[:400]
        return json.loads(text).get("results", [])


def container_exec(*argv):
    """Run a command in the Splunk container as the splunk user (it owns
    var/log/splunk, mode 0700). Returns (returncode, stdout)."""
    proc = subprocess.run(["docker", "exec", "-u", "splunk", CONTAINER, *argv],
                          capture_output=True, text=True, timeout=60)
    return proc.returncode, proc.stdout


def _loads(body):
    try:
        return json.loads(body)
    except ValueError:
        return None


@pytest.fixture(scope="session")
def splunk():
    """Wait until splunkd serves this app's own persistent handler, not just
    /services/server/info: the container goes healthy before freshly-mounted
    apps' REST handlers are reachable."""
    s = Splunk()
    deadline = time.time() + 300
    last = None
    while time.time() < deadline:
        status, body = s.get("/services/cim-plicity/ping")
        last = (status, body[:300])
        if status == 200 and (_loads(body) or {}).get("ok") is True:
            return s
        time.sleep(5)
    pytest.fail(f"cim-plicity ping never answered ok within 300s; last {last}")

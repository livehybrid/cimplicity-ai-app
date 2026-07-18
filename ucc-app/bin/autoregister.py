"""Self-registration endpoint for CIMPlicity AI's MCP tools, fired by app.conf
[triggers] when tools.conf is (re)loaded (install / enable / upgrade).

Cloud vs Enterprise aware:
  * Splunk Cloud (server/info instance_type == "cloud"): a native synced-apps
    registrar already registers MCP tools from default/tools.conf on install, so
    this no-ops.
  * Splunk Enterprise (instance_type is None / not "cloud"): older MCP servers have
    no tool_registration endpoint and no native registrar, so register the tools by
    upserting them into the Splunk MCP Server's mcp_tools + mcp_tools_enabled KV
    collections from the inline TOOLS table below. Idempotent (full-doc replace by
    _key).

Unlike ucc-app-builder there is NO shipped tool_input_payload_signatures.json
(the splunk-react-app skill says default/tools.conf is the in-app contract and new
apps must not add payload signature files). The Enterprise KV docs need an
inputSchema and an execution body template that tools.conf cannot express, so the
minimal signatures live inline in TOOLS here — one place, next to the code that
ships them. Keep TOOLS in lockstep with default/tools.conf.

Also serves the cim_plicity_ping health tool (dispatch on the matched restmap
path), and is callable directly (POST /services/cim-plicity/autoregister) as a
one-shot. Runs with passSystemAuth=true (system session key). Pure stdlib +
splunk.rest, so it runs on Splunk's default persistent-handler python.
"""
import json
import urllib.parse

from splunk.persistconn.application import PersistentServerConnectionApplication

try:
    import splunk.rest as rest
except Exception:  # pragma: no cover - only importable inside splunkd
    rest = None

APP = "cim-plicity"
KV = "/servicesNS/nobody/Splunk_MCP_Server/storage/collections/data"

# (name, method, endpoint, description, properties, required, body-template)
# endpoint = the REAL HTTP path from the [script:...] stanza's `match` in
# restmap.conf — NOT /services/<endpoint_name>. body uses the Splunk MCP Server's
# $arg$ placeholders (an exact "$k$" value forwards the raw typed argument;
# unfilled optional placeholders are dropped by the server's substitution).
TOOLS = [
    ("cim_plicity_ping", "GET", "/services/cim-plicity/ping",
     "Health check for CIMPlicity AI. Returns { ok, app, tools }. Call first to "
     "verify connectivity before other tools.",
     {}, [], None),
    ("ai_detection", "POST", "/services/ai_detection",
     "Suggest Splunk field extractions for a raw log sample: props.conf-ready PCRE "
     "regexes with named capture groups, a suggested sourcetype and timestamp "
     "settings (time_format, time_prefix, max_timestamp_lookahead). Uses the "
     "app-configured AI provider with a local regex fallback. Returns { sourcetype, "
     "fields:[{name, regex}], combined_regex, time_format, time_prefix, "
     "max_timestamp_lookahead, source }.",
     {"text": {"type": "string",
               "description": "Raw sample event/lines to analyse."},
      "description": {"type": "string",
                      "description": "Optional context about the data."},
      "selected_fields": {"type": "array", "items": {"type": "string"},
                          "description": "Optional field names; when given, a "
                                         "combined_regex covering exactly these "
                                         "fields is built."}},
     ["text"],
     {"text": "$text$", "description": "$description$",
      "selected_fields": "$selected_fields$"}),
    ("pii_detection", "POST", "/services/pii_detection",
     "Detect PII in a raw log sample using scrubadub detectors (configured on the "
     "app's Configuration page) plus optional caller-supplied regex patterns. "
     "Returns { pii_results:[{type, text, score, start, end, field, examples, "
     "regex_pattern}], suggestion }.",
     {"text": {"type": "string",
               "description": "Raw sample to scan for PII."},
      "custom_patterns": {"type": "array",
                          "description": "Optional extra patterns: [{name, regex}] "
                                         "(matched case-insensitively).",
                          "items": {"type": "object",
                                    "properties": {"name": {"type": "string"},
                                                   "regex": {"type": "string"}}}}},
     ["text"],
     {"text": "$text$", "custom_patterns": "$custom_patterns$"}),
    ("cim_mapping", "POST", "/services/cim_mapping",
     "Map extracted log fields onto a Splunk CIM data model with AI, returning "
     "per-field confidence and reasoning. cimModel is a lowercase_underscore model "
     "key (e.g. authentication, network_traffic, web; loaded dynamically from "
     "Splunk_SA_CIM when installed). Returns [{field, cimField, confidence, "
     "reasoning}] or {error}. Requires the app's AI api_key to be configured.",
     {"extractedFields": {"type": "array",
                          "description": "Extracted fields, e.g. [{name, sample}]; "
                                         "sample values improve mapping quality.",
                          "items": {"type": "object",
                                    "properties": {"name": {"type": "string"},
                                                   "sample": {"type": "string"}}}},
      "cimModel": {"type": "string",
                   "description": "CIM model key, lowercase with underscores, e.g. "
                                  "authentication, network_traffic, web."}},
     ["extractedFields", "cimModel"],
     {"extractedFields": "$extractedFields$", "cimModel": "$cimModel$"}),
]


def _doc(name, method, endpoint, desc, props, required, body):
    tool_id = "%s:%s" % (APP, name)
    execution = {"type": "api", "method": method, "endpoint": endpoint}
    if body is not None:
        execution["body"] = body
        # Force JSON so the MCP server sends a raw JSON body (not form-encoded);
        # this app's REST handlers json-parse req['payload'].
        execution["headers"] = {"Content-Type": "application/json"}
    return {
        "_key": tool_id, "tool_id": tool_id, "name": name, "title": name,
        "description": desc,
        "inputSchema": {"type": "object", "properties": props, "required": required},
        "_meta": {"tags": [APP], "execution": execution,
                  "external_app_id": APP, "required_app": APP},
    }


def _status(resp):
    try:
        return int(getattr(resp, "status", resp.get("status") if isinstance(resp, dict) else 500))
    except Exception:
        return 500


def _instance_type(sk):
    resp, content = rest.simpleRequest(
        "/services/server/info?output_mode=json", sessionKey=sk, method="GET", raiseAllErrors=False)
    try:
        return (json.loads(content).get("entry") or [{}])[0].get("content", {}).get("instance_type")
    except Exception:
        return None


def _post(sk, url, doc):
    # simpleRequest may RAISE on 4xx even with raiseAllErrors=False; swallow it and
    # signal "needs fallback" with None.
    try:
        resp, _ = rest.simpleRequest(url, sessionKey=sk, method="POST",
                                     jsonargs=json.dumps(doc), raiseAllErrors=False)
        return _status(resp)
    except Exception:
        return None


def _upsert(sk, collection, key, doc):
    enc = urllib.parse.quote(key, safe="")
    st = _post(sk, "%s/%s/%s" % (KV, collection, enc), doc)   # update existing
    if st is not None and st < 400:
        return st
    return _post(sk, "%s/%s" % (KV, collection), doc) or 0    # insert new (doc carries _key)


def _register_kv(sk):
    out = []
    for name, method, endpoint, desc, props, required, body in TOOLS:
        doc = _doc(name, method, endpoint, desc, props, required, body)
        tid = doc["tool_id"]
        s1 = _upsert(sk, "mcp_tools", tid, doc)
        s2 = _upsert(sk, "mcp_tools_enabled", name,
                     {"_key": name, "tool_id": tid, "collision_ids": []})
        out.append({"name": name, "mcp_tools": s1, "enabled": s2})
    return out


class AutoRegisterHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        super(AutoRegisterHandler, self).__init__()

    @staticmethod
    def _leaf(req):
        # restmap match path trailing segment, e.g. /cim-plicity/ping -> "ping"
        for key in ("path_info", "rest_path", "path"):
            v = req.get(key) if isinstance(req, dict) else None
            if isinstance(v, str) and v:
                return v.rstrip("/").rsplit("/", 1)[-1]
        return ""

    def handle(self, in_string):
        try:
            req = json.loads(in_string) if in_string else {}
            if self._leaf(req) == "ping":
                return {"payload": json.dumps({"ok": True, "app": APP,
                        "tools": [t[0] for t in TOOLS]}), "status": 200}
            sk = req.get("system_authtoken") or (req.get("session") or {}).get("authtoken")
            if rest is None or not sk:
                # 401 for direct callers; the app.conf reload trigger ignores the status
                return {"payload": json.dumps({"ok": False, "error": "no system session key"}), "status": 401}
            itype = _instance_type(sk)
            if itype == "cloud":
                return {"payload": json.dumps({"ok": True, "instance_type": itype,
                        "action": "skipped (native Cloud synced-apps registrar handles it)"}), "status": 200}
            return {"payload": json.dumps({"ok": True, "instance_type": itype,
                    "action": "kv_upsert", "results": _register_kv(sk)}), "status": 200}
        except Exception as exc:  # noqa: BLE001 - never raise out of a reload trigger
            return {"payload": json.dumps({"ok": False, "error": str(exc)}), "status": 200}

    def handleStream(self, handle, in_string):
        raise NotImplementedError("PersistentServerConnectionApplication.handleStream")

    def done(self):
        pass

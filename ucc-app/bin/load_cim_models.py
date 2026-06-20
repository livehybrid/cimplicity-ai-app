import os
import json
import logging

log = logging.getLogger(__name__)

# Hardcoded fallback — only used if Splunk_SA_CIM is not installed
_FALLBACK_CIM_FIELDS = {
    "authentication": [
        {"name": "user", "description": "Username or user identifier"},
        {"name": "src_ip", "description": "Source IP address"},
        {"name": "dest_ip", "description": "Destination IP address"},
        {"name": "action", "description": "Authentication action (success, failure)"},
        {"name": "app", "description": "Application name"},
        {"name": "session_id", "description": "Session identifier"},
    ],
    "network_traffic": [
        {"name": "src_ip", "description": "Source IP address"},
        {"name": "dest_ip", "description": "Destination IP address"},
        {"name": "src_port", "description": "Source port number"},
        {"name": "dest_port", "description": "Destination port number"},
        {"name": "protocol", "description": "Network protocol"},
        {"name": "bytes_in", "description": "Bytes received"},
        {"name": "bytes_out", "description": "Bytes sent"},
    ],
    "web": [
        {"name": "clientip", "description": "Client IP address"},
        {"name": "uri_path", "description": "URI path requested"},
        {"name": "status", "description": "HTTP status code"},
        {"name": "method", "description": "HTTP method"},
        {"name": "user_agent", "description": "User agent string"},
        {"name": "referer", "description": "HTTP referer"},
    ],
}


def _find_cim_app_path():
    """Locate the Splunk_SA_CIM app directory."""
    splunk_home = os.environ.get("SPLUNK_HOME", "/opt/splunk")
    cim_path = os.path.join(splunk_home, "etc", "apps", "Splunk_SA_CIM")
    if os.path.isdir(cim_path):
        return cim_path
    # Try searching sibling apps directory (handles non-standard installs)
    apps_dir = os.path.join(splunk_home, "etc", "apps")
    if os.path.isdir(apps_dir):
        for entry in os.listdir(apps_dir):
            if entry.lower() in ("splunk_sa_cim", "da-ess-contentupdate"):
                candidate = os.path.join(apps_dir, entry)
                if os.path.isdir(candidate):
                    return candidate
    return None


def _parse_model_file(filepath):
    """
    Parse a CIM data model JSON file and return (model_key, [{"name", "description"}]).
    Returns None if the file cannot be parsed.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log.warning("Could not read CIM model file %s: %s", filepath, e)
        return None

    model_name = data.get("modelName") or data.get("displayName")
    if not model_name:
        return None

    model_key = model_name.lower().replace(" ", "_")
    fields = []
    seen = set()

    for obj in data.get("objects", []):
        for field in obj.get("fields", []):
            fname = field.get("fieldName") or field.get("name")
            if not fname or fname in seen:
                continue
            seen.add(fname)
            description = (
                field.get("comment")
                or field.get("description")
                or field.get("displayName")
                or fname
            )
            fields.append({"name": fname, "description": description})

    return (model_key, fields) if fields else None


def load_cim_fields():
    """
    Load CIM field definitions from the installed Splunk_SA_CIM app.
    Falls back to the hardcoded set if the app is not found.
    Returns dict: {model_key: [{"name": str, "description": str}]}
    """
    cim_app_path = _find_cim_app_path()
    if not cim_app_path:
        log.info("Splunk_SA_CIM not found; using fallback CIM field definitions")
        return _FALLBACK_CIM_FIELDS

    models_dir = os.path.join(cim_app_path, "appserver", "static", "data", "models")
    if not os.path.isdir(models_dir):
        log.warning("CIM models directory not found at %s; using fallback", models_dir)
        return _FALLBACK_CIM_FIELDS

    cim_fields = {}
    for filename in os.listdir(models_dir):
        if not filename.endswith(".json"):
            continue
        result = _parse_model_file(os.path.join(models_dir, filename))
        if result:
            model_key, fields = result
            cim_fields[model_key] = fields
            log.debug("Loaded CIM model '%s' (%d fields)", model_key, len(fields))

    if not cim_fields:
        log.warning("No CIM models parsed from %s; using fallback", models_dir)
        return _FALLBACK_CIM_FIELDS

    log.info("Loaded %d CIM models from Splunk_SA_CIM", len(cim_fields))
    return cim_fields

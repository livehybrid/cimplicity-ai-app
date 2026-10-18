"""One log file for every CIM-plicity handler: $SPLUNK_HOME/var/log/splunk/cim-plicity.log.

Why this exists. splunkd runs every persistent REST handler of a given Python
version in ONE shared persistconn/appserver.py process (all of this app's
handlers and other apps' too), importing each script into it on first use.
The handlers used to call logging.basicConfig(filename=...) at import, which
configures the shared ROOT logger and is a silent no-op once the root logger
has any handler. So whichever script the process imported first decided where
everything logged: cim_mapping.py first sent every handler's lines to
cim-plicity_cim_mapping.log, and cim-plicity.log was never created; another
app's handler configuring root first would have taken them all.

So the app logs through its own named logger, "cim-plicity", with its own file
handler and propagate=False: nothing another module does to the root logger
changes where these lines go, and the handler is added once per process however
many handler scripts import this module.

Lines carry a timestamp so Splunk's default monitor of var/log/splunk indexes
them into _internal with event time (default/props.conf sets the sourcetype
cim-plicity:log; previously they had none and were learned as
"cim-plicity-too_small").
"""
import logging
import logging.handlers
import os

LOGGER_NAME = "cim-plicity"
LOG_FILE_NAME = "cim-plicity.log"
LOG_FORMAT = "%(asctime)s %(levelname)s pid=%(process)d %(name)s - %(message)s"
_MARKER = "_cim_plicity_file_handler"


def log_file_path():
    splunk_home = os.environ.get("SPLUNK_HOME", "/opt/splunk")
    return os.path.join(splunk_home, "var", "log", "splunk", LOG_FILE_NAME)


def _app_logger():
    logger = logging.getLogger(LOGGER_NAME)
    if not any(getattr(h, _MARKER, False) for h in logger.handlers):
        try:
            handler = logging.handlers.RotatingFileHandler(
                log_file_path(), maxBytes=25 * 1024 * 1024, backupCount=5, encoding="utf-8")
        except OSError:
            # Never let logging take a handler down: stderr reaches splunkd.log.
            handler = logging.StreamHandler()
        setattr(handler, _MARKER, True)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def get_logger(component):
    """Logger for one handler or module, e.g. get_logger("pii_detection")."""
    return _app_logger().getChild(component)


def set_level(level_name):
    """Apply the [logging] log_level setting to every CIM-plicity logger."""
    level = getattr(logging, str(level_name or "INFO").upper(), None)
    if not isinstance(level, int):
        level = logging.INFO
    _app_logger().setLevel(level)

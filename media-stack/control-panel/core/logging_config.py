"""Single shared logger for the control-panel backend. Every router/service
currently surfaces errors only via core/responses.py's fail() (an HTTP
response, nothing persisted) - this gives the stack one consistent log
location and format instead of scattered print()s or nothing at all.

Overridable via CONTROL_PANEL_LOG_DIR so tests don't write into /logs.

The file handler's mkdir/file-open is deferred to the first actual log call
(_ensure_file_handler, wired in as a logging.Filter) rather than done at
plain import time - some test modules (e.g. test_posters_quality.py) import
services.posters.* standalone, outside the cp_main_app fixture that sets
CONTROL_PANEL_LOG_DIR, and a hard mkdir("/logs") at import time PermissionErrors
in that path. A console-only logger is always safe to construct at import
time; the file handler attaches lazily on first use.
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

_configured = False
_file_handler_attached = False


def log_dir() -> Path:
    return Path(os.environ.get("CONTROL_PANEL_LOG_DIR", "/logs"))


def log_file() -> Path:
    return log_dir() / "control-panel.log"


class _LazyFileHandlerFilter(logging.Filter):
    """Attaches the RotatingFileHandler on the first record actually
    logged, deferring the mkdir/file-open until a log call really happens
    rather than at import time. Always returns True - never filters out
    the record it's attached to."""

    def filter(self, record: logging.LogRecord) -> bool:
        _ensure_file_handler()
        return True


def _ensure_file_handler() -> None:
    global _file_handler_attached
    if _file_handler_attached:
        return
    _file_handler_attached = True
    log_dir().mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(log_file(), maxBytes=10 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.getLogger("control-panel").addHandler(file_handler)


def configure_logging() -> logging.Logger:
    """Idempotent - safe to call from multiple import paths without
    stacking duplicate handlers (same reasoning as api_hit_counts.install())."""
    global _configured
    control_panel_logger = logging.getLogger("control-panel")
    if _configured:
        return control_panel_logger

    control_panel_logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    control_panel_logger.addHandler(console_handler)
    control_panel_logger.addFilter(_LazyFileHandlerFilter())

    _configured = True
    return control_panel_logger


logger = configure_logging()

"""
Persisted control-panel settings (theme, adjustable thresholds, recent
free-text values for the command palette). Same atomic-write pattern as
POSTER_STATE_PATH in app.py: tmp file + json.dump + os.replace, into the
one writable mount (/data, see docker-compose.yml's control-panel
volumes) so values survive a container recreate. Deliberately no schema
validation/migrations - a handful of keys, not a database.
"""
import json
import os
import threading

SETTINGS_PATH = "/data/settings.json"
_LOCK = threading.Lock()

DEFAULTS = {
    "theme": "amber",
    "failed_pending_storm_threshold": 15,
    "loop_review_profile_threshold": 8,
    "recent_values": {},
}


def _load() -> dict:
    try:
        with open(SETTINGS_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    return {**DEFAULTS, **data}


def _save(data: dict) -> None:
    tmp_path = f"{SETTINGS_PATH}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f)
    os.replace(tmp_path, SETTINGS_PATH)


def get_settings() -> dict:
    with _LOCK:
        return _load()


def update_settings(patch: dict) -> dict:
    with _LOCK:
        data = _load()
        data.update({k: v for k, v in patch.items() if k in DEFAULTS})
        _save(data)
        return data


def remember_value(arg_name: str, value: str, keep: int = 5) -> None:
    """Push a used free-text value onto that arg's recent-value list
    (most recent first, de-duplicated, capped at `keep`) so the palette
    can offer it as a one-click chip next time instead of a blank field."""
    with _LOCK:
        data = _load()
        recent = data["recent_values"].setdefault(arg_name, [])
        if value in recent:
            recent.remove(value)
        recent.insert(0, value)
        del recent[keep:]
        _save(data)

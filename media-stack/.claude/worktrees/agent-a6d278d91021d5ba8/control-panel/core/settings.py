"""DB-backed replacement for settings_store.py - same public API
(get_settings/update_settings/remember_value), same DEFAULTS, same
atomic-write guarantee (now a DB transaction/commit instead of tmp-file +
os.replace) - see settings_store.py's own docstring and the plan's
Pattern Grounding table for why the mechanism changes but the contract
doesn't.
"""
import json

from core.db import SessionLocal
from models.setting import Setting

DEFAULTS = {
    "theme": "amber",
    "failed_pending_storm_threshold": 15,
    "loop_review_profile_threshold": 8,
    "recent_values": {},
}


def _load(db) -> dict:
    rows = db.query(Setting).all()
    data = {row.key: json.loads(row.value_json) for row in rows}
    return {**DEFAULTS, **data}


def _persist_key(db, key: str, value) -> None:
    value_json = json.dumps(value)
    row = db.query(Setting).filter(Setting.key == key).first()
    if row is not None:
        row.value_json = value_json
    else:
        db.add(Setting(key=key, value_json=value_json))


def get_settings() -> dict:
    db = SessionLocal()
    try:
        return _load(db)
    finally:
        db.close()


def update_settings(patch: dict) -> dict:
    db = SessionLocal()
    try:
        data = _load(db)
        for key, value in patch.items():
            if key in DEFAULTS:
                data[key] = value
                _persist_key(db, key, value)
        db.commit()
        return data
    finally:
        db.close()


def remember_value(arg_name: str, value: str, keep: int = 5) -> None:
    db = SessionLocal()
    try:
        data = _load(db)
        recent = data["recent_values"].setdefault(arg_name, [])
        if value in recent:
            recent.remove(value)
        recent.insert(0, value)
        del recent[keep:]
        _persist_key(db, "recent_values", data["recent_values"])
        db.commit()
    finally:
        db.close()

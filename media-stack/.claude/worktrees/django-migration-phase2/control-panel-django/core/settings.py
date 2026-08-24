"""DB-backed settings store, ported from the FastAPI-era
control-panel/core/settings.py for the Django/DRF rewrite.

Same public API (get_settings/update_settings/remember_value), same DEFAULTS,
same atomic-write guarantee (now a Django ORM update_or_create commit instead
of SQLAlchemy's Session + commit). The Setting model lives in core.models with
db_table="settings" (Phase 1, schema parity with the preserved
/data/control-panel.db), so this module is a thin ORM wrapper over it.

Transforms applied vs. the FastAPI-era source:
1. core.db.SessionLocal() / db.query(Setting) / db.commit() becomes the
   Django ORM (Setting.objects.all() / update_or_create) - same contract,
   no more session lifecycle to manage.
2. _load/_persist_key drop their `db` parameter (Django queries don't need
   an explicit session handle).
"""
import json

from core.models import Setting

DEFAULTS = {
    "theme": "amber",
    "failed_pending_storm_threshold": 15,
    "loop_review_profile_threshold": 8,
    "recent_values": {},
}


def _load() -> dict:
    data = {row.key: json.loads(row.value_json) for row in Setting.objects.all()}
    return {**DEFAULTS, **data}


def _persist_key(key: str, value) -> None:
    Setting.objects.update_or_create(key=key, defaults={"value_json": json.dumps(value)})


def get_settings() -> dict:
    return _load()


def update_settings(patch: dict) -> dict:
    data = _load()
    for key, value in patch.items():
        if key in DEFAULTS:
            data[key] = value
            _persist_key(key, value)
    return data


def remember_value(arg_name: str, value: str, keep: int = 5) -> None:
    data = _load()
    recent = data["recent_values"].setdefault(arg_name, [])
    if value in recent:
        recent.remove(value)
    recent.insert(0, value)
    del recent[keep:]
    _persist_key("recent_values", data["recent_values"])

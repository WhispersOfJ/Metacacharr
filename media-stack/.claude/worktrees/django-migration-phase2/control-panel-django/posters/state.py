"""Poster-sync cooldown persistence, ported verbatim from the FastAPI-era
control-panel/services/posters/state.py for the Django/DRF rewrite.

Isolated from candidates.py (pure lookup logic) and services.py (job
state/background workers) because this is the one piece of poster-sync
with actual on-disk state - easiest to unit-test in isolation. No
transform needed vs. the FastAPI-era source - this module never touched
FastAPI or core.responses.fail() at all.
"""
import json
import os
import threading
import time

# Per-item cooldown, auto mode only (run_poster_sync) - manual picks via
# posters.services.apply_poster (the review picker, or a human clicking a
# candidate) always go through immediately, this only throttles the
# unattended 3x/day-Movies + 1x/day-Shows systemd timers from reapplying a
# poster to the same item more than once every 48h. Persisted to /data
# (see docker-compose.yml's control-panel volumes) as one small JSON file
# {ratingKey: last-applied unix timestamp} so the cooldown survives a
# container restart/recreate instead of resetting every deploy - not a
# database, this app deliberately has none elsewhere.
POSTER_STATE_PATH = "/data/poster-sync-state.json"
POSTER_COOLDOWN_SECONDS = 48 * 3600
POSTER_STATE_LOCK = threading.Lock()


def load_poster_state() -> dict:
    try:
        with open(POSTER_STATE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_poster_state(state: dict) -> None:
    tmp_path = f"{POSTER_STATE_PATH}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(state, f)
    os.replace(tmp_path, POSTER_STATE_PATH)


def poster_cooldown_remaining(state: dict, rating_key: str) -> float:
    """Seconds left in the 48h cooldown for this item, 0 if clear."""
    last = state.get(rating_key)
    if last is None:
        return 0
    remaining = POSTER_COOLDOWN_SECONDS - (time.time() - last)
    return max(0, remaining)

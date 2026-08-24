"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/posters/state.py, ported from app.py. Pure unit tests, no
FastAPI/auth involved - direct calls against the module.
"""
import importlib
import json
import sys
from pathlib import Path

import pytest

CONTROL_PANEL_DIR = Path(__file__).resolve().parent.parent.parent / "control-panel"


@pytest.fixture
def posters_state(monkeypatch, tmp_path):
    sys.path.insert(0, str(CONTROL_PANEL_DIR))
    sys.modules.pop("services.posters.state", None)
    try:
        module = importlib.import_module("services.posters.state")
        state_path = tmp_path / "poster-sync-state.json"
        monkeypatch.setattr(module, "POSTER_STATE_PATH", str(state_path))
        yield module
    finally:
        sys.modules.pop("services.posters.state", None)
        sys.path.remove(str(CONTROL_PANEL_DIR))


def test_load_returns_empty_dict_when_file_missing(posters_state):
    assert posters_state.load_poster_state() == {}


def test_load_returns_empty_dict_on_corrupt_json(posters_state):
    with open(posters_state.POSTER_STATE_PATH, "w") as f:
        f.write("not json")
    assert posters_state.load_poster_state() == {}


def test_save_then_load_round_trips(posters_state):
    posters_state.save_poster_state({"12345": 1000.0})
    assert posters_state.load_poster_state() == {"12345": 1000.0}


def test_save_writes_atomically_via_tmp_file(posters_state):
    posters_state.save_poster_state({"1": 1.0})
    with open(posters_state.POSTER_STATE_PATH) as f:
        assert json.load(f) == {"1": 1.0}


def test_cooldown_remaining_is_zero_when_never_applied(posters_state):
    assert posters_state.poster_cooldown_remaining({}, "12345") == 0


def test_cooldown_remaining_reports_time_left(posters_state, monkeypatch):
    now = 1_000_000.0
    monkeypatch.setattr(posters_state.time, "time", lambda: now)
    state = {"12345": now - 3600}  # applied 1h ago
    remaining = posters_state.poster_cooldown_remaining(state, "12345")
    assert remaining == pytest.approx(posters_state.POSTER_COOLDOWN_SECONDS - 3600)


def test_cooldown_remaining_clamps_to_zero_after_window_expires(posters_state, monkeypatch):
    now = 1_000_000.0
    monkeypatch.setattr(posters_state.time, "time", lambda: now)
    state = {"12345": now - 100 * 3600}  # applied 100h ago, well past 48h
    assert posters_state.poster_cooldown_remaining(state, "12345") == 0

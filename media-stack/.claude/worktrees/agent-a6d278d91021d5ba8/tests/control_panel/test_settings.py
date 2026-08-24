"""Gate tests for core/settings.py - DB-backed settings store. First-ever
coverage for this module (settings_store.py's tests were app.py-era and
never ported to this DB-backed replacement)."""
import pytest


@pytest.fixture
def settings_module(cp_main_app):
    import core.settings as module
    return module


def test_get_settings_returns_defaults_when_empty(settings_module):
    data = settings_module.get_settings()
    assert data["theme"] == "amber"
    assert data["failed_pending_storm_threshold"] == 15


def test_update_settings_persists_known_key(settings_module):
    settings_module.update_settings({"theme": "green"})
    assert settings_module.get_settings()["theme"] == "green"


def test_update_settings_ignores_unknown_key(settings_module):
    result = settings_module.update_settings({"not_a_real_setting": "x"})
    assert "not_a_real_setting" not in result


def test_update_settings_overwrites_existing_row(settings_module):
    settings_module.update_settings({"theme": "green"})
    settings_module.update_settings({"theme": "amber"})
    assert settings_module.get_settings()["theme"] == "amber"


def test_remember_value_adds_to_recent(settings_module):
    settings_module.remember_value("movie_title", "Inception")
    data = settings_module.get_settings()
    assert data["recent_values"]["movie_title"] == ["Inception"]


def test_remember_value_dedupes_and_moves_to_front(settings_module):
    settings_module.remember_value("movie_title", "A")
    settings_module.remember_value("movie_title", "B")
    settings_module.remember_value("movie_title", "A")
    data = settings_module.get_settings()
    assert data["recent_values"]["movie_title"] == ["A", "B"]


def test_remember_value_caps_at_keep_limit(settings_module):
    for v in ["A", "B", "C", "D", "E", "F"]:
        settings_module.remember_value("movie_title", v, keep=3)
    data = settings_module.get_settings()
    assert data["recent_values"]["movie_title"] == ["F", "E", "D"]

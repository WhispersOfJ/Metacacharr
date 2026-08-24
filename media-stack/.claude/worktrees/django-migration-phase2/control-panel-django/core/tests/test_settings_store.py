"""Tests for core/settings.py - the DB-backed settings store ported from
the FastAPI-era core/settings.py (the Setting MODEL itself is covered in
test_models.py; this file covers the get/update/remember store API)."""

import pytest

from core.models import Setting
from core.settings import DEFAULTS, get_settings, remember_value, update_settings


@pytest.mark.django_db
def test_get_settings_returns_defaults_when_store_empty():
    assert get_settings() == DEFAULTS


@pytest.mark.django_db
def test_update_settings_persists_known_keys_and_merges_defaults():
    result = update_settings({"theme": "midnight"})
    assert result["theme"] == "midnight"
    # Unpatched defaults remain present in the returned snapshot.
    assert result["failed_pending_storm_threshold"] == 15
    assert Setting.objects.get(key="theme").value_json == '"midnight"'


@pytest.mark.django_db
def test_update_settings_ignores_unknown_keys():
    result = update_settings({"not_a_real_setting": 123})
    assert "not_a_real_setting" not in result
    assert Setting.objects.count() == 0


@pytest.mark.django_db
def test_update_settings_is_persistent_across_calls():
    update_settings({"theme": "midnight"})
    assert get_settings()["theme"] == "midnight"


@pytest.mark.django_db
def test_remember_value_keeps_only_most_recent_five():
    for value in ("a", "b", "c", "d", "e", "f"):
        remember_value("arg", value)
    assert get_settings()["recent_values"]["arg"] == ["f", "e", "d", "c", "b"]


@pytest.mark.django_db
def test_remember_value_moves_repeat_to_front_without_duplicates():
    remember_value("arg", "a")
    remember_value("arg", "b")
    remember_value("arg", "a")
    assert get_settings()["recent_values"]["arg"] == ["a", "b"]


@pytest.mark.django_db
def test_remember_value_tracks_multiple_arguments_independently():
    remember_value("arg_one", "x")
    remember_value("arg_two", "y")
    recent = get_settings()["recent_values"]
    assert recent["arg_one"] == ["x"]
    assert recent["arg_two"] == ["y"]

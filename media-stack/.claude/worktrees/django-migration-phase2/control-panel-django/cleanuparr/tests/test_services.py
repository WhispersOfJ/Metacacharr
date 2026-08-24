import os
import sqlite3

import pytest

from cleanuparr import services
from core.api_base import ServiceError


def _make_cleanuparr_db(path, configs, instances):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE arr_configs (type TEXT)")
    con.execute("CREATE TABLE arr_instances (name TEXT)")
    con.executemany("INSERT INTO arr_configs (type) VALUES (?)", [(t,) for t in configs])
    con.executemany("INSERT INTO arr_instances (name) VALUES (?)", [(n,) for n in instances])
    con.commit()
    con.close()


def _make_events_db(path, strikes, download_items):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE download_items (id INTEGER PRIMARY KEY, title TEXT)")
    con.execute(
        "CREATE TABLE strikes (id INTEGER PRIMARY KEY, created_at TEXT, type TEXT, download_item_id INTEGER)"
    )
    con.executemany(
        "INSERT INTO download_items (id, title) VALUES (?, ?)", download_items
    )
    con.executemany(
        "INSERT INTO strikes (created_at, type, download_item_id) VALUES (?, ?, ?)", strikes
    )
    con.commit()
    con.close()


def test_check_instances_reports_gaps(tmp_path, monkeypatch):
    """radarr and sonarr are configured; only radarr has a connected
    instance - sonarr should show up as a gap, readarr never counts even
    if configured without an instance."""
    monkeypatch.setattr(services, "HOST_CONFIG_DIR", str(tmp_path))
    cleanuparr_dir = tmp_path / "cleanuparr"
    cleanuparr_dir.mkdir()
    _make_cleanuparr_db(
        str(cleanuparr_dir / "cleanuparr.db"),
        configs=["radarr", "sonarr", "readarr"],
        instances=["Radarr"],
    )
    result = services.check_instances()
    assert result["connected"] == ["radarr"]
    assert result["gaps"] == ["sonarr"]
    assert "sonarr" in result["message"]


def test_check_instances_no_gaps(tmp_path, monkeypatch):
    monkeypatch.setattr(services, "HOST_CONFIG_DIR", str(tmp_path))
    cleanuparr_dir = tmp_path / "cleanuparr"
    cleanuparr_dir.mkdir()
    _make_cleanuparr_db(
        str(cleanuparr_dir / "cleanuparr.db"),
        configs=["radarr"],
        instances=["Radarr"],
    )
    result = services.check_instances()
    assert result["gaps"] == []
    assert result["message"] == "Every configured app type has a connected instance."


def test_check_instances_missing_db_raises_service_error(tmp_path, monkeypatch):
    """A missing cleanuparr.db must raise ServiceError(502), matching
    router.py's real fail() behavior."""
    monkeypatch.setattr(services, "HOST_CONFIG_DIR", str(tmp_path))
    with pytest.raises(ServiceError) as exc_info:
        services.check_instances()
    assert exc_info.value.status_code == 502
    assert "not present" in str(exc_info.value.detail)


def test_recent_strikes_reads_events_db(tmp_path, monkeypatch):
    monkeypatch.setattr(services, "HOST_CONFIG_DIR", str(tmp_path))
    cleanuparr_dir = tmp_path / "cleanuparr"
    cleanuparr_dir.mkdir()
    _make_events_db(
        str(cleanuparr_dir / "events.db"),
        strikes=[
            ("2026-08-20T10:00:00", "stalled", 1),
            ("2026-08-21T10:00:00", "slow", 2),
        ],
        download_items=[(1, "Movie One"), (2, "Movie Two")],
    )
    result = services.recent_strikes(limit=15)
    assert result["total"] == 2
    assert len(result["items"]) == 2
    assert result["items"][0]["title"] == "Movie Two"
    assert result["items"][0]["created_at"] == "2026-08-21T10:00:00"


def test_recent_strikes_respects_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(services, "HOST_CONFIG_DIR", str(tmp_path))
    cleanuparr_dir = tmp_path / "cleanuparr"
    cleanuparr_dir.mkdir()
    _make_events_db(
        str(cleanuparr_dir / "events.db"),
        strikes=[
            ("2026-08-19T10:00:00", "stalled", 1),
            ("2026-08-20T10:00:00", "slow", 1),
            ("2026-08-21T10:00:00", "malware", 1),
        ],
        download_items=[(1, "Movie One")],
    )
    result = services.recent_strikes(limit=2)
    assert result["total"] == 3
    assert len(result["items"]) == 2


def test_recent_strikes_missing_db_raises_service_error(tmp_path, monkeypatch):
    monkeypatch.setattr(services, "HOST_CONFIG_DIR", str(tmp_path))
    with pytest.raises(ServiceError) as exc_info:
        services.recent_strikes(limit=15)
    assert exc_info.value.status_code == 502
    assert "not present" in str(exc_info.value.detail)

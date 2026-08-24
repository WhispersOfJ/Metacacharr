"""Migration-gap fix: services/cleanuparr/router.py, ported from app.py.
Covers auth gating and both sqlite-backed routes (instances, strikes).
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient


def _service_key_header(main_module):
    from core.security import hash_api_key
    from models.api_key import ApiKey

    db = main_module.SessionLocal()
    try:
        db.add(ApiKey(name="test-key", key_hash=hash_api_key("raw-service-key")))
        db.commit()
    finally:
        db.close()
    return {"X-Api-Key": "raw-service-key"}


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/cleanuparr/instances"),
    ("GET", "/api/cleanuparr/strikes"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path)
    assert resp.status_code == 401


def test_instances_502s_when_db_missing(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.cleanuparr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/cleanuparr/instances", headers=headers)
    assert resp.status_code == 502


def test_instances_reports_no_gaps_when_all_connected(cp_main_app, monkeypatch, tmp_path):
    cleanuparr_dir = tmp_path / "cleanuparr"
    cleanuparr_dir.mkdir(parents=True)
    db_path = cleanuparr_dir / "cleanuparr.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE arr_configs (type TEXT)")
    con.execute("CREATE TABLE arr_instances (name TEXT)")
    con.execute("INSERT INTO arr_configs VALUES ('radarr')")
    con.execute("INSERT INTO arr_configs VALUES ('sonarr')")
    con.execute("INSERT INTO arr_instances VALUES ('Radarr')")
    con.execute("INSERT INTO arr_instances VALUES ('Sonarr')")
    con.commit()
    con.close()
    monkeypatch.setattr("services.cleanuparr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/cleanuparr/instances", headers=headers)
    body = resp.json()
    assert "gaps" not in body
    assert "Every configured" in body["message"]


def test_instances_flags_configured_but_unconnected_type(cp_main_app, monkeypatch, tmp_path):
    cleanuparr_dir = tmp_path / "cleanuparr"
    cleanuparr_dir.mkdir(parents=True)
    db_path = cleanuparr_dir / "cleanuparr.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE arr_configs (type TEXT)")
    con.execute("CREATE TABLE arr_instances (name TEXT)")
    con.execute("INSERT INTO arr_configs VALUES ('radarr')")
    con.execute("INSERT INTO arr_configs VALUES ('sonarr')")
    con.execute("INSERT INTO arr_instances VALUES ('Radarr')")
    con.commit()
    con.close()
    monkeypatch.setattr("services.cleanuparr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/cleanuparr/instances", headers=headers)
    body = resp.json()
    assert body["gaps"] == ["sonarr"]


def test_instances_ignores_readarr_gap(cp_main_app, monkeypatch, tmp_path):
    cleanuparr_dir = tmp_path / "cleanuparr"
    cleanuparr_dir.mkdir(parents=True)
    db_path = cleanuparr_dir / "cleanuparr.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE arr_configs (type TEXT)")
    con.execute("CREATE TABLE arr_instances (name TEXT)")
    con.execute("INSERT INTO arr_configs VALUES ('readarr')")
    con.commit()
    con.close()
    monkeypatch.setattr("services.cleanuparr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/cleanuparr/instances", headers=headers)
    body = resp.json()
    assert "gaps" not in body
    assert "Every configured" in body["message"]


def test_strikes_502s_when_db_missing(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.cleanuparr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/cleanuparr/strikes", headers=headers)
    assert resp.status_code == 502


def test_strikes_returns_recent_first_respecting_limit(cp_main_app, monkeypatch, tmp_path):
    cleanuparr_dir = tmp_path / "cleanuparr"
    cleanuparr_dir.mkdir(parents=True)
    db_path = cleanuparr_dir / "events.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE download_items (id INTEGER PRIMARY KEY, title TEXT)")
    con.execute("CREATE TABLE strikes (created_at TEXT, type TEXT, download_item_id INTEGER)")
    con.execute("INSERT INTO download_items VALUES (1, 'Movie A')")
    con.execute("INSERT INTO download_items VALUES (2, 'Movie B')")
    con.execute("INSERT INTO strikes VALUES ('2026-08-01T00:00:00', 'stalled', 1)")
    con.execute("INSERT INTO strikes VALUES ('2026-08-02T00:00:00', 'slow', 2)")
    con.execute("INSERT INTO strikes VALUES ('2026-08-03T00:00:00', 'malware', 1)")
    con.commit()
    con.close()
    monkeypatch.setattr("services.cleanuparr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/cleanuparr/strikes?limit=2", headers=headers)
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["items"][0]["created_at"] == "2026-08-03T00:00:00"
    assert body["items"][0]["title"] == "Movie A"

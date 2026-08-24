"""services/mdblist/router.py - moved out of services/arr/router.py
(2026-08-08) into its own package, mirroring services/letterboxd/,
with app/sonarr_app anime routing and a tracked-list nightly sync."""
from unittest.mock import MagicMock

import httpx
from fastapi.testclient import TestClient


def _login(client, main_module, password="correct-horse-battery-staple"):
    from core.security import hash_password
    from models.user import User

    db = main_module.SessionLocal()
    try:
        db.add(User(username="admin", password_hash=hash_password(password)))
        db.commit()
    finally:
        db.close()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert resp.status_code == 200


def _service_key_header(main_module):
    from core.security import hash_api_key
    from models.api_key import ApiKey

    db = main_module.SessionLocal()
    try:
        db.add(ApiKey(name="healthcheck-cron", key_hash=hash_api_key("raw-service-key")))
        db.commit()
    finally:
        db.close()
    return {"X-Api-Key": "raw-service-key"}


def _json_response(payload, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    return resp


MDBLIST_ITEMS_RESPONSE = {
    "movies": [{"title": "Your Name.", "ids": {"tmdb": 372058}}],
    "shows": [{"title": "Frieren", "ids": {"tvdb": 424536}}],
    "pagination": {"has_more": False},
}


def _fake_get_factory(radarr_port="7878", sonarr_port="8989"):
    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        if "mdblist.com" in url:
            return _json_response(MDBLIST_ITEMS_RESPONSE)
        if "/rootfolder" in url:
            return _json_response([{"path": "/data/movies"}])
        if "/qualityprofile" in url:
            return _json_response([{"id": 1, "name": "Unlimited"}])
        if "/movie/lookup/tmdb" in url:
            return _json_response({"title": "Your Name.", "year": 2016})
        if "/series/lookup" in url:
            return _json_response([{"title": "Frieren", "tvdbId": 424536}])
        if "/movie" in url:
            return _json_response([])
        if "/series" in url:
            return _json_response([])
        return _json_response({})
    return fake_get


def test_mdblist_import_rejects_non_mdblist_url(cp_main_app, monkeypatch):
    monkeypatch.setenv("MDBLIST_KEY", "test-mdblist-key")
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/mdblist/import-list", json={"list_url": "https://example.com/not-mdblist"})
    assert resp.status_code == 400


def test_mdblist_import_requires_api_key(cp_main_app, monkeypatch):
    monkeypatch.delenv("MDBLIST_KEY", raising=False)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/mdblist/import-list", json={"list_url": "https://mdblist.com/lists/bear/toplist/"})
    assert resp.status_code == 500


def test_mdblist_import_rejects_unknown_app(cp_main_app, monkeypatch):
    monkeypatch.setenv("MDBLIST_KEY", "test-mdblist-key")
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post(
        "/api/mdblist/import-list",
        json={"list_url": "https://mdblist.com/lists/bear/toplist/", "app": "not-a-real-app"},
    )
    assert resp.status_code == 400


def test_mdblist_import_accepts_service_key(cp_main_app, monkeypatch):
    monkeypatch.setenv("MDBLIST_KEY", "test-mdblist-key")
    monkeypatch.setattr(httpx, "get", _fake_get_factory())
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _json_response({"id": 1}))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post(
        "/api/mdblist/import-list", json={"list_url": "https://mdblist.com/lists/bear/toplist/"}, headers=headers,
    )
    assert resp.status_code == 200


def test_mdblist_track_rejects_unknown_sonarr_app(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post(
        "/api/mdblist/track",
        json={"url": "https://mdblist.com/lists/bear/toplist/", "sonarr_app": "not-a-real-app"},
    )
    assert resp.status_code == 400


def test_mdblist_track_rejects_duplicate_url(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/mdblist/track", json={"url": "https://mdblist.com/lists/bear/toplist/"})
    assert resp.status_code == 200
    resp = client.post("/api/mdblist/track", json={"url": "https://mdblist.com/lists/bear/toplist/"})
    assert resp.status_code == 409


def test_track_untrack_and_list_tracked_mdblist_lists(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)

    resp = client.post(
        "/api/mdblist/track",
        json={"url": "https://mdblist.com/lists/bear/toplist/", "label": "Bear's toplist", "app": "radarr", "sonarr_app": "sonarr"},
    )
    assert resp.status_code == 200
    list_id = resp.json()["id"]

    resp = client.get("/api/mdblist/tracked")
    assert resp.status_code == 200
    lists = resp.json()["lists"]
    row = next(x for x in lists if x["id"] == list_id)
    assert row["label"] == "Bear's toplist"
    assert row["app"] == "radarr"
    assert row["sonarrApp"] == "sonarr"

    resp = client.post("/api/mdblist/untrack", json={"url": "https://mdblist.com/lists/bear/toplist/"})
    assert resp.status_code == 200

    resp = client.get("/api/mdblist/tracked")
    assert resp.json()["lists"] == []


def test_sync_tick_requires_service_key_or_session(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/mdblist/sync-tick")
    assert resp.status_code == 401


def test_sync_tick_passes_tracked_app_to_import(cp_main_app, monkeypatch):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    client.post(
        "/api/mdblist/track",
        json={"url": "https://mdblist.com/lists/bear/toplist/", "app": "radarr", "sonarr_app": "sonarr"},
    )

    calls = []

    def fake_run_import(url, **kwargs):
        calls.append(kwargs)
        return {"radarr": None, "sonarr": None}

    monkeypatch.setattr("services.mdblist.router._run_import", fake_run_import)
    resp = client.post("/api/mdblist/sync-tick")
    assert resp.status_code == 200
    assert calls[0]["app"] == "radarr"
    assert calls[0]["sonarr_app"] == "sonarr"


def test_history_reflects_import_run(cp_main_app, monkeypatch):
    monkeypatch.setenv("MDBLIST_KEY", "test-mdblist-key")
    monkeypatch.setattr(httpx, "get", _fake_get_factory())
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _json_response({"id": 1}))
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    client.post("/api/mdblist/import-list", json={"list_url": "https://mdblist.com/lists/bear/toplist/"})

    resp = client.get("/api/mdblist/history")
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    assert runs[0]["listUrl"] == "https://mdblist.com/lists/bear/toplist/"
    assert runs[0]["radarrAdded"] == 1
    assert runs[0]["sonarrAdded"] == 1

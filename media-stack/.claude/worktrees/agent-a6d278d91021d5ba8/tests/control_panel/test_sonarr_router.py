"""services/sonarr/router.py - POST /api/arr/sonarr/monitor-episodes-fix.
First-ever coverage for this router."""
from unittest.mock import MagicMock

import httpx
from fastapi.testclient import TestClient


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


def test_monitor_episodes_fix_requires_auth(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/arr/sonarr/monitor-episodes-fix")
    assert resp.status_code == 401


def test_monitor_episodes_fix_series_lookup_failure_502s(cp_main_app, monkeypatch):
    import services.sonarr.router as router_module

    def raise_error(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(router_module.httpx, "get", raise_error)

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/arr/sonarr/monitor-episodes-fix", headers=headers)
    assert resp.status_code == 502


def test_monitor_episodes_fix_skips_specials_season(cp_main_app, monkeypatch):
    import services.sonarr.router as router_module
    put_calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if url.endswith("/series"):
            resp.json.return_value = [{"id": 1, "monitored": True}]
        elif url.endswith("/episode"):
            resp.json.return_value = [
                {"id": 10, "seasonNumber": 0, "monitored": False},
                {"id": 11, "seasonNumber": 1, "monitored": False},
            ]
        return resp

    def fake_put(url, json=None, headers=None, timeout=None):
        put_calls.append(json)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        return resp

    monkeypatch.setattr(router_module.httpx, "get", fake_get)
    monkeypatch.setattr(router_module.httpx, "put", fake_put)

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/arr/sonarr/monitor-episodes-fix", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["fixed"] == 1
    assert put_calls[0]["episodeIds"] == [11]


def test_monitor_episodes_fix_no_unmonitored_episodes(cp_main_app, monkeypatch):
    import services.sonarr.router as router_module

    def fake_get(url, params=None, headers=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if url.endswith("/series"):
            resp.json.return_value = [{"id": 1, "monitored": True}]
        elif url.endswith("/episode"):
            resp.json.return_value = [{"id": 10, "seasonNumber": 1, "monitored": True}]
        return resp

    monkeypatch.setattr(router_module.httpx, "get", fake_get)

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/arr/sonarr/monitor-episodes-fix", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["fixed"] == 0

"""services/prowlarr/router.py - GET /api/prowlarr/indexers. First-ever
coverage for this router."""
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


def test_indexers_missing_key_fails_503(cp_main_app, monkeypatch):
    import core.arr_client as arr_client
    monkeypatch.setitem(arr_client.PROWLARR_CFG, "key", None)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/prowlarr/indexers", headers=headers)
    assert resp.status_code == 503


def test_indexers_returns_sorted_enabled_summary(cp_main_app, monkeypatch):
    import core.arr_client as arr_client
    monkeypatch.setitem(arr_client.PROWLARR_CFG, "key", "test-prowlarr-key")

    def fake_get(url, headers=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = [
            {"name": "Zeta Indexer", "enable": True, "priority": 25},
            {"name": "Alpha Indexer", "enable": False, "priority": 25},
        ]
        return resp

    import services.prowlarr.router as router_module
    monkeypatch.setattr(router_module.httpx, "get", fake_get)

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/prowlarr/indexers", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["name"] == "Alpha Indexer"
    assert "1/2 indexers enabled" in body["message"]


def test_indexers_http_error_fails_502(cp_main_app, monkeypatch):
    import core.arr_client as arr_client
    monkeypatch.setitem(arr_client.PROWLARR_CFG, "key", "test-prowlarr-key")

    def raise_error(*a, **k):
        raise httpx.ConnectError("refused")

    import services.prowlarr.router as router_module
    monkeypatch.setattr(router_module.httpx, "get", raise_error)

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/prowlarr/indexers", headers=headers)
    assert resp.status_code == 502


def test_indexers_requires_auth(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/prowlarr/indexers")
    assert resp.status_code == 401

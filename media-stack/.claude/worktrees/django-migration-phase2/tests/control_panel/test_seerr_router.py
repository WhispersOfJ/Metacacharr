"""Migration-gap fix: services/seerr/router.py, ported from app.py.
Covers auth gating, missing-key 503, upstream failure, and the request
list's title-fallback shaping.
"""
import json
from unittest.mock import MagicMock

import httpx
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


def _json_response(payload, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    return resp


def _write_settings(tmp_path, api_key="test-seerr-key"):
    seerr_dir = tmp_path / "seerr"
    seerr_dir.mkdir(parents=True)
    (seerr_dir / "settings.json").write_text(json.dumps({"main": {"apiKey": api_key}}))


def test_requests_requires_auth(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/seerr/requests")
    assert resp.status_code == 401


def test_requests_503s_when_key_missing(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.seerr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/seerr/requests", headers=headers)
    assert resp.status_code == 503


def test_requests_502s_on_upstream_failure(cp_main_app, monkeypatch, tmp_path):
    _write_settings(tmp_path)
    monkeypatch.setattr("services.seerr.router.HOST_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response({}, status_code=500))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/seerr/requests", headers=headers)
    assert resp.status_code == 502


def test_requests_falls_back_to_tmdb_id_when_slug_missing(cp_main_app, monkeypatch, tmp_path):
    _write_settings(tmp_path)
    monkeypatch.setattr("services.seerr.router.HOST_CONFIG_DIR", str(tmp_path))
    payload = {"results": [{
        "media": {"tmdbId": 603, "mediaType": "movie"},
        "requestedBy": {"displayName": "Bear"},
        "status": 1,
        "createdAt": "2026-08-06T00:00:00Z",
    }]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response(payload))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/seerr/requests", headers=headers)
    body = resp.json()
    assert body["items"][0]["title"] == "tmdb:603"
    assert body["items"][0]["requestedBy"] == "Bear"


def test_requests_prefers_external_service_slug(cp_main_app, monkeypatch, tmp_path):
    _write_settings(tmp_path)
    monkeypatch.setattr("services.seerr.router.HOST_CONFIG_DIR", str(tmp_path))
    payload = {"results": [{
        "media": {"tmdbId": 603, "mediaType": "movie", "externalServiceSlug": "the-matrix"},
        "requestedBy": {"displayName": "Bear"},
        "status": 1,
        "createdAt": "2026-08-06T00:00:00Z",
    }]}
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["params"] = params
        captured["headers"] = headers
        return _json_response(payload)

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    key_headers = _service_key_header(cp_main_app)
    resp = client.get("/api/seerr/requests?status=approved", headers=key_headers)
    body = resp.json()
    assert body["items"][0]["title"] == "the-matrix"
    assert captured["params"]["filter"] == "approved"
    assert captured["headers"]["X-Api-Key"] == "test-seerr-key"

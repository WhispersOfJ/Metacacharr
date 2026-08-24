"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/nzbdav/router.py, ported from app.py. Covers auth gating, response
shaping for queue/history, dedup-config-check's healthy/unhealthy branches,
and delete-failures' partial-failure accounting.
"""
from unittest.mock import MagicMock

import httpx
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


def _json_response(payload, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    return resp


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/nzbdav/queue"),
    ("GET", "/api/nzbdav/history"),
    ("GET", "/api/nzbdav/dedup-config-check"),
    ("GET", "/api/nzbdav/stats"),
    ("POST", "/api/nzbdav/delete-failures"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path)
    assert resp.status_code == 401


def test_queue_shapes_slots(cp_main_app, monkeypatch):
    monkeypatch.setattr("services.nzbdav.router.nzbdav_api", lambda mode, **k: {
        "queue": {"slots": [{"filename": "Show.S01E01", "cat": "tv", "status": "Downloading",
                              "percentage": "50", "mb": "1000", "mbleft": "500"}]},
    })
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/nzbdav/queue", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == [{"name": "Show.S01E01", "category": "tv", "status": "Downloading",
                             "percentage": "50", "size_mb": "1000", "size_left_mb": "500"}]


def test_dedup_config_check_healthy(cp_main_app, monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _json_response(
        {"configItems": [{"configValue": "mark-failed"}]}))
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/nzbdav/dedup-config-check", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["healthy"] is True
    assert body["value"] == "mark-failed"


def test_dedup_config_check_flags_unhealthy_value(cp_main_app, monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _json_response(
        {"configItems": [{"configValue": "increment"}]}))
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/nzbdav/dedup-config-check", headers=headers)
    body = resp.json()
    assert body["healthy"] is False
    assert "importBlocked bug" in body["message"]


def test_stats_aggregates_queue_and_history(cp_main_app, monkeypatch):
    def fake_nzbdav_api(mode, **kwargs):
        if mode == "queue":
            return {"queue": {"slots": [{"mbleft": "100"}, {"mbleft": "50"}]}}
        return {"history": {"slots": [{"status": "Completed"}, {"status": "Failed"}, {"status": "Failed"}]}}

    monkeypatch.setattr("services.nzbdav.router.nzbdav_api", fake_nzbdav_api)
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/nzbdav/stats", headers=headers)
    body = resp.json()
    assert body["queued"] == 2
    assert body["mb_left"] == 150
    assert body["history_count"] == 3
    assert body["history_failed"] == 2


def test_delete_failures_reports_no_failures_shortcut(cp_main_app, monkeypatch):
    monkeypatch.setattr("services.nzbdav.router.nzbdav_api", lambda mode, **k: {"history": {"slots": []}})
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/nzbdav/delete-failures", headers=headers)
    body = resp.json()
    assert body["deleted"] == 0
    assert body["errors"] == 0


def test_delete_failures_counts_partial_success(cp_main_app, monkeypatch):
    monkeypatch.setattr("services.nzbdav.router.nzbdav_api", lambda mode, **k: {"history": {"slots": [
        {"nzo_id": "1", "name": "a", "status": "Failed"},
        {"nzo_id": "2", "name": "b", "status": "Failed"},
    ]}})

    def fake_get(url, params=None, **kwargs):
        if params.get("value") == "1":
            return _json_response({"status": True})
        return _json_response({"status": False, "error": "not found"})

    monkeypatch.setattr(httpx, "get", fake_get)
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/nzbdav/delete-failures", headers=headers)
    body = resp.json()
    assert body["deleted"] == 1
    assert len(body["errors"]) == 1
    assert "not found" in body["errors"][0]

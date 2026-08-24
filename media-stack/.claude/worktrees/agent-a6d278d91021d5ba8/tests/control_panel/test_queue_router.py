"""services/queue/router.py - GET /api/queue-status, the cross-app download
queue aggregator. First-ever coverage for this router (it 404'd in
production before being ported, per its own module docstring)."""
import pytest
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


@pytest.fixture
def queue_module(cp_main_app):
    import services.queue.router as module
    return module


def test_bucket_arr_item_importing_state(queue_module):
    q = {"id": 1, "title": "Movie", "size": 1000, "sizeleft": 0, "trackedDownloadState": "importPending"}
    bucket, item = queue_module._bucket_arr_item(q, {})
    assert bucket == "importing"


def test_bucket_arr_item_queued_when_sizeleft_zero(queue_module):
    q = {"id": 1, "title": "Movie", "size": 1000, "sizeleft": 0}
    bucket, item = queue_module._bucket_arr_item(q, {})
    assert bucket == "queued"


def test_bucket_arr_item_downloading_with_progress(queue_module):
    q = {"id": 1, "title": "Movie", "size": 1000, "sizeleft": 400}
    bucket, item = queue_module._bucket_arr_item(q, {1: 600})
    assert bucket == "downloading"
    assert "speed" in item
    assert "eta" in item


def test_bucket_arr_item_stalled_when_no_progress(queue_module):
    q = {"id": 1, "title": "Movie", "size": 1000, "sizeleft": 600}
    bucket, item = queue_module._bucket_arr_item(q, {1: 600})
    assert bucket == "stalled"


def test_bucket_nzbdav_item_downloading(queue_module):
    s = {"nzo_id": "a", "filename": "x", "mb": 1000, "mbleft": 400, "status": "Downloading"}
    bucket, item = queue_module._bucket_nzbdav_item(s, {"a": 600})
    assert bucket == "downloading"


def test_bucket_nzbdav_item_importing_when_mbleft_zero(queue_module):
    s = {"nzo_id": "a", "filename": "x", "mb": 1000, "mbleft": 0, "status": "Downloading"}
    bucket, item = queue_module._bucket_nzbdav_item(s, {})
    assert bucket == "importing"


def test_bucket_plex_activity_stalled_by_default(queue_module):
    a = {"uuid": "u1", "title": "Scan", "progress": 10}
    bucket, item = queue_module._bucket_plex_activity(a, {})
    assert bucket == "stalled"


def test_bucket_plex_activity_downloading_with_progress(queue_module):
    a = {"uuid": "u1", "title": "Scan", "progress": 50}
    bucket, item = queue_module._bucket_plex_activity(a, {"u1": 20})
    assert bucket == "downloading"
    assert "eta" in item


def test_queue_status_requires_auth(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/queue-status")
    assert resp.status_code == 401


def test_queue_status_aggregates_all_sources(cp_main_app, monkeypatch):
    import services.queue.router as router_module

    monkeypatch.setattr(router_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(router_module, "arr_queue", lambda app: [])
    monkeypatch.setattr(router_module, "nzbdav_api", lambda mode, **k: {"queue": {"slots": []}})
    monkeypatch.setattr(router_module, "plex_activities", lambda: [])
    monkeypatch.setattr(router_module, "plex_progress_snapshot", lambda: {})

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/queue-status", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "radarr" in body["queues"]
    assert "sonarr" in body["queues"]
    assert "nzbdav" in body["queues"]
    assert "plex" in body["queues"]


def test_queue_status_marks_unreachable_arr_app(cp_main_app, monkeypatch):
    from fastapi import HTTPException
    import services.queue.router as router_module

    def raise_fail(app):
        raise HTTPException(status_code=502, detail="unreachable")

    monkeypatch.setattr(router_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(router_module, "arr_queue", raise_fail)
    monkeypatch.setattr(router_module, "nzbdav_api", lambda mode, **k: {"queue": {"slots": []}})
    monkeypatch.setattr(router_module, "plex_activities", lambda: [])
    monkeypatch.setattr(router_module, "plex_progress_snapshot", lambda: {})

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/queue-status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["queues"]["radarr"]["error"] == "unreachable"

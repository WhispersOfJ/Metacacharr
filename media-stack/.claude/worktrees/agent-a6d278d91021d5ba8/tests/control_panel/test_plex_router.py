"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/plex/router.py, ported from app.py. Covers auth gating for every
route, plus behavioral coverage for scan-health's hung/stalled/scanning/
healthy branches and duplicates' 1.5x-largest-file threshold - the two
routes with real incident-derived logic, mirroring test_arr_router.py's
httpx-mocking style.
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
    ("POST", "/api/plex/scan"),
    ("GET", "/api/plex/libraries"),
    ("POST", "/api/plex/empty-trash"),
    ("POST", "/api/plex/analyze"),
    ("POST", "/api/plex/optimize-db"),
    ("POST", "/api/plex/clean-bundles"),
    ("POST", "/api/plex/butler/refresh-libraries"),
    ("GET", "/api/plex/updates"),
    ("GET", "/api/plex/scan-health"),
    ("GET", "/api/plex/duplicates"),
    ("GET", "/api/plex/tmdb-missing"),
    ("GET", "/api/plex/sessions"),
    ("GET", "/api/plex/recently-added"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path)
    assert resp.status_code == 401


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/plex/scan"),
    ("GET", "/api/plex/libraries"),
    ("POST", "/api/plex/optimize-db"),
    ("POST", "/api/plex/clean-bundles"),
    ("POST", "/api/plex/butler/refresh-libraries"),
    ("GET", "/api/plex/scan-health"),
])
def test_routes_accept_service_key(cp_main_app, monkeypatch, method, path):
    """None of these mutate library state - all safe for the same
    automation callers as the arr queue-autofix set."""
    def fake_get(url, headers=None, timeout=None, **kwargs):
        if "sections" in url:
            return _json_response({"MediaContainer": {"Directory": []}})
        if "activities" in url:
            return _json_response({"MediaContainer": {"Activity": []}})
        return _json_response({"MediaContainer": {}})

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _json_response({}))
    monkeypatch.setattr(httpx, "put", lambda *a, **k: _json_response({}))
    monkeypatch.setattr("services.plex.router.nzbdav_api", lambda *a, **k: {"queue": {"slots": []}})
    monkeypatch.setattr("services.plex.router._plex_container_pid", lambda: None)
    monkeypatch.setattr("services.plex.router._fuse_waiting_total", lambda: 0)
    monkeypatch.setattr("services.plex.router._mount_test", lambda *a, **k: True)
    monkeypatch.setattr("services.plex.router._plex_scanner_processes", lambda: [])
    monkeypatch.setattr("services.plex.router._plex_log_tail", lambda **k: {
        "lines": [], "busy_db_errors": 0, "recent_busy_db_timestamps": [],
        "analysis_active": False, "analysis_batches": 0, "analysis_last_seconds": None,
    })

    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path, headers=headers)
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------
# scan-health's state-machine - the highest-risk port in Phase 4, per
# advisor review, since _bounded_exec's shutdown(wait=False) shape is
# easy to accidentally "clean up" back into a hang.
# ---------------------------------------------------------------------

def _mock_scan_health(monkeypatch, main_module, *, dstate=None, mount_ok=True,
                       scanner_running=False, nzbdav_pending=0, nzbdav_processing=0,
                       activities=None, analysis_active=False):
    monkeypatch.setattr("services.plex.router._plex_container_pid", lambda: 123)
    monkeypatch.setattr("services.plex.router._plex_dstate_threads", lambda pid: dstate or [])
    monkeypatch.setattr("services.plex.router._fuse_waiting_total", lambda: 0)
    monkeypatch.setattr("services.plex.router._mount_test", lambda *a, **k: mount_ok)
    monkeypatch.setattr("services.plex.router._plex_scanner_processes",
                         lambda: ["Plex Media Scanner running"] if scanner_running else [])
    monkeypatch.setattr("services.plex.router._nzbdav_queue_counts",
                         lambda: {"pending": nzbdav_pending, "processing": nzbdav_processing})
    monkeypatch.setattr("services.plex.router._plex_log_tail", lambda **k: {
        "lines": [], "busy_db_errors": 0, "recent_busy_db_timestamps": [],
        "analysis_active": analysis_active, "analysis_batches": 0, "analysis_last_seconds": None,
    })
    monkeypatch.setattr("services.plex.router.plex_activities", lambda: activities or [])

    docker_container = MagicMock()
    docker_container.attrs = {"State": {"Health": {"Status": "healthy"}}, "RestartCount": 0}
    docker_client_mock = MagicMock()
    docker_client_mock.containers.get.return_value = docker_container
    monkeypatch.setattr("services.plex.router.docker_client", docker_client_mock)

    return _service_key_header(main_module)


def test_scan_health_hung_when_dstate_threads_present(cp_main_app, monkeypatch):
    headers = _mock_scan_health(monkeypatch, cp_main_app, dstate=[{"tid": "1", "state": "D "}])
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/plex/scan-health", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["state"] == "hung_confirmed"


def test_scan_health_hung_when_mount_test_fails(cp_main_app, monkeypatch):
    headers = _mock_scan_health(monkeypatch, cp_main_app, mount_ok=False)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/plex/scan-health", headers=headers)
    assert resp.json()["state"] == "hung_confirmed"


def test_scan_health_stalled_suspected_when_activity_stuck_with_no_scanner(cp_main_app, monkeypatch):
    headers = _mock_scan_health(monkeypatch, cp_main_app, nzbdav_pending=3,
                                 activities=[{"uuid": "a1", "progress": 10}], scanner_running=False,
                                 analysis_active=False)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/plex/scan-health", headers=headers)
    assert resp.json()["state"] == "stalled_suspected"


def test_scan_health_scanning_when_scanner_process_is_actually_running(cp_main_app, monkeypatch):
    headers = _mock_scan_health(monkeypatch, cp_main_app, nzbdav_pending=3,
                                 activities=[{"uuid": "a1", "progress": 10}], scanner_running=True)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/plex/scan-health", headers=headers)
    assert resp.json()["state"] == "scanning"


def test_scan_health_healthy_when_nothing_pending(cp_main_app, monkeypatch):
    headers = _mock_scan_health(monkeypatch, cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/plex/scan-health", headers=headers)
    assert resp.json()["state"] == "healthy"


# ---------------------------------------------------------------------
# duplicates' 1.5x-largest-file threshold
# ---------------------------------------------------------------------

def test_duplicates_flags_items_over_threshold(cp_main_app, monkeypatch):
    def fake_get(url, headers=None, timeout=None, **kwargs):
        if url.endswith("/library/sections"):
            return _json_response({"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}})
        return _json_response({"MediaContainer": {"Metadata": [
            {"title": "Big Movie", "year": 2020, "ratingKey": "1",
             "Media": [{"Part": [{"size": 6_000_000_000}]}, {"Part": [{"size": 4_000_000_000}]}]},
            {"title": "Normal Upgrade", "year": 2021, "ratingKey": "2",
             "Media": [{"Part": [{"size": 6_000_000_000}]}, {"Part": [{"size": 2_000_000_000}]}]},
        ]}})

    monkeypatch.setattr(httpx, "get", fake_get)
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/plex/duplicates", headers=headers)
    assert resp.status_code == 200
    titles = [i["title"] for i in resp.json()["items"]]
    assert "Big Movie" in titles
    assert "Normal Upgrade" not in titles


def test_duplicates_ignores_items_under_min_gb(cp_main_app, monkeypatch):
    def fake_get(url, headers=None, timeout=None, **kwargs):
        if url.endswith("/library/sections"):
            return _json_response({"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}})
        return _json_response({"MediaContainer": {"Metadata": [
            {"title": "Tiny Duplicate", "year": 2020, "ratingKey": "3",
             "Media": [{"Part": [{"size": 100_000_000}]}, {"Part": [{"size": 100_000_000}]}]},
        ]}})

    monkeypatch.setattr(httpx, "get", fake_get)
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/plex/duplicates", headers=headers)
    assert resp.json()["items"] == []


def test_butler_task_rejects_unknown_task(cp_main_app, monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _json_response({}))
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/plex/butler/not-a-real-task", headers=headers)
    assert resp.status_code == 502

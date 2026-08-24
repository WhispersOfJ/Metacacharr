"""Phase 2 validation for .claude/plans/evolved-control-panel-backend.plan.md:
fleet status/containers/restart/stop/start and settings, ported from
app.py, now behind the Phase 1 auth split - read-only routes accept a
session or the service API key, mutating routes require a real session.
"""
import sys
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
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


def _docker_client_module(cp_main_app):
    return sys.modules["core.docker_client"]


def _fake_container(name, container_id, status="running", labels=None, health=None):
    c = MagicMock()
    c.id = container_id
    c.name = name
    c.status = status
    c.labels = labels or {}
    c.attrs = {"State": {"Health": {"Status": health}} if health else {}}
    c.image.tags = [f"{name}:latest"]
    return c


def test_status_without_session_or_key_is_401(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/status")
    assert resp.status_code == 401


def test_status_with_service_api_key(cp_main_app):
    from core.security import hash_api_key
    from models.api_key import ApiKey

    db = cp_main_app.SessionLocal()
    try:
        db.add(ApiKey(name="healthcheck-cron", key_hash=hash_api_key("raw-service-key")))
        db.commit()
    finally:
        db.close()

    dc = _docker_client_module(cp_main_app)
    me = _fake_container("control-panel", "me-id", labels={"com.docker.compose.project": "media-stack"})
    radarr = _fake_container("radarr", "radarr-id", health="healthy")
    dc.docker_client.containers.get.return_value = me
    dc.docker_client.containers.list.return_value = [me, radarr]

    client = TestClient(cp_main_app.app)
    resp = client.get("/api/status", headers={"X-Api-Key": "raw-service-key"})
    assert resp.status_code == 200
    assert resp.json()["radarr"] == {"state": "running", "health": "healthy"}


def test_status_with_session(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    me = _fake_container("control-panel", "me-id", labels={"com.docker.compose.project": "media-stack"})
    dc.docker_client.containers.get.return_value = me
    dc.docker_client.containers.list.return_value = [me]

    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.get("/api/status")
    assert resp.status_code == 200


def test_container_restart_requires_session(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/container/radarr/restart")
    assert resp.status_code == 401


def test_container_restart_plex_requires_activated_flag(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    me = _fake_container("control-panel", "me-id", labels={"com.docker.compose.project": "media-stack"})
    plex = _fake_container("plex", "plex-id")
    dc.docker_client.containers.get.return_value = me
    dc.docker_client.containers.list.return_value = [me, plex]

    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/container/plex/restart")
    assert resp.status_code == 400
    plex.restart.assert_not_called()

    resp2 = client.post("/api/container/plex/restart?activated=true")
    assert resp2.status_code == 200
    plex.restart.assert_called_once_with(timeout=30)


def test_container_restart_rejects_self(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    me = _fake_container(
        "control-panel", "me-id", labels={"com.docker.compose.project": "media-stack"}
    )
    dc.docker_client.containers.get.return_value = me
    dc.docker_client.containers.list.return_value = [me]

    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/container/control-panel/restart")
    assert resp.status_code == 400


def test_container_stop_already_stopped_is_a_no_op(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    me = _fake_container("control-panel", "me-id", labels={"com.docker.compose.project": "media-stack"})
    radarr = _fake_container("radarr", "radarr-id", status="exited")
    dc.docker_client.containers.get.return_value = me
    dc.docker_client.containers.list.return_value = [me, radarr]

    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/container/radarr/stop")
    assert resp.status_code == 200
    radarr.stop.assert_not_called()


def test_settings_get_allows_service_key_patch_requires_session(cp_main_app):
    from core.security import hash_api_key
    from models.api_key import ApiKey

    db = cp_main_app.SessionLocal()
    try:
        db.add(ApiKey(name="healthcheck-cron", key_hash=hash_api_key("raw-service-key")))
        db.commit()
    finally:
        db.close()

    client = TestClient(cp_main_app.app)

    get_resp = client.get("/api/settings", headers={"X-Api-Key": "raw-service-key"})
    assert get_resp.status_code == 200
    assert get_resp.json()["theme"] == "amber"

    patch_unauth = client.patch("/api/settings", json={"theme": "green"})
    assert patch_unauth.status_code == 401

    _login(client, cp_main_app)
    patch_resp = client.patch("/api/settings", json={"theme": "green"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["theme"] == "green"

    get_after = client.get("/api/settings", headers={"X-Api-Key": "raw-service-key"})
    assert get_after.json()["theme"] == "green"


def test_verify_same_origin_rejects_unknown_host(cp_main_app, monkeypatch):
    monkeypatch.setenv("HOST_IP", "testserver")
    client = TestClient(cp_main_app.app, base_url="http://not-this-host")
    resp = client.post("/api/auth/login", json={"username": "x", "password": "y"})
    assert resp.status_code == 403
    assert "Host header" in resp.json()["message"]


def test_project_containers_fails_without_compose_label(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    me = _fake_container("control-panel", "me-id", labels={})
    dc.docker_client.containers.get.return_value = me

    with pytest.raises(HTTPException):
        dc.project_containers()

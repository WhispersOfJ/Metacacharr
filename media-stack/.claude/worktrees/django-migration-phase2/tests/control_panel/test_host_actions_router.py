"""Validation for services/host_actions/router.py and
core/host_helper_client.py - the reboot/pacman-sync/pacman-upgrade
routes brokered through the host-privileged-action helper daemon (see
.claude/plans/host-privileged-helper.plan.md). Mirrors
test_host_diagnostics.py's login/service-key fixtures for the
session-required gate, and test_posters_router.py's confirm-gate style
from /api/disk-health/prune.
"""
import socket
import threading

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


@pytest.mark.parametrize("path", ["/api/host/reboot", "/api/host/pacman-sync", "/api/host/pacman-upgrade"])
def test_routes_require_auth(cp_main_app, path):
    client = TestClient(cp_main_app.app)
    resp = client.post(path, json={"confirm": True})
    assert resp.status_code == 401


@pytest.mark.parametrize("path", ["/api/host/reboot", "/api/host/pacman-sync", "/api/host/pacman-upgrade"])
def test_routes_require_session_not_service_key(cp_main_app, path):
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.post(path, headers=headers, json={"confirm": True})
    assert resp.status_code == 401


@pytest.mark.parametrize("path", ["/api/host/reboot", "/api/host/pacman-sync", "/api/host/pacman-upgrade"])
def test_routes_require_confirm_true(cp_main_app, path):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post(path, json={"confirm": False})
    assert resp.status_code == 400


def test_reboot_calls_helper_with_reboot_action(cp_main_app, monkeypatch):
    captured = {}

    def fake_call(action, timeout=600):
        captured["action"] = action
        return {"ok": True, "message": "rebooting", "returncode": 0}

    monkeypatch.setattr("services.host_actions.router.call_host_helper", fake_call)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/host/reboot", json={"confirm": True})
    assert resp.status_code == 200
    assert captured["action"] == "reboot"


def test_pacman_sync_calls_helper_with_pacman_sync_action(cp_main_app, monkeypatch):
    captured = {}

    def fake_call(action, timeout=600):
        captured["action"] = action
        return {"ok": True, "message": "synced", "returncode": 0}

    monkeypatch.setattr("services.host_actions.router.call_host_helper", fake_call)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/host/pacman-sync", json={"confirm": True})
    assert resp.status_code == 200
    assert captured["action"] == "pacman_sync"


def test_pacman_upgrade_calls_helper_with_pacman_upgrade_action(cp_main_app, monkeypatch):
    captured = {}

    def fake_call(action, timeout=600):
        captured["action"] = action
        return {"ok": True, "message": "upgraded", "returncode": 0}

    monkeypatch.setattr("services.host_actions.router.call_host_helper", fake_call)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/host/pacman-upgrade", json={"confirm": True})
    assert resp.status_code == 200
    assert captured["action"] == "pacman_upgrade"


def test_action_502s_when_helper_reports_failure(cp_main_app, monkeypatch):
    monkeypatch.setattr("services.host_actions.router.call_host_helper",
                         lambda action, timeout=600: {"ok": False, "message": "pacman exited 1", "returncode": 1})
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/host/pacman-upgrade", json={"confirm": True})
    assert resp.status_code == 502
    assert "pacman exited 1" in resp.json()["detail"]["message"]


# ---------------------------------------------------------------------
# core.host_helper_client - the Unix-socket client itself, exercised
# against a real socket server (a fake stand-in for the host daemon) so
# the request/response framing is actually proven, not just mocked away.
# ---------------------------------------------------------------------

def _fake_helper_server(socket_path, response_bytes):
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    server.listen(1)

    def run():
        conn, _ = server.accept()
        try:
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            conn.sendall(response_bytes)
        finally:
            conn.close()
            server.close()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def test_call_host_helper_round_trips_over_real_socket(cp_main_app, monkeypatch, tmp_path):
    from core.host_helper_client import call_host_helper

    socket_path = str(tmp_path / "helper.sock")
    monkeypatch.setattr("core.host_helper_client.HOST_HELPER_SOCKET", socket_path)
    t = _fake_helper_server(socket_path, b'{"ok": true, "message": "synced", "returncode": 0}\n')
    result = call_host_helper("pacman_sync")
    t.join(timeout=2)
    assert result == {"ok": True, "message": "synced", "returncode": 0}


def test_call_host_helper_503s_when_socket_missing(cp_main_app, monkeypatch, tmp_path):
    from core.host_helper_client import call_host_helper

    monkeypatch.setattr("core.host_helper_client.HOST_HELPER_SOCKET", str(tmp_path / "does-not-exist.sock"))
    with pytest.raises(Exception) as exc_info:
        call_host_helper("reboot")
    assert "503" in str(exc_info.value) or getattr(exc_info.value, "status_code", None) == 503

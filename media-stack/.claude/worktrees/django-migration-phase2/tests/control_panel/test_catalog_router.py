"""Tests for services/catalog/router.py - the curated software catalog
(Phase 02 of the control-panel v3 design treatment). Install/remove go
through the Docker SDK directly (docker_client mocked the same way
test_host.py mocks it), never a real docker.sock call.
"""
import sys
from unittest.mock import MagicMock

import docker
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
        db.add(ApiKey(name="test-key", key_hash=hash_api_key("raw-service-key")))
        db.commit()
    finally:
        db.close()
    return {"X-Api-Key": "raw-service-key"}


def _docker_client_module(cp_main_app):
    return sys.modules["core.docker_client"]


def _fake_container(name, container_id="abc123", status="running", ports=None):
    c = MagicMock()
    c.id = container_id
    c.name = name
    c.status = status
    c.attrs = {
        "State": {"Health": {"Status": "healthy"}, "StartedAt": "2026-08-07T00:00:00Z"},
        "HostConfig": {"PortBindings": {f"{p}/tcp": [{"HostPort": str(p)}] for p in (ports or [])}},
    }
    return c


def test_list_requires_auth(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/catalog")
    assert resp.status_code == 401


def test_list_accepts_service_key_and_has_expanded_entry_count(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("no such container")
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/catalog", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) >= 41
    assert all(i["status"] == "not_installed" for i in body["items"])


def test_list_marks_installed_entry(cp_main_app):
    dc = _docker_client_module(cp_main_app)

    def get_side_effect(name):
        if name == "catalog-dozzle":
            return _fake_container("catalog-dozzle")
        raise docker.errors.NotFound("no such container")

    dc.docker_client.containers.get.side_effect = get_side_effect
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/catalog", headers=headers)
    items = {i["id"]: i for i in resp.json()["items"]}
    assert items["dozzle"]["status"] == "running"
    assert items["uptime-kuma"]["status"] == "not_installed"


def test_install_requires_session_not_just_service_key(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("no such container")
    dc.docker_client.containers.list.return_value = []
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/catalog/dozzle/install", headers=headers, json={"confirm": True})
    assert resp.status_code == 401


def test_install_unknown_id_404s(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/catalog/not-a-real-app/install", json={"confirm": True})
    assert resp.status_code == 404


def test_install_without_confirm_400s(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/catalog/dozzle/install", json={"confirm": False})
    assert resp.status_code == 400


def test_install_already_installed_409s(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    dc.docker_client.containers.get.return_value = _fake_container("catalog-dozzle")
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/catalog/dozzle/install", json={"confirm": True})
    assert resp.status_code == 409


def test_install_port_conflict_409s(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("no such container")
    # uptime-kuma wants host port 3050 - simulate another container already bound to it.
    dc.docker_client.containers.list.return_value = [_fake_container("something-else", ports=[3050])]
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/catalog/uptime-kuma/install", json={"confirm": True})
    assert resp.status_code == 409
    assert "3050" in resp.text


def test_install_success_pulls_and_runs_with_labels(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("no such container")
    dc.docker_client.containers.list.return_value = []
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/catalog/dozzle/install", json={"confirm": True})
    assert resp.status_code == 200, resp.text
    dc.docker_client.images.pull.assert_called_once_with("amir20/dozzle", tag="latest")
    run_kwargs = dc.docker_client.containers.run.call_args.kwargs
    assert run_kwargs["name"] == "catalog-dozzle"
    assert run_kwargs["network"] == "stacknet"
    assert run_kwargs["labels"] == {"media-stack.catalog": "dozzle"}
    assert run_kwargs["restart_policy"] == {"Name": "unless-stopped"}
    # Dozzle needs the docker socket, read-only, to read every container's logs.
    assert run_kwargs["volumes"]["/var/run/docker.sock"]["mode"] == "ro"


def test_install_portainer_gets_readwrite_docker_sock(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("no such container")
    dc.docker_client.containers.list.return_value = []
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/catalog/portainer/install", json={"confirm": True})
    assert resp.status_code == 200, resp.text
    run_kwargs = dc.docker_client.containers.run.call_args.kwargs
    assert run_kwargs["volumes"]["/var/run/docker.sock"]["mode"] == "rw"


def test_remove_without_confirm_400s(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/catalog/dozzle/remove", json={"confirm": False})
    assert resp.status_code == 400


def test_remove_not_installed_404s(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("no such container")
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/catalog/dozzle/remove", json={"confirm": True})
    assert resp.status_code == 404


def test_remove_stops_and_removes_without_touching_volumes_by_default(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    fake = _fake_container("catalog-uptime-kuma")
    dc.docker_client.containers.get.return_value = fake
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/catalog/uptime-kuma/remove", json={"confirm": True})
    assert resp.status_code == 200, resp.text
    fake.stop.assert_called_once()
    fake.remove.assert_called_once_with(v=False)
    dc.docker_client.volumes.get.assert_not_called()
    assert "kept" in resp.json()["message"]


def test_remove_with_remove_volumes_deletes_named_volume(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    fake = _fake_container("catalog-uptime-kuma")
    dc.docker_client.containers.get.return_value = fake
    fake_volume = MagicMock()
    dc.docker_client.volumes.get.return_value = fake_volume
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/catalog/uptime-kuma/remove", json={"confirm": True, "remove_volumes": True})
    assert resp.status_code == 200, resp.text
    fake_volume.remove.assert_called_once()


def test_list_includes_environment_and_volumes(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("no such container")
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/catalog", headers=headers)
    items = {i["id"]: i for i in resp.json()["items"]}
    speedtest = items["speedtest-tracker"]
    assert speedtest["environment"] == {"OOKLA_EULA_GDPR": "true"}
    assert speedtest["volumes"] == {"catalog_speedtest_data": {"bind": "/config", "mode": "rw"}}

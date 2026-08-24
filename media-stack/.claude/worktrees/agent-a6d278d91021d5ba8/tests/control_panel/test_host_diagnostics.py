"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
the host-diagnostic routes appended to services/host/router.py (resource-
check, log-levels, oom-check, disk-usage, mount-health, perms-check,
image-check, version, docs/readme, notify/test, top), ported from app.py.
Mirrors test_host.py's docker-mocking style for Phase 2's routes.
"""
import sys
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient


def _docker_client_module(cp_main_app):
    return sys.modules["core.docker_client"]


def _fake_container(name, container_id, status="running", labels=None, oom_killed=False):
    c = MagicMock()
    c.id = container_id
    c.name = name
    c.status = status
    c.labels = labels or {}
    c.attrs = {"State": {"OOMKilled": oom_killed}, "HostConfig": {"Memory": 0, "NanoCpus": 0}}
    c.image.tags = [f"{name}:latest"]
    c.image.attrs = {"RepoDigests": []}
    return c


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


def _setup_project(cp_main_app, others):
    dc = _docker_client_module(cp_main_app)
    me = _fake_container("control-panel", "me-id", labels={"com.docker.compose.project": "media-stack"})
    dc.docker_client.containers.get.return_value = me
    dc.docker_client.containers.list.return_value = [me, *others]
    return me


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/resource-check"),
    ("GET", "/api/log-levels"),
    ("POST", "/api/log-levels/reset"),
    ("GET", "/api/oom-check"),
    ("GET", "/api/disk-usage"),
    ("GET", "/api/mount-health"),
    ("GET", "/api/perms-check"),
    ("GET", "/api/image-check"),
    ("GET", "/api/version"),
    ("GET", "/api/docs/readme"),
    ("POST", "/api/notify/test"),
    ("GET", "/api/top"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path)
    assert resp.status_code == 401


def test_resource_check_flags_missing_limits(cp_main_app):
    radarr = _fake_container("radarr", "radarr-id")
    _setup_project(cp_main_app, [radarr])
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/resource-check", headers=headers)
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()["containers"]]
    assert "radarr" in names


def test_oom_check_flags_oom_killed_containers(cp_main_app):
    radarr = _fake_container("radarr", "radarr-id", oom_killed=True)
    _setup_project(cp_main_app, [radarr])
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/oom-check", headers=headers)
    assert resp.json()["containers"] == ["radarr"]


def test_oom_check_empty_when_none_killed(cp_main_app):
    radarr = _fake_container("radarr", "radarr-id", oom_killed=False)
    _setup_project(cp_main_app, [radarr])
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/oom-check", headers=headers)
    assert resp.json()["containers"] == []


def test_disk_usage_missing_mount_fails(cp_main_app, monkeypatch):
    monkeypatch.setattr("services.host.router.HOST_CONFIG_DIR", "/definitely/not/mounted")
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/disk-usage", headers=headers)
    assert resp.status_code == 502


def test_mount_health_reports_missing_mount(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.host.router.HOST_MNT_DIR", str(tmp_path))
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/mount-health", headers=headers)
    body = resp.json()
    assert body["mounts"][0]["mount"] == "remote/nzbdav"
    assert body["mounts"][0]["status"] == "missing"


def test_log_levels_reports_debug_apps(cp_main_app, monkeypatch):
    def fake_get(url, headers=None, timeout=None, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"logLevel": "debug", "id": 1}
        return resp

    monkeypatch.setattr(httpx, "get", fake_get)
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/log-levels", headers=headers)
    body = resp.json()
    assert body["levels"]["radarr"] == "debug"
    assert "radarr" in body["message"]


def test_version_reads_readme_declared_version(cp_main_app, monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("Some text\nCurrent version: **v3.2.1**\nMore text\n")
    monkeypatch.setattr("services.host.router.HOST_README", str(readme))
    radarr = _fake_container("radarr", "radarr-id")
    _setup_project(cp_main_app, [radarr])
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/version", headers=headers)
    body = resp.json()
    assert body["version"] == "v3.2.1"
    assert body["total"] == 2


def test_notify_test_fails_when_all_sinks_fail(cp_main_app, monkeypatch):
    """No DISCORD_WEBHOOK_URL and no reachable ntfy (unresolvable host in
    the test environment) - both sinks fail, so the whole route 502s."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/notify/test", headers=headers)
    assert resp.status_code == 502


def test_notify_test_fails_when_webhook_unset(cp_main_app, monkeypatch):
    """Discord is the sole notification sink (ntfy retired 2026-08-18) - no
    webhook configured means the route fails outright, not a partial result."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/notify/test", headers=headers)
    assert resp.status_code != 200


def test_notify_test_sends_via_discord(cp_main_app, monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    monkeypatch.setattr("services.host.router.httpx.post", lambda *a, **k: mock_resp)
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/notify/test", headers=headers)
    assert resp.status_code == 200


def test_top_sorts_by_requested_metric(cp_main_app, monkeypatch):
    radarr = _fake_container("radarr", "radarr-id")
    sonarr = _fake_container("sonarr", "sonarr-id")
    _setup_project(cp_main_app, [radarr, sonarr])
    stats_by_name = {"radarr": {"cpu_percent": 80.0, "mem_percent": 10.0, "mem_used_mb": 100},
                      "sonarr": {"cpu_percent": 20.0, "mem_percent": 90.0, "mem_used_mb": 900}}
    monkeypatch.setattr("services.host.router.container_stats", lambda c: stats_by_name[c.name])
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/top?by=cpu", headers=headers)
    items = resp.json()["items"]
    assert items[0]["name"] == "radarr"

    resp = client.get("/api/top?by=mem", headers=headers)
    items = resp.json()["items"]
    assert items[0]["name"] == "sonarr"


def test_top_rejects_bad_metric(cp_main_app):
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/top?by=bogus", headers=headers)
    assert resp.status_code == 400


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


def test_disk_health_reports_mount_and_reclaimable(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.host.router.HOST_MNT_DIR", str(tmp_path))
    dc = _docker_client_module(cp_main_app)
    dc.docker_client.df.return_value = {
        "Images": [{"Size": 500_000_000, "SharedSize": 0, "Containers": 0}],
        "Containers": [{"SizeRw": 10_000_000, "State": "exited"}],
        "Volumes": [{"UsageData": {"Size": 200_000_000, "RefCount": 0}}],
        "BuildCache": [{"Size": 50_000_000, "InUse": False}],
    }
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/disk-health", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mount"]["path"] == str(tmp_path)
    assert "MB" in body["reclaimable"]["images"] or "KB" in body["reclaimable"]["images"]


def test_disk_health_prune_requires_confirm(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/disk-health/prune", json={"confirm": False})
    assert resp.status_code == 400


def test_disk_health_prune_requires_session_not_service_key(cp_main_app):
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/disk-health/prune", headers=headers, json={"confirm": True})
    assert resp.status_code == 401


def test_disk_health_prune_reports_reclaimed_space(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    dc.docker_client.images.prune.return_value = {"ImagesDeleted": [{"Deleted": "x"}], "SpaceReclaimed": 1_000_000}
    dc.docker_client.volumes.prune.return_value = {"VolumesDeleted": ["v1"], "SpaceReclaimed": 500_000}
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/disk-health/prune", json={"confirm": True})
    assert resp.status_code == 200, resp.text
    assert "Reclaimed" in resp.json()["message"]


def test_host_resources_reports_cpu_and_mem(cp_main_app, monkeypatch, tmp_path):
    (tmp_path / "meminfo").write_text(
        "MemTotal:       16000000 kB\nMemFree:         2000000 kB\nMemAvailable:    4000000 kB\n"
    )
    calls = {"n": 0}
    stat_lines = ["cpu  100 0 100 800 0 0 0 0 0 0\n", "cpu  110 0 110 850 0 0 0 0 0 0\n"]

    def fake_read_cpu():
        line = stat_lines[min(calls["n"], 1)]
        calls["n"] += 1
        return [int(x) for x in line.split()[1:]]

    monkeypatch.setattr("services.host.router.HOST_PROC_DIR", str(tmp_path))
    monkeypatch.setattr("services.host.router._read_host_proc_cpu_line", fake_read_cpu)
    monkeypatch.setattr("services.host.router.time.sleep", lambda s: None)
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/host-resources", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert 0 <= body["cpu_percent"] <= 100
    assert body["mem_percent"] > 0


def test_host_resources_503s_without_proc_mount(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.host.router.HOST_PROC_DIR", str(tmp_path / "nope"))
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/host-resources", headers=headers)
    assert resp.status_code == 503

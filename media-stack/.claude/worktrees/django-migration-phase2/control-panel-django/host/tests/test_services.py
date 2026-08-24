"""host/services.py unit tests.

Grouped by dependency, per plan Task 16 Step 2:
- container-management functions mock core.docker_client.docker_client
  (a real docker.from_env() is not available in the test env)
- get_settings/patch_settings mock core.settings (DB-backed, but the
  FastAPI-era store's defaults are what we assert against - the Setting
  table is empty in tests unless we seed it)
- host-resource functions mock filesystem reads against a tmp_path
  standing in for HOST_PROC_DIR/HOST_CONFIG_DIR
- log_levels/reset_log_levels mock the *arr httpx calls
- notify_test mocks the Discord webhook httpx.post
- docs_readme reads a tmp_path-provided fixture README
"""
import os
from pathlib import Path

import docker
import httpx
import pytest

from core import host_paths
from core.api_base import ServiceError
from host import services


class _FakeContainer:
    """Minimal docker container stand-in with just what the ported host
    services touch: name, id, status, labels, image tags, attrs, and the
    restart/stop/start methods."""

    def __init__(self, name, status="running", oom=False, health="healthy"):
        self.name = name
        self.id = f"id-{name}"
        self.status = status
        self.labels = {"com.docker.compose.project": "stack", "com.docker.compose.service": name}
        self.attrs = {
            "State": {"Health": {"Status": health}, "OOMKilled": oom},
            "HostConfig": {"Memory": 512 * 1024 * 1024, "NanoCpus": 1_000_000_000},
        }
        self.image = _FakeImage(name)
        self.restart_calls = 0
        self.stop_calls = 0
        self.start_calls = 0

    def restart(self, timeout=30):
        self.restart_calls += 1
        self.status = "running"

    def stop(self, timeout=30):
        self.stop_calls += 1
        self.status = "exited"

    def start(self):
        self.start_calls += 1
        self.status = "running"

    def reload(self):
        pass


class _FakeImage:
    def __init__(self, name):
        self.tags = [f"test/{name}:latest"]
        self.short_id = "sha256:abc"
        self.attrs = {"RepoDigests": ["test/name@sha256:digest"]}


def _fake_project(monkeypatch, containers, self_name="control-panel"):
    me = _FakeContainer(self_name)
    # project_containers() is imported into host.services AND called by
    # core.docker_client.find_project_container via that module's own
    # namespace - patch both so every caller sees the same fake project.
    monkeypatch.setattr("host.services.project_containers", lambda: (me, containers))
    monkeypatch.setattr("core.docker_client.project_containers", lambda: (me, containers))
    return me


@pytest.fixture(autouse=True)
def _fake_docker_client(monkeypatch):
    """docker_client is a module-level docker.from_env() whose .images/
    .volumes/.df accessors return fresh objects each access, so attribute
    patching on the instance doesn't stick. Swap the whole docker_client
    name in host.services for a fake with the handful of methods the
    ported services touch."""

    class _FakeImages:
        def prune(self):
            return {"SpaceReclaimed": 100, "ImagesDeleted": [{"Deleted": "x"}]}

        def get_registry_data(self, tag_ref):
            raise docker.errors.APIError("no registry in tests")

    class _FakeVolumes:
        def prune(self):
            return {"SpaceReclaimed": 200, "VolumesDeleted": [{"Deleted": "v"}]}

    class _FakeDocker:
        images = _FakeImages()
        volumes = _FakeVolumes()

        def df(self):
            return {"Images": [], "Containers": [], "Volumes": [], "BuildCache": []}

    monkeypatch.setattr(services, "docker_client", _FakeDocker())


# --- get_status / list_containers / container management ---


def test_get_status_reports_state_and_health(monkeypatch):
    _fake_project(monkeypatch, [_FakeContainer("radarr", health="unhealthy"), _FakeContainer("plex")])
    result = services.get_status()
    assert result == {
        "radarr": {"state": "running", "health": "unhealthy"},
        "plex": {"state": "running", "health": "healthy"},
    }


def test_list_containers_marks_self_and_includes_stats(monkeypatch):
    me = _fake_project(monkeypatch, [_FakeContainer("radarr")])
    items = services.list_containers()
    assert len(items) == 1
    row = items[0]
    assert row["name"] == "radarr"
    assert row["label"] == "Radarr"
    assert row["is_self"] is False
    assert set(row) >= {"cpu_percent", "mem_percent", "mem_used_mb", "mem_limit_mb"}
    # me is the control-panel container; only radarr is in the list
    assert me.name not in [i["name"] for i in items]


def test_restart_container_requires_activated_for_plex(monkeypatch):
    _fake_project(monkeypatch, [_FakeContainer("plex")])
    with pytest.raises(ServiceError) as exc_info:
        services.restart_container("plex")
    assert exc_info.value.status_code == 400
    assert "activated=true" in str(exc_info.value.detail)


def test_restart_container_with_activated_restarts_plex(monkeypatch):
    containers = [_FakeContainer("plex")]
    _fake_project(monkeypatch, containers)
    message = services.restart_container("plex", activated=True)
    assert containers[0].restart_calls == 1
    assert "restarted" in message


def test_restart_container_unknown_raises_404(monkeypatch):
    _fake_project(monkeypatch, [_FakeContainer("radarr")])
    with pytest.raises(ServiceError) as exc_info:
        services.restart_container("not-a-container")
    assert exc_info.value.status_code == 404


def test_stop_container_skips_when_not_running(monkeypatch):
    containers = [_FakeContainer("radarr", status="exited")]
    _fake_project(monkeypatch, containers)
    message = services.stop_container("radarr")
    assert containers[0].stop_calls == 0
    assert "already exited" in message


def test_stop_container_stops_running(monkeypatch):
    containers = [_FakeContainer("radarr")]
    _fake_project(monkeypatch, containers)
    message = services.stop_container("radarr")
    assert containers[0].stop_calls == 1
    assert "stopped" in message


def test_start_container_skips_when_running(monkeypatch):
    containers = [_FakeContainer("radarr")]
    _fake_project(monkeypatch, containers)
    message = services.start_container("radarr")
    assert containers[0].start_calls == 0
    assert "already running" in message


def test_start_container_starts_stopped(monkeypatch):
    containers = [_FakeContainer("radarr", status="exited")]
    _fake_project(monkeypatch, containers)
    message = services.start_container("radarr")
    assert containers[0].start_calls == 1
    assert "started" in message


def test_stream_container_logs_yields_sse_lines(monkeypatch):
    class _LogsContainer(_FakeContainer):
        def logs(self, stream=True, follow=True, tail=100, timestamps=True):
            yield b"line one\n"
            yield b"line two\n"

    _fake_project(monkeypatch, [_LogsContainer("radarr")])
    gen = services.stream_container_logs("radarr", tail=100)
    lines = list(gen)
    assert lines == ["data: line one\n\n", "data: line two\n\n"]


def test_restart_all_returns_names_and_runs_worker(monkeypatch):
    containers = [_FakeContainer("radarr"), _FakeContainer("sonarr")]
    me = _FakeContainer("control-panel")
    monkeypatch.setattr("host.services.project_containers", lambda: (me, containers + [me]))

    # wait_for_healthy sleeps in a loop - stub it so the worker thread
    # finishes quickly and deterministically.
    monkeypatch.setattr("host.services.wait_for_healthy", lambda c, timeout=60: None)

    message = services.restart_all()
    assert "radarr" in message and "sonarr" in message
    assert "control-panel" not in message


# --- settings ---


def test_get_settings_returns_defaults(monkeypatch):
    monkeypatch.setattr("host.services.settings_core.get_settings", lambda: {
        "theme": "amber", "failed_pending_storm_threshold": 15,
        "loop_review_profile_threshold": 8, "recent_values": {},
    })
    result = services.get_settings()
    assert result["theme"] == "amber"
    assert result["failed_pending_storm_threshold"] == 15


def test_patch_settings_passes_patch_through(monkeypatch):
    captured = {}
    monkeypatch.setattr("host.services.settings_core.update_settings", lambda patch: captured.update(patch) or {
        "theme": "green", "failed_pending_storm_threshold": 15,
        "loop_review_profile_threshold": 8, "recent_values": {},
    })
    result = services.patch_settings({"theme": "green"})
    assert captured == {"theme": "green"}
    assert result["theme"] == "green"


# --- resource / disk / host-proc diagnostics ---


def test_resource_check_reports_missing_limits(monkeypatch):
    ok_container = _FakeContainer("radarr")
    missing = _FakeContainer("sonarr")
    missing.attrs = {"HostConfig": {"Memory": 0, "NanoCpus": 0}}
    _fake_project(monkeypatch, [ok_container, missing])
    result = services.resource_check()
    assert result["containers"] == [{"name": "sonarr", "mem_limit_set": False, "cpus_set": False,
                                     "cpu_percent": None, "mem_used_mb": None,
                                     "mem_limit_mb": None, "mem_percent": None}]
    assert "1 container(s) missing" in result["message"]


def test_resource_check_all_set(monkeypatch):
    _fake_project(monkeypatch, [_FakeContainer("radarr")])
    result = services.resource_check()
    assert result["containers"] == []
    assert "Every container has both" in result["message"]


def test_disk_health_reports_mount_and_reclaimable(monkeypatch, tmp_path):
    monkeypatch.setattr(host_paths, "HOST_MNT_DIR", str(tmp_path))
    monkeypatch.setattr(services, "HOST_MNT_DIR", str(tmp_path))
    result = services.disk_health()
    assert result["mount"]["path"] == str(tmp_path)
    assert result["mount"]["percent"] is not None
    # fake docker df returns all-empty -> zero reclaimable
    assert result["reclaimable"]["images"] == "0B"
    assert result["total_reclaimable"] == "0B"


def test_prune_disk_reports_reclaimed(monkeypatch):
    result = services.prune_disk()
    assert "Reclaimed" in result
    assert "1 image(s)" in result
    assert "1 volume(s)" in result
    assert "300B" in result


def test_host_resources_reads_host_proc(monkeypatch, tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    # 16777216 kB = exactly 16 GiB total, 4194304 kB = exactly 4 GiB
    # available -> mem_used = 12 GiB, percent = 75.0.
    (proc / "meminfo").write_text(
        "MemTotal:       16777216 kB\nMemAvailable:    4194304 kB\n"
    )
    monkeypatch.setattr(host_paths, "HOST_PROC_DIR", str(proc))
    monkeypatch.setattr(services, "HOST_PROC_DIR", str(proc))
    monkeypatch.setattr(services.time, "sleep", lambda s: None)
    # CPU percent needs two /proc/stat samples; a static file yields zero
    # delta, so feed the two reads directly (both go through the same
    # module-level helper the real code uses).
    samples = iter([[1000, 0, 500, 9000], [1100, 0, 600, 9000]])
    monkeypatch.setattr("host.services._read_host_proc_cpu_line", lambda: next(samples))

    result = services.host_resources()
    # idle delta 0 of total delta 200 -> 100% busy
    assert result["cpu_percent"] == 100.0
    assert result["mem_percent"] == 75.0
    assert result["mem_used"] == "12.0GB"
    assert result["mem_total"] == "16.0GB"


def test_host_resources_missing_proc_raises_503(monkeypatch, tmp_path):
    monkeypatch.setattr(host_paths, "HOST_PROC_DIR", str(tmp_path / "nope"))
    monkeypatch.setattr(services, "HOST_PROC_DIR", str(tmp_path / "nope"))
    with pytest.raises(ServiceError) as exc_info:
        services.host_resources()
    assert exc_info.value.status_code == 503


def test_oom_check_lists_killed(monkeypatch):
    killed = _FakeContainer("seerr", oom=True)
    fine = _FakeContainer("radarr")
    _fake_project(monkeypatch, [killed, fine])
    result = services.oom_check()
    assert result["containers"] == ["seerr"]
    assert "OOM-killed" in result["message"]


def test_disk_usage_sums_config_dirs(monkeypatch, tmp_path):
    config = tmp_path / "config"
    (config / "radarr").mkdir(parents=True)
    (config / "radarr" / "a.log").write_bytes(b"x" * (1024 * 1024))  # 1 MiB, definitely nonzero st_blocks
    (config / "sonarr").mkdir()
    monkeypatch.setattr(host_paths, "HOST_CONFIG_DIR", str(config))
    monkeypatch.setattr(services, "HOST_CONFIG_DIR", str(config))
    result = services.disk_usage()
    by_app = {s["app"]: s["mb"] for s in result["sizes"]}
    assert "radarr" in by_app
    assert by_app["radarr"] > 0
    assert by_app["sonarr"] == 0.0
    assert result["sizes"][0]["app"] == "radarr"  # sorted desc by mb


def test_mount_health_reports_healthy_and_missing(monkeypatch, tmp_path):
    mnt = tmp_path / "mnt"
    (mnt / "remote" / "nzbdav").mkdir(parents=True)
    monkeypatch.setattr(host_paths, "HOST_MNT_DIR", str(mnt))
    monkeypatch.setattr(services, "HOST_MNT_DIR", str(mnt))
    result = services.mount_health()
    assert result["mounts"] == [{"mount": "remote/nzbdav", "path": str(mnt / "remote" / "nzbdav"),
                                 "status": "healthy"}]
    assert "All known mounts" in result["message"]


def test_perms_check_finds_unreadable_files(monkeypatch, tmp_path):
    config = tmp_path / "config"
    (config / "radarr").mkdir(parents=True)
    readable = config / "radarr" / "ok.conf"
    readable.write_text("x")
    readable.chmod(0o644)
    locked = config / "radarr" / "locked.conf"
    locked.write_text("y")
    locked.chmod(0o600)
    monkeypatch.setattr(host_paths, "HOST_CONFIG_DIR", str(config))
    monkeypatch.setattr(services, "HOST_CONFIG_DIR", str(config))
    result = services.perms_check()
    assert len(result["files"]) == 1
    assert result["files"][0].startswith("config/radarr/locked.conf")


# --- log levels / image check / version / docs / notify / top ---


def test_log_levels_reports_per_app(httpx_mock):
    httpx_mock.add_response(url="http://radarr:7878/api/v3/config/host", json={"logLevel": "debug"})
    httpx_mock.add_response(url="http://sonarr:8989/api/v3/config/host", json={"logLevel": "info"})
    httpx_mock.add_response(url="http://prowlarr:9696/api/v1/config/host", json={"logLevel": "info"})
    result = services.log_levels()
    assert result["levels"] == {"radarr": "debug", "sonarr": "info", "prowlarr": "info"}
    assert "1 app(s) at debug: radarr" in result["message"]


def test_log_levels_tolerates_unreachable_app(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("refused"), url="http://radarr:7878/api/v3/config/host")
    httpx_mock.add_response(url="http://sonarr:8989/api/v3/config/host", json={"logLevel": "info"})
    httpx_mock.add_response(url="http://prowlarr:9696/api/v1/config/host", json={"logLevel": "info"})
    result = services.log_levels()
    assert result["levels"]["radarr"].startswith("error:")


def test_reset_log_levels_resets_debug_apps(httpx_mock):
    httpx_mock.add_response(url="http://radarr:7878/api/v3/config/host", json={"id": 1, "logLevel": "debug"})
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/config/host/1", method="PUT",
        json={"id": 1, "logLevel": "info"},
    )
    httpx_mock.add_response(url="http://sonarr:8989/api/v3/config/host", json={"id": 2, "logLevel": "info"})
    httpx_mock.add_response(url="http://prowlarr:9696/api/v1/config/host", json={"id": 3, "logLevel": "info"})
    message = services.reset_log_levels()
    assert "Reset 1 app(s) to info: radarr" in message


def test_reset_log_levels_nothing_to_reset(httpx_mock):
    httpx_mock.add_response(url="http://radarr:7878/api/v3/config/host", json={"id": 1, "logLevel": "info"})
    httpx_mock.add_response(url="http://sonarr:8989/api/v3/config/host", json={"id": 2, "logLevel": "info"})
    httpx_mock.add_response(url="http://prowlarr:9696/api/v1/config/host", json={"id": 3, "logLevel": "info"})
    assert services.reset_log_levels() == "Nothing to reset - no app was at debug."


def test_image_check_tolerates_registry_error(monkeypatch):
    containers = [_FakeContainer("radarr")]
    _fake_project(monkeypatch, containers)
    result = services.image_check()
    assert len(result["images"]) == 1
    assert result["images"][0]["update_available"] is None
    assert "error" in result["images"][0]


def test_get_version_reads_readme(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# Stack\nCurrent version: **v11.17.0**\n")
    monkeypatch.setattr(host_paths, "HOST_README", str(readme))
    monkeypatch.setattr(services, "HOST_README", str(readme))
    _fake_project(monkeypatch, [_FakeContainer("radarr", status="running"), _FakeContainer("plex", status="exited")])
    result = services.get_version()
    assert result["version"] == "v11.17.0"
    assert result["running"] == 1
    assert result["total"] == 2


def test_docs_readme_returns_text(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# hello stack")
    monkeypatch.setattr(host_paths, "HOST_README", str(readme))
    monkeypatch.setattr(services, "HOST_README", str(readme))
    assert services.docs_readme() == "# hello stack"


def test_docs_readme_missing_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(host_paths, "HOST_README", str(tmp_path / "nope.md"))
    monkeypatch.setattr(services, "HOST_README", str(tmp_path / "nope.md"))
    with pytest.raises(ServiceError):
        services.docs_readme()


def test_notify_test_posts_discord_webhook(httpx_mock, monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test")
    httpx_mock.add_response(url="https://discord.com/api/webhooks/test", method="POST", json={})
    assert services.notify_test() == "Test notification sent."


def test_notify_test_missing_webhook_raises(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    with pytest.raises(ServiceError):
        services.notify_test()


def test_stack_top_sorts_by_cpu(monkeypatch):
    busy = _FakeContainer("busy")
    busy.stats_override = {"cpu_percent": 90.0, "mem_percent": 10.0, "mem_used_mb": 100.0}
    idle = _FakeContainer("idle")
    idle.stats_override = {"cpu_percent": 1.0, "mem_percent": 5.0, "mem_used_mb": 50.0}
    _fake_project(monkeypatch, [busy, idle])
    monkeypatch.setattr(
        "host.services.container_stats",
        lambda c: getattr(c, "stats_override", {"cpu_percent": None, "mem_percent": None, "mem_used_mb": None}),
    )
    result = services.stack_top(by="cpu", limit=10)
    assert [i["name"] for i in result["items"]] == ["busy", "idle"]
    assert "Top 2 containers by cpu" in result["message"]


def test_stack_top_rejects_bad_by(monkeypatch):
    _fake_project(monkeypatch, [])
    with pytest.raises(ServiceError) as exc_info:
        services.stack_top(by="gpu")
    assert exc_info.value.status_code == 400

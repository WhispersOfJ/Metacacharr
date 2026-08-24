"""Gate tests for core/docker_client.py - untested since the app.py-era
test_container_stats.py was deleted in the Plan 3 consolidation (c7fc6b8)."""
from unittest.mock import MagicMock

import docker
import pytest


@pytest.fixture
def docker_client_module(cp_main_app):
    import core.docker_client as module
    return module


def test_container_label_known_container(docker_client_module):
    assert docker_client_module.container_label("plex") == "Plex"


def test_container_label_unknown_falls_back_to_name(docker_client_module):
    assert docker_client_module.container_label("some-unlisted-thing") == "some-unlisted-thing"


def test_container_stats_not_running_returns_all_none(docker_client_module):
    c = MagicMock(status="stopped")
    result = docker_client_module.container_stats(c)
    assert result == {"cpu_percent": None, "mem_used_mb": None, "mem_limit_mb": None, "mem_percent": None}


def test_container_stats_computes_percentages(docker_client_module):
    c = MagicMock(status="running")
    c.stats.return_value = {
        "cpu_stats": {"cpu_usage": {"total_usage": 1500, "percpu_usage": [1, 1]}, "system_cpu_usage": 10000, "online_cpus": 2},
        "precpu_stats": {"cpu_usage": {"total_usage": 1000}, "system_cpu_usage": 9000},
        "memory_stats": {"usage": 100 * 1024 * 1024, "limit": 200 * 1024 * 1024, "stats": {"inactive_file": 0}},
    }
    result = docker_client_module.container_stats(c)
    # cpu_delta=500, system_delta=1000 -> (500/1000)*2*100 = 100.0
    assert result["cpu_percent"] == 100.0
    assert result["mem_used_mb"] == 100.0
    assert result["mem_limit_mb"] == 200.0
    assert result["mem_percent"] == 50.0


def test_container_stats_subtracts_page_cache(docker_client_module):
    c = MagicMock(status="running")
    c.stats.return_value = {
        "cpu_stats": {"cpu_usage": {"total_usage": 0}, "system_cpu_usage": 0},
        "precpu_stats": {"cpu_usage": {"total_usage": 0}, "system_cpu_usage": 0},
        "memory_stats": {"usage": 100 * 1024 * 1024, "limit": 200 * 1024 * 1024,
                          "stats": {"inactive_file": 40 * 1024 * 1024}},
    }
    result = docker_client_module.container_stats(c)
    assert result["mem_used_mb"] == 60.0


def test_container_stats_exception_falls_back_to_all_none(docker_client_module):
    c = MagicMock(status="running")
    c.stats.side_effect = RuntimeError("docker API unreachable")
    result = docker_client_module.container_stats(c)
    assert result == {"cpu_percent": None, "mem_used_mb": None, "mem_limit_mb": None, "mem_percent": None}


def test_project_containers_fails_when_self_not_found(docker_client_module, monkeypatch):
    from fastapi import HTTPException

    def raise_not_found():
        raise docker.errors.NotFound("no such container")

    monkeypatch.setattr(docker_client_module, "own_container", raise_not_found)
    with pytest.raises(HTTPException) as exc:
        docker_client_module.project_containers()
    assert exc.value.status_code == 502


def test_project_containers_fails_without_compose_label(docker_client_module, monkeypatch):
    from fastapi import HTTPException
    me = MagicMock()
    me.labels = {}
    monkeypatch.setattr(docker_client_module, "own_container", lambda: me)
    with pytest.raises(HTTPException) as exc:
        docker_client_module.project_containers()
    assert exc.value.status_code == 502


def test_find_project_container_not_found_404s(docker_client_module, monkeypatch):
    from fastapi import HTTPException
    me = MagicMock(id="self-id")
    monkeypatch.setattr(docker_client_module, "project_containers", lambda: (me, []))
    with pytest.raises(HTTPException) as exc:
        docker_client_module.find_project_container("ghost", reject_self=False)
    assert exc.value.status_code == 404


def test_find_project_container_rejects_self_when_flagged(docker_client_module, monkeypatch):
    from fastapi import HTTPException
    me = MagicMock(id="self-id")
    me.name = "control-panel"  # MagicMock(name=...) sets the mock's repr, not an attribute
    monkeypatch.setattr(docker_client_module, "project_containers", lambda: (me, [me]))
    with pytest.raises(HTTPException) as exc:
        docker_client_module.find_project_container("control-panel", reject_self=True)
    assert exc.value.status_code == 400


def test_wait_for_healthy_returns_when_healthy(docker_client_module, monkeypatch):
    container = MagicMock()
    container.attrs = {"State": {"Health": {"Status": "healthy"}}}
    monkeypatch.setattr(docker_client_module.time, "sleep", lambda s: None)
    # Should return without raising and without looping forever.
    docker_client_module.wait_for_healthy(container, timeout=5)


def test_wait_for_healthy_no_health_block_waits_once_then_returns(docker_client_module, monkeypatch):
    container = MagicMock()
    container.attrs = {"State": {}}
    sleep_calls = []
    monkeypatch.setattr(docker_client_module.time, "sleep", lambda s: sleep_calls.append(s))
    # time.monotonic() must eventually exceed deadline - patch a short timeout.
    docker_client_module.wait_for_healthy(container, timeout=0)
    assert 10 in sleep_calls

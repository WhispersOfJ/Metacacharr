"""Shared docker.from_env() client and fleet-discovery helpers, ported
from app.py (lines 149-169, 206, 346-411, 3788-3910) - Phase 2 of
.claude/plans/evolved-control-panel-backend.plan.md. Every integration
that needs container state imports from here instead of calling
docker.from_env() again.
"""
import socket
import time

import docker

from core.responses import fail

docker_client = docker.from_env()

CONTAINER_LABELS = {
    "radarr": ("Radarr", None),
    "sonarr": ("Sonarr", None),
    "prowlarr": ("Prowlarr", None),
    "plex": ("Plex", None),
    "nzbdav": ("NzbDAV", "Usenet, WebDAV + SABnzbd-compatible API"),
    "nzbdav_rclone": ("NzbDAV rclone", "rclone sidecar - FUSE-mounts NzbDAV's WebDAV tree"),
    "seerr": ("Seerr", None),
    "unpackerr": ("Unpackerr", None),
    "watchtower": ("Watchtower", None),
    "cleanuparr": ("Cleanuparr", "queue cleanup: strikes, malware block, stalled/failed removal"),
    "control-panel": ("Control Panel", "this dashboard"),
}

# Same FUSE-landmine mount ordering as app.py's stack_restart_all - see
# app.py's MOUNT_PREREQS comment block for the full history (NzbDAV/
# nzbdav-rclone -> BearMount -> nzbdav/nzbdav cutover) behind why prereqs
# restart first, then the provider, then everything else, then dependents
# last (and prereqs again, to rebind their own direct /mnt bind-mount).
MOUNT_PREREQS = {"nzbdav"}
MOUNT_PROVIDERS = {"nzbdav_rclone"}
MOUNT_DEPENDENTS = {"radarr", "sonarr", "plex", "unpackerr", "cleanuparr"}


def own_container():
    return docker_client.containers.get(socket.gethostname())


def project_containers():
    try:
        me = own_container()
    except docker.errors.NotFound:
        fail("Could not find this container's own record - can't determine the compose project.")
    project = me.labels.get("com.docker.compose.project")
    if not project:
        fail("This container has no compose project label - can't tell what 'the stack' is.")
    containers = docker_client.containers.list(
        all=True, filters={"label": f"com.docker.compose.project={project}"}
    )
    return me, containers


def container_stats(c) -> dict:
    if c.status != "running":
        return {"cpu_percent": None, "mem_used_mb": None, "mem_limit_mb": None, "mem_percent": None}
    try:
        s = c.stats(stream=False)
        cpu = s.get("cpu_stats", {})
        precpu = s.get("precpu_stats", {})
        cpu_total = cpu.get("cpu_usage", {}).get("total_usage")
        precpu_total = precpu.get("cpu_usage", {}).get("total_usage")
        system = cpu.get("system_cpu_usage")
        presystem = precpu.get("system_cpu_usage")
        online_cpus = cpu.get("online_cpus") or len(cpu.get("cpu_usage", {}).get("percpu_usage") or [1]) or 1
        cpu_percent = None
        if None not in (cpu_total, precpu_total, system, presystem):
            cpu_delta = cpu_total - precpu_total
            system_delta = system - presystem
            if system_delta > 0 and cpu_delta >= 0:
                cpu_percent = round((cpu_delta / system_delta) * online_cpus * 100, 1)
        mem = s.get("memory_stats", {})
        mem_used = mem.get("usage")
        mem_stats = mem.get("stats", {})
        cache = mem_stats.get("inactive_file", mem_stats.get("total_inactive_file", 0)) or 0
        if mem_used is not None:
            mem_used = max(mem_used - cache, 0)
        mem_limit = mem.get("limit")
        mem_used_mb = round(mem_used / 1024 / 1024, 1) if mem_used is not None else None
        mem_limit_mb = round(mem_limit / 1024 / 1024, 1) if mem_limit else None
        mem_percent = round((mem_used / mem_limit) * 100, 1) if mem_used and mem_limit else None
        return {
            "cpu_percent": cpu_percent,
            "mem_used_mb": mem_used_mb,
            "mem_limit_mb": mem_limit_mb,
            "mem_percent": mem_percent,
        }
    except Exception:
        return {"cpu_percent": None, "mem_used_mb": None, "mem_limit_mb": None, "mem_percent": None}


def find_project_container(name: str, *, reject_self: bool):
    me, containers = project_containers()
    match = next((c for c in containers if c.name == name), None)
    if match is None:
        fail(f"'{name}' is not a container in this compose project.", status_code=404)
    if reject_self and match.id == me.id:
        fail("This panel can't stop or restart itself - use the host/systemd to do that.", status_code=400)
    return match


def container_label(name: str) -> str:
    return CONTAINER_LABELS.get(name, (name, None))[0]


def wait_for_healthy(container, timeout=60):
    deadline = time.monotonic() + timeout
    saw_health_block = False
    while time.monotonic() < deadline:
        try:
            container.reload()
            status = container.attrs.get("State", {}).get("Health", {}).get("Status")
        except Exception:
            status = None
        if status:
            saw_health_block = True
            if status == "healthy":
                return
        time.sleep(2)
    if not saw_health_block:
        time.sleep(10)

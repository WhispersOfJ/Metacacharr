"""Fleet status/control + settings, ported from app.py (lines 437-501,
3802-3970) - Phase 2 of .claude/plans/evolved-control-panel-backend.plan.md.
Diagnostic routes (resource-check onward) added in Phase 4, ported from
app.py lines 4103-4321, 4444-4474, 4748-4816.

Auth split per the plan's Acceptance criteria: read-only routes accept
either a session or the health-check cron's service API key
(current_user_or_service); every mutating route (restart/stop/start,
restart-all, PATCH settings) requires a real logged-in session. The Phase
4 diagnostics are all read-only or trigger-a-one-off-check
(log-levels/reset, notify/test) - current_user_or_service throughout,
same reasoning as services/arr's automation-invoked routes.
"""
import concurrent.futures
import os
import re
import shutil
import threading
import time
from typing import Literal

import docker
import httpx
from core import settings as settings_core
from core.arr_client import ARR_APPS, PROWLARR_CFG
from core.docker_client import (
    CONTAINER_LABELS,
    MOUNT_DEPENDENTS,
    MOUNT_PREREQS,
    MOUNT_PROVIDERS,
    container_label,
    container_stats,
    docker_client,
    find_project_container,
    project_containers,
    wait_for_healthy,
)
from core.host_paths import HOST_CONFIG_DIR, HOST_MNT_DIR, HOST_PROC_DIR, HOST_README
from core.responses import fail, now, ok
from core.security import current_user, current_user_or_service
from core.rate_limit import rate_limit
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(tags=["host"])

SERVICE_META = {"label": "Host/Fleet", "health_check": None}


@router.get("/api/status")
def status(_=Depends(current_user_or_service)):
    _, containers = project_containers()
    out = {}
    for c in containers:
        health = c.attrs.get("State", {}).get("Health", {}).get("Status")
        out[c.name] = {"state": c.status, "health": health}
    return out


def _container_row(me, c) -> dict:
    label, note = CONTAINER_LABELS.get(c.name, (c.name, None))
    health = c.attrs.get("State", {}).get("Health", {}).get("Status")
    image_tags = c.image.tags
    image = image_tags[0] if image_tags else (c.image.short_id or "")
    service = c.labels.get("com.docker.compose.service", c.name)
    return {
        "name": c.name,
        "label": label,
        "note": note,
        "service": service,
        "image": image,
        "state": c.status,
        "health": health,
        "is_self": c.id == me.id,
        **container_stats(c),
    }


@router.get("/api/containers")
def containers_list(_=Depends(current_user_or_service)):
    me, containers = project_containers()
    ordered = sorted(containers, key=lambda c: c.name)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(ordered), 16) or 1) as pool:
        return list(pool.map(lambda c: _container_row(me, c), ordered))


@router.post("/api/container/{name}/restart")
# current_user_or_service, not current_user: stack-container.fish calls this
# unattended via __stack_api's service key (2026-08-06).
def container_restart(name: str, activated: bool = False, _=Depends(current_user_or_service)):
    if name == "plex" and not activated:
        fail(
            "Plex restart requires activated=true - a plain restart click is no longer "
            "enough (by design). Pass activated=true explicitly to restart Plex.",
            status_code=400,
        )
    c = find_project_container(name, reject_self=True)
    try:
        c.restart(timeout=30)
    except Exception as e:
        fail(f"Restart failed: {e}")
    return ok(f"{container_label(name)} restarted.")


@router.post("/api/container/{name}/stop")
# current_user_or_service, not current_user: stack-container.fish calls this
# unattended via __stack_api's service key (2026-08-06).
def container_stop(name: str, _=Depends(current_user_or_service)):
    c = find_project_container(name, reject_self=True)
    if c.status != "running":
        return ok(f"{container_label(name)} is already {c.status}.")
    try:
        c.stop(timeout=30)
    except Exception as e:
        fail(f"Stop failed: {e}")
    return ok(f"{container_label(name)} stopped.")


@router.post("/api/container/{name}/start")
# current_user_or_service, not current_user: stack-container.fish calls this
# unattended via __stack_api's service key (2026-08-06).
def container_start(name: str, _=Depends(current_user_or_service)):
    c = find_project_container(name, reject_self=False)
    if c.status == "running":
        return ok(f"{container_label(name)} is already running.")
    try:
        c.start()
    except Exception as e:
        fail(f"Start failed: {e}")
    return ok(f"{container_label(name)} started.")


@router.get("/api/container/{name}/logs/stream")
def container_logs_stream(name: str, tail: int = 100, _=Depends(current_user_or_service)):
    c = find_project_container(name, reject_self=False)

    def generate():
        for line in c.logs(stream=True, follow=True, tail=tail, timestamps=True):
            text = line.decode(errors="replace").rstrip("\n")
            for part in text.splitlines() or [""]:
                yield f"data: {part}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/api/stack/restart-all")
# current_user_or_service, not current_user: stack-restart-all.fish calls
# this unattended via __stack_api's service key (2026-08-06).
def stack_restart_all(_=Depends(current_user_or_service), _rate: None = Depends(rate_limit(max_requests=3, window_seconds=300))):
    me, containers = project_containers()
    targets = [c for c in containers if c.id != me.id]
    if not targets:
        fail("No other containers found in this compose project.")
    names = sorted(c.name for c in targets)

    prereqs = [c for c in targets if c.name in MOUNT_PREREQS]
    providers = [c for c in targets if c.name in MOUNT_PROVIDERS]
    dependents = [c for c in targets if c.name in MOUNT_DEPENDENTS]
    staged = MOUNT_PREREQS | MOUNT_PROVIDERS | MOUNT_DEPENDENTS
    rest = [c for c in targets if c.name not in staged]

    def worker():
        for c in prereqs:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")
        for c in prereqs:
            wait_for_healthy(c)
        for c in providers:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")
        for c in providers:
            wait_for_healthy(c)
        for c in rest:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")
        for c in dependents:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")
        # nzbdav bind-mounts /mnt directly too, not just as an upstream
        # prereq for nzbdav_rclone - re-restart it here, after every other
        # mount consumer has settled on the provider's final instance, to
        # rebind it. Same reasoning as app.py's stack_restart_all.
        for c in prereqs:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")

    threading.Thread(target=worker, daemon=True).start()
    return ok(f"Restarting {len(names)} containers (everything except this panel): {', '.join(names)}")


class SettingsPatch(BaseModel):
    theme: Literal["amber", "green"] | None = None
    failed_pending_storm_threshold: int | None = None
    loop_review_profile_threshold: int | None = None


@router.get("/api/settings")
def get_settings(_=Depends(current_user_or_service)):
    return settings_core.get_settings()


@router.patch("/api/settings")
def patch_settings(body: SettingsPatch, _=Depends(current_user)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return settings_core.update_settings(patch)


@router.get("/api/resource-check")
def resource_check(_=Depends(current_user_or_service)):
    """Every container missing mem_limit or cpus - the exact gap a live
    audit found for 10 services (docker stats silently reporting the full
    host memory as their ceiling instead of a real number)."""
    me, containers = project_containers()
    missing = []
    for c in containers:
        if c.id == me.id:
            continue
        host_config = c.attrs.get("HostConfig", {})
        mem_limit = host_config.get("Memory") or 0
        nano_cpus = host_config.get("NanoCpus") or 0
        if mem_limit == 0 or nano_cpus == 0:
            missing.append({
                "name": c.name,
                "mem_limit_set": mem_limit != 0,
                "cpus_set": nano_cpus != 0,
                **container_stats(c),
            })
    if not missing:
        return ok("Every container has both mem_limit and cpus set.", containers=[])
    return ok(f"{len(missing)} container(s) missing mem_limit and/or cpus.", containers=missing)


def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


@router.get("/api/disk-health")
def disk_health(_=Depends(current_user_or_service)):
    """Host mount free space (shutil.disk_usage against the read-only
    /mnt bind - real host filesystem stats, not container-scoped) plus
    Docker's own reclaimable-space breakdown (client.df(), the same data
    `docker system df` prints) - the "how much could I get back" half of
    disk health that the existing per-app disk-usage endpoint doesn't
    cover (that one sums config/ directory sizes, not what's reclaimable)."""
    total, used, free = shutil.disk_usage(HOST_MNT_DIR)
    mount = {
        "path": HOST_MNT_DIR, "total": _human_bytes(total), "used": _human_bytes(used),
        "free": _human_bytes(free), "percent": round(used / total * 100, 1) if total else 0.0,
    }
    try:
        df = docker_client.df()
    except docker.errors.APIError as e:
        fail(f"Docker df failed: {e}")
    reclaimable = {
        "images": sum(i.get("Size", 0) - i.get("SharedSize", 0) for i in df.get("Images") or [] if i.get("Containers") == 0),
        "containers": sum(c.get("SizeRw", 0) for c in df.get("Containers") or [] if c.get("State") != "running"),
        "volumes": sum(v.get("UsageData", {}).get("Size", 0) or 0 for v in df.get("Volumes") or [] if (v.get("UsageData") or {}).get("RefCount", 1) == 0),
        "build_cache": sum(b.get("Size", 0) for b in df.get("BuildCache") or [] if not b.get("InUse")),
    }
    reclaimable_human = {k: _human_bytes(v) for k, v in reclaimable.items()}
    total_reclaimable = sum(reclaimable.values())
    return ok(f"{mount['path']}: {mount['percent']}% used, {mount['free']} free. "
              f"{_human_bytes(total_reclaimable)} reclaimable from unused Docker images/volumes/build cache.",
              mount=mount, reclaimable=reclaimable_human, total_reclaimable=_human_bytes(total_reclaimable))


class PruneRequest(BaseModel):
    confirm: bool = False


@router.post("/api/disk-health/prune")
def disk_health_prune(payload: PruneRequest, _=Depends(current_user), _rate: None = Depends(rate_limit(max_requests=3, window_seconds=300))):
    """Prunes dangling images and unused (zero-refcount) volumes only -
    never a running or stopped-but-referenced container's own image or
    volume. Equivalent to `docker image prune` + `docker volume prune`,
    not the more aggressive `-a` variants."""
    if not payload.confirm:
        fail("Set confirm=true to prune - this deletes dangling images and unused volumes.", status_code=400)
    try:
        images_result = docker_client.images.prune()
        volumes_result = docker_client.volumes.prune()
    except docker.errors.APIError as e:
        fail(f"Prune failed: {e}")
    reclaimed = (images_result.get("SpaceReclaimed") or 0) + (volumes_result.get("SpaceReclaimed") or 0)
    return ok(f"Reclaimed {_human_bytes(reclaimed)} "
              f"({len(images_result.get('ImagesDeleted') or [])} image(s), "
              f"{len(volumes_result.get('VolumesDeleted') or [])} volume(s)).")


def _read_host_proc_meminfo() -> dict | None:
    path = os.path.join(HOST_PROC_DIR, "meminfo")
    if not os.path.isfile(path):
        return None
    values = {}
    with open(path) as f:
        for line in f:
            key, _, rest = line.partition(":")
            try:
                values[key] = int(rest.strip().split()[0]) * 1024  # kB -> bytes
            except (ValueError, IndexError):
                continue
    return values


def _read_host_proc_cpu_line() -> list[int] | None:
    path = os.path.join(HOST_PROC_DIR, "stat")
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        first = f.readline()
    if not first.startswith("cpu "):
        return None
    return [int(x) for x in first.split()[1:]]


@router.get("/api/host-resources")
def host_resources(_=Depends(current_user_or_service)):
    """Real host-wide CPU/RAM, read from /host-proc (bind-mounted for the
    Plex Health feature, 2026-07-26) - correcting an assumption in the
    original host.js comment ("this container has no pid:host, and no
    real host /proc") that was true when written but predates that mount.
    CPU percent needs two time-separated /proc/stat samples; this takes
    a short 200ms internal pause rather than relying on the caller to
    poll twice, so one request returns one real number."""
    mem = _read_host_proc_meminfo()
    cpu_before = _read_host_proc_cpu_line()
    if mem is None or cpu_before is None:
        fail(f"{HOST_PROC_DIR} not available - host resource stats need the Plex Health proc mount.", status_code=503)
    time.sleep(0.2)
    cpu_after = _read_host_proc_cpu_line()

    idle_before, idle_after = cpu_before[3], cpu_after[3]
    total_before, total_after = sum(cpu_before), sum(cpu_after)
    total_delta = total_after - total_before
    idle_delta = idle_after - idle_before
    cpu_percent = round((1 - idle_delta / total_delta) * 100, 1) if total_delta else 0.0

    mem_total = mem.get("MemTotal", 0)
    mem_available = mem.get("MemAvailable", mem.get("MemFree", 0))
    mem_used = mem_total - mem_available
    mem_percent = round(mem_used / mem_total * 100, 1) if mem_total else 0.0

    return ok(f"CPU {cpu_percent}%, RAM {mem_percent}% ({_human_bytes(mem_used)} / {_human_bytes(mem_total)}).",
              cpu_percent=cpu_percent, mem_percent=mem_percent,
              mem_used=_human_bytes(mem_used), mem_total=_human_bytes(mem_total))


LOG_LEVEL_APPS = {
    "radarr": ARR_APPS["radarr"],
    "sonarr": ARR_APPS["sonarr"],
    "prowlarr": PROWLARR_CFG,
}


@router.get("/api/log-levels")
def log_levels(_=Depends(current_user_or_service)):
    """Current logLevel for every Servarr-shaped app - debug left on in
    production was a real, invisible-until-checked finding this session
    (100MB+ log directories on 5 apps, likely months old)."""
    out = {}
    for name, cfg in LOG_LEVEL_APPS.items():
        try:
            r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/config/host", headers={"X-Api-Key": cfg["key"]}, timeout=10)
            r.raise_for_status()
            out[name] = r.json().get("logLevel")
        except Exception as e:
            out[name] = f"error: {e}"
    debug_apps = [n for n, lvl in out.items() if lvl == "debug"]
    msg = f"{len(debug_apps)} app(s) at debug: {', '.join(debug_apps)}" if debug_apps else "All apps at info (or non-debug)."
    return ok(msg, levels=out)


@router.post("/api/log-levels/reset")
def log_levels_reset(_=Depends(current_user_or_service), _rate: None = Depends(rate_limit(max_requests=3, window_seconds=300))):
    """Sets logLevel back to 'info' on every app currently at 'debug'."""
    reset = []
    for name, cfg in LOG_LEVEL_APPS.items():
        try:
            r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/config/host", headers={"X-Api-Key": cfg["key"]}, timeout=10)
            r.raise_for_status()
            current = r.json()
            if current.get("logLevel") != "debug":
                continue
            current["logLevel"] = "info"
            httpx.put(
                f"{cfg['url']}/api/{cfg['api']}/config/host/{current['id']}",
                headers={"X-Api-Key": cfg["key"], "Content-Type": "application/json"},
                json=current,
                timeout=10,
            ).raise_for_status()
            reset.append(name)
        except Exception as e:
            print(f"log-levels-reset: failed for {name}: {e}")
    if not reset:
        return ok("Nothing to reset - no app was at debug.")
    return ok(f"Reset {len(reset)} app(s) to info: {', '.join(reset)}")


@router.get("/api/oom-check")
def oom_check(_=Depends(current_user_or_service)):
    """Containers Docker itself has ever recorded an OOM kill for
    (State.OOMKilled) - the NeutArr finding (15 kills in one overnight
    window, invisible on the dashboard since restart:unless-stopped
    self-heals every time) came from journalctl, but Docker tracks this
    per-container without needing host journal access at all."""
    me, containers = project_containers()
    killed = [c.name for c in containers if c.id != me.id and c.attrs.get("State", {}).get("OOMKilled")]
    if not killed:
        return ok("No container currently shows an OOM-kill flag.", containers=[])
    return ok(
        f"{len(killed)} container(s) have been OOM-killed at least once (flag persists until next "
        f"recreate, not necessarily still happening): {', '.join(killed)}",
        containers=killed,
    )


@router.get("/api/disk-usage")
def disk_usage(_=Depends(current_user_or_service)):
    """Per-app config/ directory size - would have caught Stash's
    cache/generated growth (or any future app's) before it became a
    backup-bloat problem, instead of after."""
    if not os.path.isdir(HOST_CONFIG_DIR):
        fail(f"{HOST_CONFIG_DIR} not mounted.")
    sizes = []
    for entry in sorted(os.listdir(HOST_CONFIG_DIR)):
        path = os.path.join(HOST_CONFIG_DIR, entry)
        if not os.path.isdir(path):
            continue
        total = 0
        # followlinks=False keeps os.walk from descending into a symlinked
        # subdirectory; os.lstat().st_blocks * 512 (not st_size) matches
        # `du`'s own accounting through symlinks and sparse/preallocated
        # FUSE cache files - see app.py's original comment for the two
        # real bugs (349GB and 152GB false readings) this shape fixes.
        for dirpath, _, filenames in os.walk(path, followlinks=False):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.lstat(fp).st_blocks * 512
                except OSError:
                    pass
        sizes.append({"app": entry, "mb": round(total / 1024 / 1024, 1)})
    sizes.sort(key=lambda x: x["mb"], reverse=True)
    return ok(f"{len(sizes)} app config directories.", sizes=sizes)


KNOWN_MOUNTS = ["remote/nzbdav"]


@router.get("/api/mount-health")
def mount_health(_=Depends(current_user_or_service)):
    """Every known FUSE mountpoint under /mnt, checked for a clean listing -
    catches a stale mount (registered but dead backing process) before it
    causes the cascade failure documented in README's mount-cascade section."""
    results = []
    for name in KNOWN_MOUNTS:
        path = os.path.join(HOST_MNT_DIR, name)
        entry = {"mount": name, "path": path}
        if not os.path.exists(path):
            entry["status"] = "missing"
        else:
            try:
                os.listdir(path)
                entry["status"] = "healthy"
            except OSError as e:
                entry["status"] = f"stale: {e}"
        results.append(entry)
    unhealthy = [r for r in results if r["status"] != "healthy"]
    if not unhealthy:
        return ok("All known mounts resolve cleanly.", mounts=results)
    return ok(f"{len(unhealthy)} mount(s) not healthy: {', '.join(r['mount'] for r in unhealthy)}", mounts=results)


@router.get("/api/perms-check")
def perms_check(_=Depends(current_user_or_service)):
    """Config files that are root-owned and unreadable by group/other - the
    exact class of bug that left Stash's config.yml (mode 640) out of every
    backup run despite the backup script having no error handling that
    would have surfaced it. Doesn't need to actually run as that user to
    check this - just inspects the mode bits directly."""
    if not os.path.isdir(HOST_CONFIG_DIR):
        fail(f"{HOST_CONFIG_DIR} not mounted.")
    unreadable = []
    # followlinks=False + lstat, same reasoning as disk_usage() above.
    for dirpath, _, filenames in os.walk(HOST_CONFIG_DIR, followlinks=False):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                mode = os.lstat(fp).st_mode
            except OSError:
                continue
            # No group or other read bit at all.
            if not (mode & 0o044):
                unreadable.append(fp.replace(HOST_CONFIG_DIR, "config", 1))
    if not unreadable:
        return ok("No config files found unreadable by group/other.", files=[])
    return ok(f"{len(unreadable)} file(s) unreadable by group/other (won't be backed up):", files=unreadable[:200])


@router.get("/api/image-check")
def image_check(_=Depends(current_user_or_service)):
    """For every running container's image, queries the registry directly
    (no pull) for whether a newer digest exists under the same tag - the
    digest/exact-version-pinned tier Watchtower never touches on its own.
    Registry queries can be slow/rate-limited, so this is opt-in, not part
    of the container grid's own 15s poll."""
    me, containers = project_containers()
    results = []
    for c in containers:
        if c.id == me.id:
            continue
        image_tags = c.image.tags
        if not image_tags:
            continue
        tag_ref = image_tags[0]
        current_digests = set(c.image.attrs.get("RepoDigests", []))
        try:
            registry_data = docker_client.images.get_registry_data(tag_ref)
            remote_digest = registry_data.attrs.get("Descriptor", {}).get("digest")
            has_update = bool(remote_digest) and not any(remote_digest in d for d in current_digests)
            results.append({"name": c.name, "image": tag_ref, "update_available": has_update})
        except Exception as e:
            results.append({"name": c.name, "image": tag_ref, "update_available": None, "error": str(e)})
    updates = [r["name"] for r in results if r.get("update_available")]
    msg = f"{len(updates)} image(s) with a newer digest available: {', '.join(updates)}" if updates else \
          "No newer digests found for any currently-pinned tag (or all checks failed - see errors)."
    return ok(msg, images=results)


@router.get("/api/version")
def version(_=Depends(current_user_or_service)):
    """Current version from README's own declared line, plus a live
    core/extras container count - a quick doc-vs-reality drift check."""
    declared = "unknown"
    if os.path.isfile(HOST_README):
        with open(HOST_README) as f:
            for line in f:
                m = re.match(r"Current version: \*\*(v[\d.]+)\*\*", line)
                if m:
                    declared = m.group(1)
                    break
    me, containers = project_containers()
    running = sum(1 for c in containers if c.status == "running")
    total = len(containers)
    return ok(f"README declares {declared}. {running}/{total} containers currently running.",
              version=declared, running=running, total=total)


@router.get("/api/docs/readme")
def docs_readme(_=Depends(current_user_or_service)):
    """Raw text of this stack's own README.md - served as plain markdown
    text; the client renders it directly rather than pulling in a
    markdown-parsing dependency for one panel."""
    if not os.path.isfile(HOST_README):
        fail("README.md not mounted at /host-README.md.")
    with open(HOST_README) as f:
        return ok("README.md", text=f.read())


@router.post("/api/notify/test")
def notify_test(_=Depends(current_user_or_service), _rate: None = Depends(rate_limit(max_requests=3, window_seconds=300))):
    """Sends a real test message through the Discord webhook every
    backup/health-check alert already uses. ntfy was removed 2026-08-18
    (Plan 3 consolidation) and Discord is now the sole sink."""
    discord_webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not discord_webhook_url:
        fail("DISCORD_WEBHOOK_URL not set.")

    try:
        r = httpx.post(discord_webhook_url, json={"content": f"Control Panel test notification - {now()}"}, timeout=10)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Discord notification failed: {e}")

    return ok("Test notification sent.")


@router.get("/api/top")
def stack_top(by: str = "cpu", limit: int = 10, _=Depends(current_user_or_service)):
    """Top containers by CPU or memory in one compact list - the same data
    the container grid already shows per-card, sorted and truncated so a
    quick "what's using resources right now" doesn't mean scanning 30
    cards by eye."""
    if by not in ("cpu", "mem"):
        fail("'by' must be 'cpu' or 'mem'.", status_code=400)
    me, containers = project_containers()
    rows = []
    for c in containers:
        if c.id == me.id or c.status != "running":
            continue
        stats = container_stats(c)
        rows.append({
            "name": c.name,
            "cpu_percent": stats["cpu_percent"],
            "mem_percent": stats["mem_percent"],
            "mem_used_mb": stats["mem_used_mb"],
        })
    key = "cpu_percent" if by == "cpu" else "mem_percent"
    rows = [r for r in rows if r[key] is not None]
    rows.sort(key=lambda r: r[key], reverse=True)
    return ok(f"Top {min(limit, len(rows))} containers by {by}.", items=rows[:limit])

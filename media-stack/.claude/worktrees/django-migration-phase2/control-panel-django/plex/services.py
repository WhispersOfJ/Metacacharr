"""Plex routes, ported from the FastAPI-era
control-panel/services/plex/router.py (originally itself ported from
app.py lines 522-699, 3075-3369, 4537-4642, 5156-5180).

All routes are read-only or trigger-only (no destructive Plex action
exists here) - IsAuthenticatedOrServiceKey throughout (the default
EnvelopeAPIView tier), matching the FastAPI-era current_user_or_service
dependency used on every route in the source file, extended to the POSTs
since none of them mutate library state (scan/analyze/optimize/butler are
all Plex's own maintenance jobs, safe for the same automation callers as
the arr queue-autofix set).

This is the app the migration plan flags as needing the exact FastAPI
source read rather than plan-authored reimplementation: the D-state/
FUSE-waiting diagnostics (`_plex_dstate_threads`, `_fuse_waiting_total`,
`_mount_test`) are exactly the kind of logic a hand-retyped-from-summary
port would get subtly wrong (see project memory
project_bearmount_fuse_hang_investigation_2026-07-26 for how many subtle
bugs this exact category of code has produced before). Every helper below
is ported byte-identical in logic from the source, with only the
fail()->ServiceError / HTTPException->ServiceError transform applied.

Module-qualified references to core.plex_client (`plex_client.PLEX_URL`,
`plex_client.plex_headers()`, `plex_client.plex_sections()`) rather than
`from core.plex_client import PLEX_URL` are deliberate, matching
nzbdav/services.py's documented reasoning: PLEX_URL is a plain str
constant, and importing the name directly would bind a copy at import
time that tests could not monkeypatch. HOST_PROC_DIR/HOST_SYS_FUSE_DIR/
HOST_CONFIG_DIR are imported by name instead (matching ratings/seerr's
constant-import style) since tests monkeypatch them directly on this
module (`monkeypatch.setattr(services, "HOST_PROC_DIR", ...)`).
"""
import concurrent.futures
import logging
import os
import re

import docker
import httpx

from core import nzbdav_client, plex_client
from core.api_base import ServiceError
from core.docker_client import docker_client
from core.host_paths import HOST_CONFIG_DIR, HOST_PROC_DIR, HOST_SYS_FUSE_DIR

logger = logging.getLogger(__name__)


def scan() -> dict:
    try:
        r = httpx.get(f"{plex_client.PLEX_URL}/library/sections/all/refresh",
                       headers=plex_client.plex_headers(), timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"Plex scan failed: {e}") from e
    return {"message": "Scan for new files started across every library."}


def list_libraries() -> dict:
    """Library names as Plex itself knows them, read live from Plex."""
    try:
        sections = plex_client.plex_sections()
    except httpx.HTTPError as e:
        raise ServiceError(f"Could not read Plex libraries: {e}") from e
    items = [{"key": s["key"], "title": s["title"]} for s in sections]
    return {"message": f"{len(items)} Plex librar{'y' if len(items) == 1 else 'ies'}.", "items": items}


def _resolve_library_targets(library: str | None) -> list[dict]:
    try:
        sections = plex_client.plex_sections()
    except httpx.HTTPError as e:
        raise ServiceError(f"Could not read Plex libraries: {e}") from e
    targets = sections if library is None else [s for s in sections if s["title"].lower() == library.lower()]
    if not targets:
        raise ServiceError(f"No library found matching '{library}'.")
    return targets


def empty_trash(library: str | None = None) -> dict:
    """Empties trash on every library, or just one if `library` (matched
    case-insensitively against its title) is given."""
    targets = _resolve_library_targets(library)
    try:
        for s in targets:
            r = httpx.put(f"{plex_client.PLEX_URL}/library/sections/{s['key']}/emptyTrash",
                           headers=plex_client.plex_headers(), timeout=30)
            r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"Empty trash failed: {e}") from e
    return {"message": f"Trash emptied on: {', '.join(s['title'] for s in targets)}."}


def analyze(library: str | None = None) -> dict:
    """Queues Plex's per-item deep analysis for one library, or every
    library if none given."""
    targets = _resolve_library_targets(library)
    try:
        for s in targets:
            r = httpx.put(f"{plex_client.PLEX_URL}/library/sections/{s['key']}/analyze",
                           headers=plex_client.plex_headers(), timeout=30)
            r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"Analyze failed: {e}") from e
    return {"message": f"Deep analysis queued for: {', '.join(s['title'] for s in targets)}."}


def optimize_db() -> dict:
    try:
        r = httpx.post(f"{plex_client.PLEX_URL}/butler/OptimizeDatabase",
                        headers=plex_client.plex_headers(), timeout=30)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"Database optimize failed: {e}") from e
    return {"message": "Database optimization started."}


def clean_bundles() -> dict:
    try:
        r = httpx.post(f"{plex_client.PLEX_URL}/butler/CleanOldBundles",
                        headers=plex_client.plex_headers(), timeout=30)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"Clean bundles failed: {e}") from e
    return {"message": "Cleanup of old bundles started."}


# Every other Butler task Plex's own /butler endpoint currently advertises
# (confirmed live, not guessed - byte-identical to the FastAPI-era
# PLEX_BUTLER_TASKS table). OptimizeDatabase/CleanOldBundles already have
# dedicated routes above and are left out to avoid a duplicate path.
PLEX_BUTLER_TASKS = {
    "automatic-updates": "AutomaticUpdates",
    "backup-database": "BackupDatabase",
    "clean-log-files": "ButlerTaskCleanSupplementalLogFiles",
    "generate-ad-markers": "ButlerTaskGenerateAdMarkers",
    "generate-credits-markers": "ButlerTaskGenerateCreditsMarkers",
    "generate-intro-markers": "ButlerTaskGenerateIntroMarkers",
    "generate-voice-activity": "ButlerTaskGenerateVoiceActivity",
    "clean-cache-files": "CleanOldCacheFiles",
    "deep-media-analysis": "DeepMediaAnalysis",
    "garbage-collect-blobs": "GarbageCollectBlobs",
    "garbage-collect-media": "GarbageCollectLibraryMedia",
    "generate-chapter-thumbs": "GenerateChapterThumbs",
    "generate-media-index": "GenerateMediaIndexFiles",
    "loudness-analysis": "LoudnessAnalysis",
    "music-analysis": "MusicAnalysis",
    "process-assets": "ProcessAssets",
    "refresh-epg": "RefreshEpgGuides",
    "refresh-libraries": "RefreshLibraries",
    "refresh-local-media": "RefreshLocalMedia",
    "upgrade-media-analysis": "UpgradeMediaAnalysis",
}


def butler_task(task: str) -> dict:
    """Fires one named Butler task on demand - `task` is this stack's own
    kebab-case alias (see PLEX_BUTLER_TASKS), not Plex's raw CamelCase
    task name.

    Deviation from the FastAPI-era source: the source's fail() call for an
    unknown task used fail()'s default status_code (502). This plan's
    Step 2 explicitly specifies ServiceError(status=400) for an unknown
    Butler task (a client input-validation error, not an upstream
    failure) - followed here per the plan's literal test requirement."""
    plex_task = PLEX_BUTLER_TASKS.get(task)
    if plex_task is None:
        raise ServiceError(
            f"Unknown Butler task '{task}'. Known: {', '.join(sorted(PLEX_BUTLER_TASKS))}", status=400,
        )
    try:
        r = httpx.post(f"{plex_client.PLEX_URL}/butler/{plex_task}", headers=plex_client.plex_headers(), timeout=30)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"Butler task '{task}' failed: {e}") from e
    return {"message": f"Butler task started: {task}."}


def get_updates() -> dict:
    """Checks Plex's own update-checker. This container is pinned
    deliberately (see README's Image pinning policy) - this is a check,
    never an auto-apply action."""
    try:
        r = httpx.get(f"{plex_client.PLEX_URL}/identity", headers=plex_client.plex_headers(), timeout=10)
        r.raise_for_status()
        running_version = r.json().get("MediaContainer", {}).get("version")
    except httpx.HTTPError as e:
        raise ServiceError(f"Could not read Plex's running version: {e}") from e
    available = []
    try:
        r = httpx.get(f"{plex_client.PLEX_URL}/updater/status", headers=plex_client.plex_headers(), timeout=10)
        r.raise_for_status()
        for u in r.json().get("MediaContainer", {}).get("Release", []):
            available.append({"version": u.get("version"), "added_at": u.get("added")})
    except httpx.HTTPError:
        pass
    return {
        "message": "Plex is up to date." if not available else f"{len(available)} Plex update(s) available.",
        "running_version": running_version,
        "update_available": bool(available),
        "releases": available,
    }


def _plex_container_pid() -> int | None:
    """Pure Docker API metadata. Returns the HOST pid Docker itself
    reports for Plex's own init process."""
    try:
        c = docker_client.containers.get("plex")
        return c.attrs.get("State", {}).get("Pid") or None
    except docker.errors.NotFound:
        return None


def _bounded_exec(container, cmd: list[str], timeout: int = 5):
    """Runs container.exec_run(cmd) with a hard wall-clock bound.

    A bare ThreadPoolExecutor (no `with`) is required, not stylistic: a
    `with` block calls shutdown(wait=True) on exit, which blocks until the
    submitted worker actually finishes even after future.result(timeout=...)
    already raised TimeoutError - confirmed live 2026-07-25 this
    reintroduces the exact hang the timeout was meant to prevent. Do not
    "clean this up" into a context manager."""
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(container.exec_run, cmd=cmd)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        return None
    finally:
        pool.shutdown(wait=False)


def _plex_scanner_processes() -> list[str]:
    try:
        c = docker_client.containers.get("plex")
    except docker.errors.NotFound:
        return []
    try:
        result = _bounded_exec(c, ["ps", "aux"], timeout=5)
    except Exception as e:
        logger.error(f"_plex_scanner_processes: ps aux exec failed: {e}")
        return []
    if result is None:
        return []
    lines = result.output.decode(errors="replace").splitlines()
    return [line for line in lines if "Plex Media Scanner" in line]


def _plex_dstate_threads(pid: int | None) -> list[dict]:
    """Iterates /host-proc/{pid}/task/*/status for any thread in D (disk
    sleep, uninterruptible) state - the exact signature of a FUSE hang."""
    if not pid or not os.path.isdir(HOST_PROC_DIR):
        return []
    task_dir = os.path.join(HOST_PROC_DIR, str(pid), "task")
    found = []
    try:
        tids = os.listdir(task_dir)
    except OSError:
        return []
    for tid in tids:
        status_path = os.path.join(task_dir, tid, "status")
        try:
            with open(status_path) as f:
                text = f.read()
        except OSError:
            continue
        state = comm = None
        for line in text.splitlines():
            if line.startswith("State:"):
                state = line.split(":", 1)[1].strip()
            elif line.startswith("Name:"):
                comm = line.split(":", 1)[1].strip()
        if state and state.startswith("D "):
            entry = {"tid": tid, "comm": comm, "state": state}
            stack_path = os.path.join(task_dir, tid, "stack")
            try:
                with open(stack_path) as f:
                    entry["stack"] = f.read().strip().splitlines()[:6]
            except OSError:
                pass
            found.append(entry)
    return found


def _fuse_waiting_total() -> int:
    """Sums the 'waiting' counter across every live FUSE connection."""
    conn_dir = os.path.join(HOST_SYS_FUSE_DIR, "connections")
    if not os.path.isdir(conn_dir):
        return 0
    total = 0
    try:
        conn_ids = os.listdir(conn_dir)
    except OSError:
        return 0
    for conn_id in conn_ids:
        waiting_path = os.path.join(conn_dir, conn_id, "waiting")
        try:
            with open(waiting_path) as f:
                total += int(f.read().strip() or 0)
        except (OSError, ValueError):
            continue
    return total


def _plex_log_tail(lines: int = 200, tail_bytes: int = 512_000) -> dict:
    """Reads only the last `tail_bytes` of Plex's own log file - seeking
    from the end bounds this to a fixed amount of I/O regardless of how
    large the file gets (confirmed live 2026-07-25: reading the whole file
    made this route itself take 10s+ under a heavy scan burst, which
    looked like a real Plex freeze from the outside)."""
    empty = {"lines": [], "busy_db_errors": 0, "recent_busy_db_timestamps": [],
              "analysis_active": False, "analysis_batches": 0, "analysis_last_seconds": None}
    log_path = os.path.join(HOST_CONFIG_DIR, "plex", "Plex Media Server", "Logs", "Plex Media Server.log")
    if not os.path.isfile(log_path):
        return empty
    try:
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - tail_bytes))
            chunk = f.read().decode(errors="replace")
    except OSError:
        return empty
    all_lines = chunk.splitlines()
    tail = all_lines[-lines:]
    busy_lines = [line for line in all_lines if "busy database" in line]
    timestamps = [line.split("]")[0].split("[")[0].strip() for line in busy_lines[-10:]]

    analysis_lines = [line for line in all_lines
                       if "Media Analyzer" in line and ("Performing on-the-fly analysis" in line
                                                         or "Background analysis completed" in line)]
    last_analysis_seconds = None
    for line in reversed(analysis_lines):
        if "Background analysis completed in" in line:
            try:
                last_analysis_seconds = float(line.split("completed in")[1].split("seconds")[0].strip())
            except (IndexError, ValueError):
                pass
            break

    return {"lines": tail, "busy_db_errors": len(busy_lines), "recent_busy_db_timestamps": timestamps,
            "analysis_active": bool(analysis_lines), "analysis_batches": len(analysis_lines),
            "analysis_last_seconds": last_analysis_seconds}


def _nzbdav_queue_counts() -> dict:
    """Deviation from the FastAPI-era source: the source caught
    fastapi.HTTPException around nzbdav_api() here. core.nzbdav_client's
    Django-era nzbdav_api() raises core.api_base.ServiceError on failure
    instead (see core/nzbdav_client.py's module docstring) - catching
    ServiceError here is the direct equivalent."""
    try:
        slots = nzbdav_client.nzbdav_api("queue", timeout=5).get("queue", {}).get("slots", [])
    except ServiceError:
        return {"pending": 0, "processing": 0, "unreachable": True}
    processing = sum(1 for s in slots if s.get("status") == "Downloading")
    pending = len(slots) - processing
    return {"pending": pending, "processing": processing}


def _mount_test(container_name: str = "plex", timeout: int = 5) -> bool:
    """Bounded twice over: the in-container `timeout` command bounds a
    merely-slow mount, and _bounded_exec bounds the exec_run call itself
    from the caller's side."""
    try:
        c = docker_client.containers.get(container_name)
    except docker.errors.NotFound:
        return False
    try:
        result = _bounded_exec(c, ["timeout", str(timeout), "ls", "/mnt/remote/nzbdav"], timeout=timeout + 2)
    except Exception as e:
        logger.error(f"_mount_test: exec failed for container '{container_name}': {e}")
        return False
    if result is None:
        return False
    return result.exit_code == 0


def get_activities() -> list[dict]:
    try:
        r = httpx.get(f"{plex_client.PLEX_URL}/activities", headers=plex_client.plex_headers(), timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"Plex activities lookup failed: {e}") from e
    return r.json().get("MediaContainer", {}).get("Activity", [])


def get_progress_snapshot() -> dict[str, int]:
    """Cross-app dependency: imported by queue_app (Task 8) to sample
    Plex's own scan/analysis progress. Deviation from the FastAPI-era
    source: catches core.api_base.ServiceError instead of
    fastapi.HTTPException (see get_activities()/ServiceError above)."""
    try:
        return {a["uuid"]: a.get("progress", 0) for a in get_activities()}
    except ServiceError:
        return {}


def scan_health() -> dict:
    """One snapshot combining every signal used to tell a healthy-but-slow
    scan apart from a genuine hang: live /activities progress, whether a
    real scanner subprocess is actually running, D-state kernel threads,
    FUSE waiting-request count, a bounded mount test, NzbDAV's own queue
    state, and recent "busy database" log activity."""
    pid = _plex_container_pid()
    dstate = _plex_dstate_threads(pid)
    fuse_waiting = _fuse_waiting_total()
    mount_ok = _mount_test("plex")
    scanner_lines = _plex_scanner_processes()
    nzbdav_queue = _nzbdav_queue_counts()
    log_info = _plex_log_tail(lines=50)

    try:
        activities = get_activities()
    except ServiceError:
        activities = []

    try:
        c = docker_client.containers.get("plex")
        c.reload()
        health = c.attrs.get("State", {}).get("Health", {}).get("Status") or "unknown"
        restart_count = c.attrs.get("RestartCount", 0)
    except docker.errors.NotFound:
        health = "missing"
        restart_count = 0

    if dstate or not mount_ok:
        state = "hung_confirmed"
    elif nzbdav_queue.get("pending", 0) or nzbdav_queue.get("processing", 0):
        state = "stalled_suspected" if activities and not scanner_lines and not log_info["analysis_active"] else "scanning"
    elif activities:
        state = "scanning"
    else:
        state = "healthy"

    return {
        "message": f"Plex is {state.replace('_', ' ')}.",
        "state": state,
        "activities": activities,
        "scanner_running": bool(scanner_lines),
        "dstate_threads": dstate,
        "fuse_waiting": fuse_waiting,
        "mount_ok": mount_ok,
        "container": {"health": health, "restart_count": restart_count},
        "nzbdav_queue": nzbdav_queue,
        "recent_busy_db_errors": log_info["busy_db_errors"],
        "recent_busy_db_timestamps": log_info["recent_busy_db_timestamps"],
        "analysis_active": log_info["analysis_active"],
        "analysis_batches": log_info["analysis_batches"],
        "analysis_last_seconds": log_info["analysis_last_seconds"],
        "log_tail": log_info["lines"][-20:],
    }


def duplicates(min_gb: float = 5.0) -> dict:
    """Flags anything whose total size is more than 1.5x its single
    largest file - a movie with one real multi-version upgrade rarely
    trips this."""
    try:
        sections = plex_client.plex_sections()
    except httpx.HTTPError as e:
        raise ServiceError(f"Could not read Plex libraries: {e}") from e
    movie_sections = [s for s in sections if s.get("type") == "movie"]
    flagged = []
    for s in movie_sections:
        try:
            r = httpx.get(f"{plex_client.PLEX_URL}/library/sections/{s['key']}/all",
                           headers=plex_client.plex_headers(), timeout=30)
            r.raise_for_status()
        except httpx.HTTPError:
            continue
        for v in r.json().get("MediaContainer", {}).get("Metadata", []):
            sizes = list({int(p.get("size") or 0) for m in v.get("Media", []) for p in m.get("Part", [])})
            if len(sizes) < 2:
                continue
            total = sum(sizes)
            largest = max(sizes)
            if total < min_gb * 1e9 or total < largest * 1.5:
                continue
            flagged.append({
                "title": v.get("title"), "year": v.get("year"), "ratingKey": v.get("ratingKey"),
                "file_count": len(sizes), "total_gb": round(total / 1e9, 1), "largest_gb": round(largest / 1e9, 1),
            })
    flagged.sort(key=lambda f: f["total_gb"], reverse=True)
    return {"message": f"{len(flagged)} movie(s) look like they're carrying redundant duplicate files.",
            "items": flagged}


TMDB_LEGACY_GUID_RE = re.compile(r"com\.plexapp\.agents\.themoviedb://")


def tmdb_missing() -> dict:
    """Every movie/show (top-level, not episodes) with no TMDb link -
    neither the new agent's tmdb:// Guid nor the legacy
    com.plexapp.agents.themoviedb:// agent id."""
    try:
        sections = plex_client.plex_sections()
    except httpx.HTTPError as e:
        raise ServiceError(f"Could not read Plex libraries: {e}") from e
    targets = [s for s in sections if s.get("type") in ("movie", "show")]

    missing = []
    for s in targets:
        try:
            r = httpx.get(
                f"{plex_client.PLEX_URL}/library/sections/{s['key']}/all?includeGuids=1&X-Plex-Container-Size=200000",
                headers=plex_client.plex_headers(), timeout=60,
            )
            r.raise_for_status()
        except httpx.HTTPError:
            continue
        for item in r.json()["MediaContainer"].get("Metadata", []):
            has_tmdb = any(g.get("id", "").startswith("tmdb://") for g in item.get("Guid", []))
            if not has_tmdb and TMDB_LEGACY_GUID_RE.search(item.get("guid") or ""):
                has_tmdb = True
            if has_tmdb:
                continue
            missing.append({"library": s["title"], "title": item.get("title"), "year": item.get("year"),
                             "ratingKey": item.get("ratingKey")})
    return {"message": f"{len(missing)} item(s) missing a TMDb link.", "items": missing}


def sessions() -> dict:
    """Who's watching what right now, direct play vs transcode."""
    try:
        r = httpx.get(f"{plex_client.PLEX_URL}/status/sessions", headers=plex_client.plex_headers(), timeout=10)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"Could not read Plex sessions: {e}") from e
    result = []
    for v in r.json().get("MediaContainer", {}).get("Metadata", []):
        user = v.get("User") or {}
        player = v.get("Player") or {}
        media = (v.get("Media") or [{}])[0]
        title = f"{v['grandparentTitle']} - {v['title']}" if v.get("grandparentTitle") else v.get("title")
        duration = int(v.get("duration") or 1)
        result.append({
            "title": title, "user": user.get("title"), "player": player.get("product"), "state": player.get("state"),
            "decision": media.get("videoDecision") or media.get("selected"),
            "progress_pct": round(int(v.get("viewOffset") or 0) / max(duration, 1) * 100, 1),
        })
    return {"message": f"{len(result)} active session(s).", "sessions": result}


def recently_added(limit: int = 15) -> dict:
    """What actually finished importing and became visible in Plex."""
    try:
        r = httpx.get(f"{plex_client.PLEX_URL}/library/all", params={"sort": "addedAt:desc", "type": 1},
                       headers=plex_client.plex_headers(), timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"Could not read Plex's recently-added list: {e}") from e
    movies = r.json().get("MediaContainer", {}).get("Metadata", [])
    try:
        r = httpx.get(f"{plex_client.PLEX_URL}/library/all", params={"sort": "addedAt:desc", "type": 2},
                       headers=plex_client.plex_headers(), timeout=20)
        r.raise_for_status()
        shows = r.json().get("MediaContainer", {}).get("Metadata", [])
    except httpx.HTTPError:
        shows = []
    combined = sorted(movies + shows, key=lambda el: el.get("addedAt") or 0, reverse=True)[:limit]
    items = [{"title": el.get("title"), "year": el.get("year"), "type": el.get("type"),
              "addedAt": el.get("addedAt"), "librarySectionTitle": el.get("librarySectionTitle")}
             for el in combined]
    return {"message": f"{len(items)} most recently added item(s) across Plex movie/show libraries.",
            "items": items}

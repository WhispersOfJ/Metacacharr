"""Plex routes, ported from app.py (lines 522-699, 3075-3369, 4537-4642,
5156-5180) - Phase 4 of .claude/plans/evolved-control-panel-backend.plan.md.

All routes read-only or trigger-only (no destructive Plex action exists
here) - current_user_or_service throughout, matching services/arr's policy
for GETs, extended to these POSTs since none of them mutate library state
(scan/analyze/optimize/butler are all Plex's own maintenance jobs, safe for
the same automation callers as the arr queue-autofix set).
"""
import concurrent.futures
import os
import re

import docker
import httpx
from core.api_hit_counts import install as install_hit_counter
from core.api_hit_counts import register_host_label
from core.nzbdav_client import nzbdav_api
from core.docker_client import docker_client
from core.host_paths import HOST_CONFIG_DIR, HOST_PROC_DIR, HOST_SYS_FUSE_DIR
from core.logging_config import logger
from core.plex_client import PLEX_URL, plex_headers, plex_sections
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends

router = APIRouter(tags=["plex"])

SERVICE_META = {"label": "Plex", "health_check": None}

register_host_label(PLEX_URL, "Plex")
install_hit_counter()


@router.post("/api/plex/scan")
def plex_scan(_=Depends(current_user_or_service)):
    try:
        r = httpx.get(f"{PLEX_URL}/library/sections/all/refresh", headers=plex_headers(), timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Plex scan failed: {e}")
    return ok("Scan for new files started across every library.")


@router.get("/api/plex/libraries")
def plex_libraries(_=Depends(current_user_or_service)):
    """Library names as Plex itself knows them, read live from Plex."""
    try:
        sections = plex_sections()
    except httpx.HTTPError as e:
        fail(f"Could not read Plex libraries: {e}")
    return [{"key": s["key"], "title": s["title"]} for s in sections]


@router.post("/api/plex/empty-trash")
def plex_empty_trash(library: str | None = None, _=Depends(current_user_or_service)):
    """Empties trash on every library, or just one if `library` (matched
    case-insensitively against its title) is given."""
    try:
        sections = plex_sections()
        targets = sections if library is None else [s for s in sections if s["title"].lower() == library.lower()]
        if not targets:
            fail(f"No library found matching '{library}'.")
        for s in targets:
            r = httpx.put(f"{PLEX_URL}/library/sections/{s['key']}/emptyTrash", headers=plex_headers(), timeout=30)
            r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Empty trash failed: {e}")
    return ok(f"Trash emptied on: {', '.join(s['title'] for s in targets)}.")


@router.post("/api/plex/analyze")
def plex_analyze(library: str | None = None, _=Depends(current_user_or_service)):
    """Queues Plex's per-item deep analysis for one library, or every
    library if none given."""
    try:
        sections = plex_sections()
        targets = sections if library is None else [s for s in sections if s["title"].lower() == library.lower()]
        if not targets:
            fail(f"No library found matching '{library}'.")
        for s in targets:
            r = httpx.put(f"{PLEX_URL}/library/sections/{s['key']}/analyze", headers=plex_headers(), timeout=30)
            r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Analyze failed: {e}")
    return ok(f"Deep analysis queued for: {', '.join(s['title'] for s in targets)}.")


@router.post("/api/plex/optimize-db")
def plex_optimize_db(_=Depends(current_user_or_service)):
    try:
        r = httpx.post(f"{PLEX_URL}/butler/OptimizeDatabase", headers=plex_headers(), timeout=30)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Database optimize failed: {e}")
    return ok("Database optimization started.")


@router.post("/api/plex/clean-bundles")
def plex_clean_bundles(_=Depends(current_user_or_service)):
    try:
        r = httpx.post(f"{PLEX_URL}/butler/CleanOldBundles", headers=plex_headers(), timeout=30)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Clean bundles failed: {e}")
    return ok("Cleanup of old bundles started.")


# Every other Butler task Plex's own /butler endpoint currently advertises
# (confirmed live, not guessed). OptimizeDatabase/CleanOldBundles already
# have dedicated routes above and are left out to avoid a duplicate path.
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


@router.post("/api/plex/butler/{task}")
def plex_butler_task(task: str, _=Depends(current_user_or_service)):
    """Fires one named Butler task on demand - `task` is this stack's own
    kebab-case alias (see PLEX_BUTLER_TASKS), not Plex's raw CamelCase
    task name."""
    plex_task = PLEX_BUTLER_TASKS.get(task)
    if plex_task is None:
        fail(f"Unknown Butler task '{task}'. Known: {', '.join(sorted(PLEX_BUTLER_TASKS))}")
    try:
        r = httpx.post(f"{PLEX_URL}/butler/{plex_task}", headers=plex_headers(), timeout=30)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Butler task '{task}' failed: {e}")
    return ok(f"Butler task started: {task}.")


@router.get("/api/plex/updates")
def plex_updates(_=Depends(current_user_or_service)):
    """Checks Plex's own update-checker. This container is pinned
    deliberately (see README's Image pinning policy) - this is a check,
    never an auto-apply action."""
    try:
        r = httpx.get(f"{PLEX_URL}/identity", headers=plex_headers(), timeout=10)
        r.raise_for_status()
        running_version = r.json().get("MediaContainer", {}).get("version")
    except httpx.HTTPError as e:
        fail(f"Could not read Plex's running version: {e}")
    available = []
    try:
        r = httpx.get(f"{PLEX_URL}/updater/status", headers=plex_headers(), timeout=10)
        r.raise_for_status()
        for u in r.json().get("MediaContainer", {}).get("Release", []):
            available.append({"version": u.get("version"), "added_at": u.get("added")})
    except httpx.HTTPError:
        pass
    return {"running_version": running_version, "update_available": bool(available), "releases": available}


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
    from fastapi import HTTPException
    try:
        slots = nzbdav_api("queue", timeout=5).get("queue", {}).get("slots", [])
    except HTTPException:
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


def plex_activities() -> list[dict]:
    try:
        r = httpx.get(f"{PLEX_URL}/activities", headers=plex_headers(), timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Plex activities lookup failed: {e}")
    return r.json().get("MediaContainer", {}).get("Activity", [])


def plex_progress_snapshot() -> dict[str, int]:
    from fastapi import HTTPException
    try:
        return {a["uuid"]: a.get("progress", 0) for a in plex_activities()}
    except HTTPException:
        return {}


@router.get("/api/plex/scan-health")
def plex_scan_health(_=Depends(current_user_or_service)):
    """One snapshot combining every signal used to tell a healthy-but-slow
    scan apart from a genuine hang: live /activities progress, whether a
    real scanner subprocess is actually running, D-state kernel threads,
    FUSE waiting-request count, a bounded mount test, NzbDAV's own queue
    state, and recent "busy database" log activity."""
    from fastapi import HTTPException

    pid = _plex_container_pid()
    dstate = _plex_dstate_threads(pid)
    fuse_waiting = _fuse_waiting_total()
    mount_ok = _mount_test("plex")
    scanner_lines = _plex_scanner_processes()
    nzbdav_queue = _nzbdav_queue_counts()
    log_info = _plex_log_tail(lines=50)

    try:
        activities = plex_activities()
    except HTTPException:
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

    return ok(f"Plex is {state.replace('_', ' ')}.",
              state=state,
              activities=activities,
              scanner_running=bool(scanner_lines),
              dstate_threads=dstate,
              fuse_waiting=fuse_waiting,
              mount_ok=mount_ok,
              container={"health": health, "restart_count": restart_count},
              nzbdav_queue=nzbdav_queue,
              recent_busy_db_errors=log_info["busy_db_errors"],
              recent_busy_db_timestamps=log_info["recent_busy_db_timestamps"],
              analysis_active=log_info["analysis_active"],
              analysis_batches=log_info["analysis_batches"],
              analysis_last_seconds=log_info["analysis_last_seconds"],
              log_tail=log_info["lines"][-20:])


@router.get("/api/plex/duplicates")
def plex_duplicates(min_gb: float = 5.0, _=Depends(current_user_or_service)):
    """Flags anything whose total size is more than 1.5x its single
    largest file - a movie with one real multi-version upgrade rarely
    trips this."""
    try:
        sections = plex_sections()
    except httpx.HTTPError as e:
        fail(f"Could not read Plex libraries: {e}")
    movie_sections = [s for s in sections if s.get("type") == "movie"]
    flagged = []
    for s in movie_sections:
        try:
            r = httpx.get(f"{PLEX_URL}/library/sections/{s['key']}/all", headers=plex_headers(), timeout=30)
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
    return ok(f"{len(flagged)} movie(s) look like they're carrying redundant duplicate files.", items=flagged)


TMDB_LEGACY_GUID_RE = re.compile(r"com\.plexapp\.agents\.themoviedb://")


@router.get("/api/plex/tmdb-missing")
def plex_tmdb_missing(_=Depends(current_user_or_service)):
    """Every movie/show (top-level, not episodes) with no TMDb link -
    neither the new agent's tmdb:// Guid nor the legacy
    com.plexapp.agents.themoviedb:// agent id."""
    try:
        sections = plex_sections()
    except httpx.HTTPError as e:
        fail(f"Could not read Plex libraries: {e}")
    targets = [s for s in sections if s.get("type") in ("movie", "show")]

    missing = []
    for s in targets:
        try:
            r = httpx.get(f"{PLEX_URL}/library/sections/{s['key']}/all?includeGuids=1&X-Plex-Container-Size=200000",
                           headers=plex_headers(), timeout=60)
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
    return ok(f"{len(missing)} item(s) missing a TMDb link.", items=missing)


@router.get("/api/plex/sessions")
def plex_sessions(_=Depends(current_user_or_service)):
    """Who's watching what right now, direct play vs transcode."""
    try:
        r = httpx.get(f"{PLEX_URL}/status/sessions", headers=plex_headers(), timeout=10)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Could not read Plex sessions: {e}")
    sessions = []
    for v in r.json().get("MediaContainer", {}).get("Metadata", []):
        user = v.get("User") or {}
        player = v.get("Player") or {}
        media = (v.get("Media") or [{}])[0]
        title = f"{v['grandparentTitle']} - {v['title']}" if v.get("grandparentTitle") else v.get("title")
        duration = int(v.get("duration") or 1)
        sessions.append({
            "title": title, "user": user.get("title"), "player": player.get("product"), "state": player.get("state"),
            "decision": media.get("videoDecision") or media.get("selected"),
            "progress_pct": round(int(v.get("viewOffset") or 0) / max(duration, 1) * 100, 1),
        })
    return ok(f"{len(sessions)} active session(s).", sessions=sessions)


@router.get("/api/plex/recently-added")
def plex_recently_added(limit: int = 15, _=Depends(current_user_or_service)):
    """What actually finished importing and became visible in Plex."""
    try:
        r = httpx.get(f"{PLEX_URL}/library/all", params={"sort": "addedAt:desc", "type": 1},
                       headers=plex_headers(), timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Could not read Plex's recently-added list: {e}")
    movies = r.json().get("MediaContainer", {}).get("Metadata", [])
    try:
        r = httpx.get(f"{PLEX_URL}/library/all", params={"sort": "addedAt:desc", "type": 2},
                       headers=plex_headers(), timeout=20)
        r.raise_for_status()
        shows = r.json().get("MediaContainer", {}).get("Metadata", [])
    except httpx.HTTPError:
        shows = []
    combined = sorted(movies + shows, key=lambda el: el.get("addedAt") or 0, reverse=True)[:limit]
    items = [{"title": el.get("title"), "year": el.get("year"), "type": el.get("type"),
              "addedAt": el.get("addedAt"), "librarySectionTitle": el.get("librarySectionTitle")}
             for el in combined]
    return ok(f"{len(items)} most recently added item(s) across Plex movie/show libraries.", items=items)

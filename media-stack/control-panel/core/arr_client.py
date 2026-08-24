"""Shared Radarr/Sonarr config + helpers, ported from app.py's ARR_APPS
block and its surrounding functions (app.py lines ~114-133, 1643-3720ish) -
Phase 3 of .claude/plans/evolved-control-panel-backend.plan.md.

Every services/arr|radarr|sonarr/router.py route imports from here instead
of re-declaring ARR_APPS or re-implementing the queue/command/history
helpers, mirroring app.py's own single-source-of-truth design.
"""
import os
import re
from datetime import datetime, timezone

import httpx

from core.nzbdav_client import NZBDAV_API_KEY, NZBDAV_URL, nzbdav_api  # noqa: F401
from core.responses import fail

# Internal stacknet hostnames - not HOST_IP, since this container reaches
# every *arr app over the docker network directly. Bare os.environ[...]
# subscript matches app.py's own behavior: a missing key is a deployment
# misconfiguration that should fail loudly at import time, not silently
# produce a broken ARR_APPS entry.
ARR_APPS = {
    "radarr": {
        "url": "http://radarr:7878",
        "api": "v3",
        "key": os.environ["RADARR_API_KEY"],
        "search_command": "MissingMoviesSearch",
        "label": "Radarr",
        "import_events": ("downloadFolderImported",),
    },
    "sonarr": {
        "url": "http://sonarr:8989",
        "api": "v3",
        "key": os.environ["SONARR_API_KEY"],
        "search_command": "MissingEpisodeSearch",
        "label": "Sonarr",
        "import_events": ("downloadFolderImported",),
    },
}

# Radarr and Sonarr both have a real download queue (NzbDAV wired to each as
# the sole download client) - Unstick/manual-import work identically on both.
QUEUE_ARR_APPS = ("radarr", "sonarr")

RADARR_APPS = ("radarr",)

SONARR_APPS = ("sonarr",)

PROWLARR_API_KEY = os.environ.get("PROWLARR_API_KEY")
PROWLARR_CFG = {"url": "http://prowlarr:9696", "api": "v1", "key": PROWLARR_API_KEY, "label": "Prowlarr"}

HOST_CONFIG_DIR = "/host-config"

# NzbDAV's SABnzbd-compatible API - queue-autofix (below) needs its queue
# health (paused state). Now owned by core/nzbdav_client.py (Phase 4);
# re-exported here (see the import at the top of the file) only so
# services/arr/router.py's existing import keeps working without touching
# every call site.


def human_size(n: int | None) -> str:
    if not n:
        return "?"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def format_eta(seconds: float) -> str:
    if seconds == float("inf") or seconds < 0:
        return "unknown"
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d{hours:02d}h"
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def arr_command(app_name: str, command: str) -> dict:
    if app_name not in ARR_APPS:
        fail(f"Unknown app '{app_name}'.", status_code=404)
    cfg = ARR_APPS[app_name]
    url = f"{cfg['url']}/api/{cfg['api']}/command"
    try:
        r = httpx.post(url, json={"name": command}, headers={"X-Api-Key": cfg["key"]}, timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} {command} failed: {e}")
    return cfg


def require_queue_app(app_name: str) -> dict:
    if app_name not in QUEUE_ARR_APPS:
        fail(f"'{app_name}' isn't supported here - only radarr and sonarr have a queue.", status_code=404)
    return ARR_APPS[app_name]


def arr_queue(app_name: str) -> list[dict]:
    cfg = ARR_APPS[app_name]
    params = {"pageSize": 250, "includeUnknownMovieItems": "true"}
    params["includeMovie" if app_name in RADARR_APPS else "includeEpisode"] = "true"
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/queue", params=params, headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} queue lookup failed: {e}")
    return r.json().get("records", [])


def stuck_queue_items(app_name: str) -> list[dict]:
    # warning/error is exactly what lights up the warning icon in Radarr's
    # and Sonarr's own Activity/Queue tab - not "importPending", which is
    # just normal in-progress state.
    return [q for q in arr_queue(app_name) if q.get("trackedDownloadStatus") in ("warning", "error")]


def import_candidate_queue_items(app_name: str) -> list[dict]:
    # Broader than stuck_queue_items - also includes "importPending" (fully
    # downloaded, waiting on the arr app's own internal queue-processing
    # command to actually run the import).
    return [
        q for q in arr_queue(app_name)
        if q.get("trackedDownloadStatus") in ("warning", "error")
        or q.get("trackedDownloadState") == "importPending"
    ]


def get_movie_or_episode(app_name: str, cfg: dict, target_id: int) -> dict | None:
    endpoint = "movie" if app_name in RADARR_APPS else "episode"
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/{endpoint}/{target_id}", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError:
        return None


def item_is_monitored(app_name: str, q: dict, cfg: dict, id_field: str) -> bool:
    # unmonitored movies/episodes should never be re-searched by the loop -
    # the queue response's embedded movie/episode object is NOT reliable
    # (confirmed live: can sit null for 8+ seconds straight), so always
    # confirm via a direct lookup by id instead of trusting it blindly.
    embedded = q.get("movie") if app_name in RADARR_APPS else q.get("episode")
    if embedded is not None:
        return bool(embedded.get("monitored", True))
    target_id = q.get(id_field)
    if target_id is None:
        return True
    endpoint = "movie" if app_name in RADARR_APPS else "episode"
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/{endpoint}/{target_id}", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
        return bool(r.json().get("monitored", True))
    except httpx.HTTPError:
        return True


def blocklist_and_research(app_name: str, items: list[dict]) -> tuple[list[str], list[str]]:
    cfg = ARR_APPS[app_name]
    fixed, errors = [], []
    search_ids: list[int] = []
    id_field = "movieId" if app_name in RADARR_APPS else "episodeId"
    for q in items:
        title = q.get("title") or str(q["id"])
        monitored = item_is_monitored(app_name, q, cfg, id_field)
        params = {"removeFromClient": "true", "blocklist": "true", "skipRedownload": str(not monitored).lower()}
        delete_ok = False
        for attempt in range(2):
            try:
                r = httpx.delete(f"{cfg['url']}/api/{cfg['api']}/queue/{q['id']}", params=params,
                                  headers={"X-Api-Key": cfg["key"]}, timeout=20)
                if r.status_code not in (200, 404):
                    r.raise_for_status()
                delete_ok = True
                break
            except httpx.TimeoutException:
                if attempt == 0:
                    continue
                errors.append(f"{title}: timed out")
            except httpx.HTTPError as e:
                errors.append(f"{title}: {e}")
                break
        if not delete_ok:
            continue
        fixed.append(title)
        target_id = q.get(id_field)
        if monitored and target_id is not None:
            search_ids.append(target_id)
    if search_ids:
        command_name = "MoviesSearch" if app_name in RADARR_APPS else "EpisodeSearch"
        command_field = "movieIds" if app_name in RADARR_APPS else "episodeIds"
        try:
            r = httpx.post(f"{cfg['url']}/api/{cfg['api']}/command", json={"name": command_name, command_field: search_ids},
                            headers={"X-Api-Key": cfg["key"]}, timeout=20)
            r.raise_for_status()
        except httpx.HTTPError as e:
            errors.append(f"search trigger failed for {len(search_ids)} item(s): {e}")
    return fixed, errors


def disable_autoredownload_if_storm(app_name: str, failed_pending_count: int, threshold: int) -> bool:
    if failed_pending_count < threshold:
        return False
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/config/downloadclient", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
        current = r.json()
        if not current.get("autoRedownloadFailed"):
            return False
        current["autoRedownloadFailed"] = False
        r = httpx.put(f"{cfg['url']}/api/{cfg['api']}/config/downloadclient/{current['id']}", json=current,
                       headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


IMPORTING_TEST_TIMEOUT_S = 40
IMPORTING_TEST_MB = 5


def dd_test_file(container, file_path: str) -> tuple[bool, str]:
    try:
        result = container.exec_run(
            cmd=["timeout", str(IMPORTING_TEST_TIMEOUT_S), "dd", f"if={file_path}", "of=/dev/null", "bs=1M",
                 f"count={IMPORTING_TEST_MB}"],
            demux=True,
        )
    except Exception as e:
        return False, f"exec failed: {e}"
    if result.exit_code == 0:
        return True, "readable"
    stderr = b""
    if result.output and result.output[1]:
        stderr = result.output[1]
    return False, stderr.decode(errors="replace").strip() or f"dd exited {result.exit_code}"


def find_candidate_files(container, output_path: str) -> tuple[str, list[str]]:
    """Returns (status, files): 'missing' if output_path doesn't exist on
    disk at all, 'empty' if the path exists but has no file worth testing,
    or 'ok' with the files found."""
    exists = container.exec_run(cmd=["test", "-e", output_path])
    if exists.exit_code != 0:
        return "missing", []
    find_result = container.exec_run(cmd=["find", output_path, "-maxdepth", "2", "-type", "l"])
    files = [f for f in find_result.output.decode(errors="replace").splitlines() if f.strip()]
    if not files:
        find_result = container.exec_run(cmd=["find", output_path, "-maxdepth", "2", "-type", "f"])
        files = [f for f in find_result.output.decode(errors="replace").splitlines() if f.strip()]
    return ("ok", files) if files else ("empty", [])


def importing_queue_targets(app_name: str) -> list[dict]:
    # Multiple queue records can share one underlying download (a season
    # pack fans out to one record per episode, all with the same
    # downloadId) - dedupe before testing.
    items = [q for q in arr_queue(app_name) if q.get("trackedDownloadState") == "importing"]
    by_download: dict[str, dict] = {}
    for q in items:
        key = q.get("downloadId") or str(q["id"])
        target = by_download.setdefault(key, {
            "queueIds": [], "title": q.get("title"), "outputPath": q.get("outputPath"),
            "seriesId": q.get("seriesId"), "movieId": q.get("movieId"),
        })
        target["queueIds"].append(q["id"])
    return list(by_download.values())


DEDUP_SUFFIX_RE = re.compile(r"\s\(\d+\)(\.[A-Za-z0-9]+)?$")


def dedup_suffix_hit(name: str | None) -> bool:
    if not name:
        return False
    base = name.rsplit("/", 1)[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    return bool(DEDUP_SUFFIX_RE.search(stem))


def current_queue_output_path(app_name: str, target_id: int, id_field: str) -> str | None:
    for q in arr_queue(app_name):
        if q.get(id_field) == target_id:
            return q.get("outputPath")
    return None


def arr_sizeleft_snapshot(app_name: str) -> dict[int, int]:
    from fastapi import HTTPException
    try:
        records = arr_queue(app_name)
    except HTTPException:
        return {}
    return {q["id"]: q.get("sizeleft") or 0 for q in records if q.get("sizeleft")}


def wanted_missing_total(app_name: str) -> int:
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/wanted/missing", params={"pageSize": 1},
                       headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} wanted/missing lookup failed: {e}")
    return r.json().get("totalRecords", 0)


RECENT_IMPORT_LOOKBACK_HOURS = 6
RECENT_IMPORT_SAMPLE_SIZE = 200
MIN_RATE_WINDOW_HOURS = 0.25


def recent_import_rate_per_hour(app_name: str) -> tuple[float, int]:
    """Returns (rate_per_hour, sample_count). Rate is 0 if there aren't at
    least 2 qualifying events, or the newest one is older than
    RECENT_IMPORT_LOOKBACK_HOURS."""
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/history",
                       params={"pageSize": RECENT_IMPORT_SAMPLE_SIZE, "sortKey": "date", "sortDirection": "descending"},
                       headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} history lookup failed: {e}")
    records = r.json().get("records", [])
    events = [rec for rec in records if rec.get("eventType") in cfg["import_events"]]
    if len(events) < 2:
        return 0.0, len(events)
    newest = datetime.fromisoformat(events[0]["date"].replace("Z", "+00:00"))
    oldest = datetime.fromisoformat(events[-1]["date"].replace("Z", "+00:00"))
    if (datetime.now(timezone.utc) - newest).total_seconds() > RECENT_IMPORT_LOOKBACK_HOURS * 3600:
        return 0.0, len(events)
    span_hours = max((newest - oldest).total_seconds() / 3600, MIN_RATE_WINDOW_HOURS)
    return len(events) / span_hours, len(events)


def radarr_root_folder_and_profile(cfg, root_folder: str | None, quality_profile: str | None) -> tuple[str, int]:
    try:
        folders = httpx.get(f"{cfg['url']}/api/{cfg['api']}/rootfolder", headers={"X-Api-Key": cfg["key"]}, timeout=15).json()
        profiles = httpx.get(f"{cfg['url']}/api/{cfg['api']}/qualityprofile", headers={"X-Api-Key": cfg["key"]}, timeout=15).json()
    except httpx.HTTPError as e:
        fail(f"Couldn't read Radarr's root folders/quality profiles: {e}")

    root_folder_path = (
        root_folder
        or next((f["path"] for f in folders if f["path"] == "/data/movies"), None)
        or (folders[0]["path"] if folders else None)
    )
    if not root_folder_path:
        fail("Radarr has no root folders configured.", status_code=500)

    wanted_profile = quality_profile or "Unlimited"
    quality_profile_id = next((p["id"] for p in profiles if p["name"] == wanted_profile), None)
    if quality_profile_id is None:
        quality_profile_id = profiles[0]["id"] if profiles else None
    if quality_profile_id is None:
        fail("Radarr has no quality profiles configured.", status_code=500)

    return root_folder_path, quality_profile_id


def radarr_quality_profile_id_by_name(cfg: dict, name: str) -> int | None:
    try:
        profiles = httpx.get(f"{cfg['url']}/api/{cfg['api']}/qualityprofile", headers={"X-Api-Key": cfg["key"]}, timeout=15).json()
    except httpx.HTTPError:
        return None
    return next((p["id"] for p in profiles if p["name"] == name), None)


def radarr_ensure_tags(cfg: dict, tag_names: list[str]) -> list[int]:
    """Returns the Radarr tag ids for tag_names, creating any that don't
    exist yet. Radarr's v3 tag API requires creating a tag via POST /tag
    before it can be referenced by id on a movie - there's no
    create-on-attach shortcut."""
    if not tag_names:
        return []
    try:
        existing = httpx.get(f"{cfg['url']}/api/{cfg['api']}/tag", headers={"X-Api-Key": cfg["key"]}, timeout=15).json()
    except httpx.HTTPError as e:
        fail(f"Couldn't read Radarr's tags: {e}")
    by_label = {t["label"]: t["id"] for t in existing}

    ids = []
    for name in tag_names:
        if name in by_label:
            ids.append(by_label[name])
            continue
        try:
            created = httpx.post(f"{cfg['url']}/api/{cfg['api']}/tag", json={"label": name},
                                  headers={"X-Api-Key": cfg["key"]}, timeout=15)
            created.raise_for_status()
        except httpx.HTTPError as e:
            fail(f"Couldn't create Radarr tag '{name}': {e}")
        new_id = created.json()["id"]
        by_label[name] = new_id
        ids.append(new_id)
    return ids


def sonarr_root_folder_and_profile(cfg, root_folder: str | None, quality_profile: str | None) -> tuple[str, int]:
    try:
        folders = httpx.get(f"{cfg['url']}/api/{cfg['api']}/rootfolder", headers={"X-Api-Key": cfg["key"]}, timeout=15).json()
        profiles = httpx.get(f"{cfg['url']}/api/{cfg['api']}/qualityprofile", headers={"X-Api-Key": cfg["key"]}, timeout=15).json()
    except httpx.HTTPError as e:
        fail(f"Couldn't read Sonarr's root folders/quality profiles: {e}")

    root_folder_path = (
        root_folder
        or next((f["path"] for f in folders if f["path"] == "/data/shows"), None)
        or (folders[0]["path"] if folders else None)
    )
    if not root_folder_path:
        fail("Sonarr has no root folders configured.", status_code=500)

    wanted_profile = quality_profile or "Any"
    quality_profile_id = next((p["id"] for p in profiles if p["name"] == wanted_profile), None)
    if quality_profile_id is None:
        quality_profile_id = profiles[0]["id"] if profiles else None
    if quality_profile_id is None:
        fail("Sonarr has no quality profiles configured.", status_code=500)

    return root_folder_path, quality_profile_id


def radarr_add_movie(cfg, tmdb_id: int, monitored: bool, search: bool, root_folder_path: str, quality_profile_id: int,
                      existing_tmdb_ids: set[int], dry_run: bool = False, tag_ids: list[int] | None = None) -> dict:
    if tmdb_id in existing_tmdb_ids:
        return {"status": "already", "title": None, "tmdbId": tmdb_id}
    try:
        lookup = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie/lookup/tmdb", params={"tmdbId": tmdb_id},
                            headers={"X-Api-Key": cfg["key"]}, timeout=20)
        lookup.raise_for_status()
        movie = lookup.json()
    except httpx.HTTPError as e:
        return {"status": "failed", "reason": f"tmdb {tmdb_id}: lookup failed ({e})"}
    if not movie or not movie.get("title"):
        return {"status": "failed", "reason": f"tmdb {tmdb_id}: no Radarr match"}

    movie["qualityProfileId"] = quality_profile_id
    movie["rootFolderPath"] = root_folder_path
    movie["monitored"] = monitored
    movie["addOptions"] = {"searchForMovie": search}
    if tag_ids:
        movie["tags"] = tag_ids

    if dry_run:
        return {"status": "added", "title": movie["title"]}

    try:
        add = httpx.post(f"{cfg['url']}/api/{cfg['api']}/movie", json=movie, headers={"X-Api-Key": cfg["key"]}, timeout=30)
        add.raise_for_status()
    except httpx.HTTPStatusError as e:
        return {"status": "failed", "reason": f'"{movie["title"]}": {e.response.text.strip() or e}'}
    except httpx.HTTPError as e:
        return {"status": "failed", "reason": f'"{movie["title"]}": {e}'}
    return {"status": "added", "title": add.json().get("title", movie["title"])}


def sonarr_add_series(cfg, tvdb_id: int, monitored: bool, search: bool, root_folder_path: str, quality_profile_id: int,
                       existing_tvdb_ids: set[int], dry_run: bool = False) -> dict:
    if tvdb_id in existing_tvdb_ids:
        return {"status": "already", "title": None, "tvdbId": tvdb_id}
    try:
        lookup = httpx.get(f"{cfg['url']}/api/{cfg['api']}/series/lookup", params={"term": f"tvdb:{tvdb_id}"},
                            headers={"X-Api-Key": cfg["key"]}, timeout=20)
        lookup.raise_for_status()
        results = lookup.json()
    except httpx.HTTPError as e:
        return {"status": "failed", "reason": f"tvdb {tvdb_id}: lookup failed ({e})"}
    if not results:
        return {"status": "failed", "reason": f"tvdb {tvdb_id}: no Sonarr match"}
    series = results[0]

    series["qualityProfileId"] = quality_profile_id
    series["rootFolderPath"] = root_folder_path
    series["monitored"] = monitored
    series["seasonFolder"] = True
    series["addOptions"] = {
        "monitor": "all" if monitored else "none",
        "searchForMissingEpisodes": search,
        "searchForCutoffUnmetEpisodes": False,
    }

    if dry_run:
        return {"status": "added", "title": series["title"]}

    try:
        add = httpx.post(f"{cfg['url']}/api/{cfg['api']}/series", json=series, headers={"X-Api-Key": cfg["key"]}, timeout=30)
        add.raise_for_status()
    except httpx.HTTPStatusError as e:
        return {"status": "failed", "reason": f'"{series["title"]}": {e.response.text.strip() or e}'}
    except httpx.HTTPError as e:
        return {"status": "failed", "reason": f'"{series["title"]}": {e}'}
    added = add.json()
    return {"status": "added", "title": added.get("title", series["title"])}

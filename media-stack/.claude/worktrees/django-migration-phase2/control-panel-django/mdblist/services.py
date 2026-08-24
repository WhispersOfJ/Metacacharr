"""MDBList -> Radarr/Sonarr integration, ported from the FastAPI-era
control-panel/services/mdblist/router.py (and services/mdblist/sync.py) for
the Django/DRF rewrite.

Owns the tracked-list sync loop: import a list's movies/shows into
Radarr/Sonarr once (import-list), or register a list for the nightly
diff-only sync (track/untrack/tracked), which sync-tick then drives.

Transforms applied vs. the FastAPI-era source:

1. core.responses.fail() (which raised a fastapi.HTTPException) is replaced
   with core.api_base.ServiceError, matching every other ported app.
2. The FastAPI source split this into a private `_run_import()` helper (the
   list-fetch + Radarr/Sonarr-add flow) called from two route handlers
   (`mdblist_import_list`, `mdblist_sync_tick`) plus a separate
   services/mdblist/sync.py module (`record_sync_log`/`recent_sync_logs`,
   SQLAlchemy `Session`-based). Task 12's brief asks for six public
   entry points named after the views (import_list, get_history, track,
   untrack, list_tracked, sync_tick), so that split is folded here: the
   private `_run_import()` helper is kept (sync_tick needs the raw
   Radarr/Sonarr result dict, not import_list()'s wrapped envelope-shaped
   one), and sync.py's two functions become `_record_sync_log()`/
   `get_history()`, now writing/reading `core.models.MDBListSyncLog` via
   the Django ORM instead of SQLAlchemy's `SessionLocal()`.
3. `models.mdblist_tracked_list.MDBListTrackedList` / `models.mdblist_sync_log.
   MDBListSyncLog` (SQLAlchemy) become `core.models.MDBListTrackedList` /
   `core.models.MDBListSyncLog` (Django ORM) - already defined in Phase 1's
   core/models.py, not created here.
4. `_radarr_cfg`/`_sonarr_cfg` validate against RADARR_APPS/SONARR_APPS -
   same behavior, `raise ServiceError(..., status=400)` instead of `fail()`.
"""
import os
import re
from datetime import datetime, timezone

import httpx

from core.api_base import ServiceError
from core.arr_client import (
    ARR_APPS,
    RADARR_APPS,
    SONARR_APPS,
    radarr_add_movie,
    radarr_root_folder_and_profile,
    sonarr_add_series,
    sonarr_root_folder_and_profile,
)
from core.models import MDBListSyncLog, MDBListTrackedList

MDBLIST_URL_RE = re.compile(r"^https://mdblist\.com/lists/([^/]+)/([^/]+)/?$")

HISTORY_PAGE_SIZE = 100


def _radarr_cfg(app: str) -> dict:
    if app not in RADARR_APPS:
        raise ServiceError(f"Unknown Radarr app '{app}' - expected one of {list(RADARR_APPS)}.", status=400)
    return ARR_APPS[app]


def _sonarr_cfg(app: str) -> dict:
    if app not in SONARR_APPS:
        raise ServiceError(f"Unknown Sonarr app '{app}' - expected one of {list(SONARR_APPS)}.", status=400)
    return ARR_APPS[app]


def _run_import(list_url: str, *, app: str = "radarr", sonarr_app: str = "sonarr", monitored: bool = True,
                 search: bool = True, limit: int | None = None, radarr_root_folder: str | None = None,
                 radarr_quality_profile: str | None = None, sonarr_root_folder: str | None = None,
                 sonarr_quality_profile: str | None = None, dry_run: bool = False) -> dict:
    """The import-list flow, callable from both import_list() and
    sync_tick() (the tracked-list scheduler). Returns a plain dict (not the
    ok() envelope) so callers can build their own summary/telemetry from it."""
    key = os.environ.get("MDBLIST_KEY") or None
    if not key:
        raise ServiceError("No MDBList API key found (MDBLIST_KEY not set in .env).", status=500)
    match = MDBLIST_URL_RE.match(list_url.strip().rstrip("/") + "/")
    if not match:
        raise ServiceError(
            "Not a recognized MDBList list URL - expected https://mdblist.com/lists/<user>/<listname>/.",
            status=400,
        )
    username, listname = match.group(1), match.group(2)

    radarr_cfg = _radarr_cfg(app)
    sonarr_cfg = _sonarr_cfg(sonarr_app)

    movies, shows = [], []
    cursor = None
    while True:
        params = {"apikey": key, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        try:
            # api.mdblist.com, not mdblist.com/api - the latter is the
            # website itself and 404s on this endpoint, same landmine
            # documented in the FastAPI-era source.
            r = httpx.get(f"https://api.mdblist.com/lists/{username}/{listname}/items", params=params, timeout=20)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ServiceError(f"MDBList lookup failed: {e}") from e
        data = r.json()
        movies.extend(data.get("movies", []))
        shows.extend(data.get("shows", []))
        if limit and (len(movies) + len(shows)) >= limit:
            break
        pagination = data.get("pagination", {})
        cursor = pagination.get("next_cursor")
        if not pagination.get("has_more") or not cursor:
            break

    if not movies and not shows:
        raise ServiceError(
            f'No items found in MDBList list "{username}/{listname}" (or it is private/doesn\'t exist).',
            status=404,
        )

    result = {"radarr": None, "sonarr": None}

    if movies:
        try:
            library = httpx.get(f"{radarr_cfg['url']}/api/{radarr_cfg['api']}/movie",
                                 headers={"X-Api-Key": radarr_cfg["key"]}, timeout=30)
            library.raise_for_status()
        except httpx.HTTPError as e:
            raise ServiceError(f"Couldn't read {radarr_cfg['label']}'s library: {e}") from e
        existing_tmdb_ids = {m["tmdbId"] for m in library.json()}
        radarr_root_folder_path, radarr_quality_profile_id = radarr_root_folder_and_profile(
            radarr_cfg, radarr_root_folder, radarr_quality_profile)

        added, already, failed = [], [], []
        for m in movies:
            tmdb_id = m.get("ids", {}).get("tmdb")
            if not tmdb_id:
                failed.append(f'"{m.get("title")}": no TMDb id from MDBList')
                continue
            r = radarr_add_movie(radarr_cfg, tmdb_id, monitored, search, radarr_root_folder_path,
                                  radarr_quality_profile_id, existing_tmdb_ids, dry_run=dry_run)
            (added if r["status"] == "added" else already if r["status"] == "already" else failed).append(
                r.get("title") or r.get("reason") or tmdb_id)
        result["radarr"] = {"added": added, "alreadyCount": len(already), "failed": failed}

    if shows:
        try:
            library = httpx.get(f"{sonarr_cfg['url']}/api/{sonarr_cfg['api']}/series",
                                 headers={"X-Api-Key": sonarr_cfg["key"]}, timeout=30)
            library.raise_for_status()
        except httpx.HTTPError as e:
            raise ServiceError(f"Couldn't read {sonarr_cfg['label']}'s library: {e}") from e
        existing_tvdb_ids = {s["tvdbId"] for s in library.json()}
        sonarr_root_folder_path, sonarr_quality_profile_id = sonarr_root_folder_and_profile(
            sonarr_cfg, sonarr_root_folder, sonarr_quality_profile)

        added, already, failed = [], [], []
        for s in shows:
            tvdb_id = s.get("ids", {}).get("tvdb")
            if not tvdb_id:
                failed.append(f'"{s.get("title")}": no TVDb id from MDBList')
                continue
            r = sonarr_add_series(sonarr_cfg, tvdb_id, monitored, search, sonarr_root_folder_path,
                                   sonarr_quality_profile_id, existing_tvdb_ids, dry_run=dry_run)
            (added if r["status"] == "added" else already if r["status"] == "already" else failed).append(
                r.get("title") or r.get("reason") or tvdb_id)
        result["sonarr"] = {"added": added, "alreadyCount": len(already), "failed": failed}

    return result


def _record_sync_log(list_url: str, *, radarr_added: int = 0, radarr_already: int = 0, radarr_failed: int = 0,
                      sonarr_added: int = 0, sonarr_already: int = 0, sonarr_failed: int = 0,
                      error_detail: str | None = None) -> None:
    """Mirrors services/mdblist/sync.py's record_sync_log, now via the ORM."""
    MDBListSyncLog.objects.create(
        list_url=list_url, radarr_added=radarr_added, radarr_already=radarr_already, radarr_failed=radarr_failed,
        sonarr_added=sonarr_added, sonarr_already=sonarr_already, sonarr_failed=sonarr_failed,
        error_detail=error_detail,
    )


def _result_counts(result: dict) -> dict:
    radarr = result.get("radarr")
    sonarr = result.get("sonarr")
    return {
        "radarr_added": len(radarr["added"]) if radarr else 0,
        "radarr_already": radarr["alreadyCount"] if radarr else 0,
        "radarr_failed": len(radarr["failed"]) if radarr else 0,
        "sonarr_added": len(sonarr["added"]) if sonarr else 0,
        "sonarr_already": sonarr["alreadyCount"] if sonarr else 0,
        "sonarr_failed": len(sonarr["failed"]) if sonarr else 0,
    }


def import_list(list_url: str, *, app: str = "radarr", sonarr_app: str = "sonarr", monitored: bool = True,
                 search: bool = True, limit: int | None = None, radarr_root_folder: str | None = None,
                 radarr_quality_profile: str | None = None, sonarr_root_folder: str | None = None,
                 sonarr_quality_profile: str | None = None, dry_run: bool = False) -> dict:
    """POST /api/v2/mdblist/import-list - one-off (or manually re-triggered)
    import of an MDBList list's movies/shows into Radarr/Sonarr."""
    result = _run_import(
        list_url, app=app, sonarr_app=sonarr_app, monitored=monitored, search=search, limit=limit,
        radarr_root_folder=radarr_root_folder, radarr_quality_profile=radarr_quality_profile,
        sonarr_root_folder=sonarr_root_folder, sonarr_quality_profile=sonarr_quality_profile, dry_run=dry_run,
    )
    _record_sync_log(list_url, **_result_counts(result))

    verb = "would be added" if dry_run else "added"
    parts = []
    if result["radarr"] is not None:
        parts.append(f"Radarr: {len(result['radarr']['added'])} {verb}, {result['radarr']['alreadyCount']} already present, "
                      f"{len(result['radarr']['failed'])} failed")
    if result["sonarr"] is not None:
        parts.append(f"Sonarr: {len(result['sonarr']['added'])} {verb}, {result['sonarr']['alreadyCount']} already present, "
                      f"{len(result['sonarr']['failed'])} failed")
    return {
        "message": "; ".join(parts),
        "radarr": result["radarr"],
        "sonarr": result["sonarr"],
        "dryRun": dry_run,
    }


def get_history() -> dict:
    """GET /api/v2/mdblist/history - recent sync-log rows, newest first."""
    rows = MDBListSyncLog.objects.order_by("-id")[:HISTORY_PAGE_SIZE]
    runs = [
        {
            "listUrl": r.list_url,
            "runAt": r.run_at.isoformat() if r.run_at else None,
            "radarrAdded": r.radarr_added,
            "radarrAlready": r.radarr_already,
            "radarrFailed": r.radarr_failed,
            "sonarrAdded": r.sonarr_added,
            "sonarrAlready": r.sonarr_already,
            "sonarrFailed": r.sonarr_failed,
            "errorDetail": r.error_detail,
        }
        for r in rows
    ]
    return {"message": f"{len(runs)} recent sync run(s).", "runs": runs}


def track(url: str, *, app: str = "radarr", sonarr_app: str = "sonarr", label: str | None = None,
          radarr_root_folder: str | None = None, radarr_quality_profile: str | None = None,
          sonarr_root_folder: str | None = None, sonarr_quality_profile: str | None = None) -> dict:
    """POST /api/v2/mdblist/track - register a list for the nightly
    diff-only sync driven by sync_tick()."""
    _radarr_cfg(app)
    _sonarr_cfg(sonarr_app)
    existing = MDBListTrackedList.objects.filter(url=url).first()
    if existing is not None:
        raise ServiceError(f"'{url}' is already tracked (id {existing.id}).", status=409)
    row = MDBListTrackedList.objects.create(
        url=url, app=app, sonarr_app=sonarr_app, label=label,
        radarr_root_folder=radarr_root_folder, radarr_quality_profile=radarr_quality_profile,
        sonarr_root_folder=sonarr_root_folder, sonarr_quality_profile=sonarr_quality_profile,
    )
    return {"message": f"Now tracking '{url}'.", "id": row.id}


def untrack(url: str) -> dict:
    """POST /api/v2/mdblist/untrack - stop syncing a tracked list."""
    row = MDBListTrackedList.objects.filter(url=url).first()
    if row is None:
        raise ServiceError(f"'{url}' isn't tracked.", status=404)
    row.delete()
    return {"message": f"Stopped tracking '{url}'."}


def list_tracked() -> dict:
    """GET /api/v2/mdblist/tracked - every list currently registered for sync."""
    rows = MDBListTrackedList.objects.order_by("created_at")
    lists = [
        {"id": r.id, "url": r.url, "app": r.app, "sonarrApp": r.sonarr_app, "label": r.label,
         "lastSyncedAt": r.last_synced_at.isoformat() if r.last_synced_at else None}
        for r in rows
    ]
    return {"message": f"{len(lists)} tracked list(s).", "lists": lists}


def sync_tick() -> dict:
    """POST /api/v2/mdblist/sync-tick - run every tracked list's import,
    once each, collecting per-row errors without aborting the loop (a
    failure on one list must not stop the rest from syncing)."""
    tracked = list(MDBListTrackedList.objects.all())
    results = []
    for row in tracked:
        try:
            result = _run_import(
                row.url, app=row.app, sonarr_app=row.sonarr_app, radarr_root_folder=row.radarr_root_folder,
                radarr_quality_profile=row.radarr_quality_profile, sonarr_root_folder=row.sonarr_root_folder,
                sonarr_quality_profile=row.sonarr_quality_profile,
            )
            _record_sync_log(row.url, **_result_counts(result))
            row.last_synced_at = datetime.now(timezone.utc)
            row.save(update_fields=["last_synced_at"])
            results.append({
                "url": row.url,
                "radarrAdded": result["radarr"]["added"] if result["radarr"] else [],
                "sonarrAdded": result["sonarr"]["added"] if result["sonarr"] else [],
            })
        except Exception as e:
            _record_sync_log(row.url, error_detail=str(e))
            results.append({"url": row.url, "radarrAdded": [], "sonarrAdded": [], "error": str(e)})
    return {"message": f"Synced {len(tracked)} tracked list(s).", "results": results}

"""MDBList -> Radarr/Sonarr integration routes. Owns every /api/mdblist/*
route. Moved out of services/arr/router.py (2026-08-08) once this became
a first-class integration spanning both Radarr and Sonarr with anime-app
support and a tracked-list nightly sync, mirroring services/letterboxd/.
"""
import os
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.arr_client import (
    ARR_APPS,
    RADARR_APPS,
    SONARR_APPS,
    radarr_add_movie,
    radarr_root_folder_and_profile,
    sonarr_add_series,
    sonarr_root_folder_and_profile,
)
from core.db import SessionLocal
from core.responses import fail, ok
from core.security import current_user, current_user_or_service
from models.mdblist_tracked_list import MDBListTrackedList
from services.mdblist.sync import record_sync_log, recent_sync_logs

router = APIRouter(tags=["mdblist"])

SERVICE_META = {"label": "MDBList", "health_check": None}

MDBLIST_URL_RE = re.compile(r"^https://mdblist\.com/lists/([^/]+)/([^/]+)/?$")


def _radarr_cfg(app: str) -> dict:
    if app not in RADARR_APPS:
        fail(f"Unknown Radarr app '{app}' - expected one of {list(RADARR_APPS)}.", status_code=400)
    return ARR_APPS[app]


def _sonarr_cfg(app: str) -> dict:
    if app not in SONARR_APPS:
        fail(f"Unknown Sonarr app '{app}' - expected one of {list(SONARR_APPS)}.", status_code=400)
    return ARR_APPS[app]


class MDBListImportRequest(BaseModel):
    list_url: str
    app: str = "radarr"
    sonarr_app: str = "sonarr"
    monitored: bool = True
    search: bool = True
    limit: int | None = None
    radarr_root_folder: str | None = None
    radarr_quality_profile: str | None = None
    sonarr_root_folder: str | None = None
    sonarr_quality_profile: str | None = None
    dry_run: bool = False


def _run_import(list_url: str, *, app: str = "radarr", sonarr_app: str = "sonarr", monitored: bool = True,
                 search: bool = True, limit: int | None = None, radarr_root_folder: str | None = None,
                 radarr_quality_profile: str | None = None, sonarr_root_folder: str | None = None,
                 sonarr_quality_profile: str | None = None, dry_run: bool = False) -> dict:
    """The import-list flow, callable from both that HTTP route and
    sync-tick (the tracked-list scheduler) - mirrors
    services/letterboxd/router.py's _run_list_sync split. Returns a plain
    dict (not the ok() envelope) so callers can build their own
    summary/telemetry from it."""
    key = os.environ.get("MDBLIST_KEY") or None
    if not key:
        fail("No MDBList API key found (MDBLIST_KEY not set in .env).", status_code=500)
    match = MDBLIST_URL_RE.match(list_url.strip().rstrip("/") + "/")
    if not match:
        fail("Not a recognized MDBList list URL - expected https://mdblist.com/lists/<user>/<listname>/.", status_code=400)
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
            # website itself (404s on every /api/lists/<user>/<slug>/items
            # call, confirmed live) and was a pre-existing bug carried over
            # unnoticed from the original services/arr/router.py version of
            # this function - real API lives on its own subdomain.
            r = httpx.get(f"https://api.mdblist.com/lists/{username}/{listname}/items", params=params, timeout=20)
            r.raise_for_status()
        except httpx.HTTPError as e:
            fail(f"MDBList lookup failed: {e}")
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
        fail(f'No items found in MDBList list "{username}/{listname}" (or it is private/doesn\'t exist).', status_code=404)

    result = {"radarr": None, "sonarr": None}

    if movies:
        try:
            library = httpx.get(f"{radarr_cfg['url']}/api/{radarr_cfg['api']}/movie",
                                 headers={"X-Api-Key": radarr_cfg["key"]}, timeout=30)
            library.raise_for_status()
        except httpx.HTTPError as e:
            fail(f"Couldn't read {radarr_cfg['label']}'s library: {e}")
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
            fail(f"Couldn't read {sonarr_cfg['label']}'s library: {e}")
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


@router.post("/api/mdblist/import-list")
# current_user_or_service, not current_user: stack-mdblist-radarr-list.fish
# calls this unattended via __stack_api's service key (same documented
# automation exception as services/letterboxd/router.py's routes).
def mdblist_import_list(payload: MDBListImportRequest, _=Depends(current_user_or_service)):
    result = _run_import(
        payload.list_url, app=payload.app, sonarr_app=payload.sonarr_app, monitored=payload.monitored,
        search=payload.search, limit=payload.limit, radarr_root_folder=payload.radarr_root_folder,
        radarr_quality_profile=payload.radarr_quality_profile, sonarr_root_folder=payload.sonarr_root_folder,
        sonarr_quality_profile=payload.sonarr_quality_profile, dry_run=payload.dry_run,
    )
    db = SessionLocal()
    try:
        record_sync_log(
            db, payload.list_url,
            radarr_added=len(result["radarr"]["added"]) if result["radarr"] else 0,
            radarr_already=result["radarr"]["alreadyCount"] if result["radarr"] else 0,
            radarr_failed=len(result["radarr"]["failed"]) if result["radarr"] else 0,
            sonarr_added=len(result["sonarr"]["added"]) if result["sonarr"] else 0,
            sonarr_already=result["sonarr"]["alreadyCount"] if result["sonarr"] else 0,
            sonarr_failed=len(result["sonarr"]["failed"]) if result["sonarr"] else 0,
        )
    finally:
        db.close()

    verb = "would be added" if payload.dry_run else "added"
    parts = []
    if result["radarr"] is not None:
        parts.append(f"Radarr: {len(result['radarr']['added'])} {verb}, {result['radarr']['alreadyCount']} already present, "
                      f"{len(result['radarr']['failed'])} failed")
    if result["sonarr"] is not None:
        parts.append(f"Sonarr: {len(result['sonarr']['added'])} {verb}, {result['sonarr']['alreadyCount']} already present, "
                      f"{len(result['sonarr']['failed'])} failed")
    return ok("; ".join(parts), radarr=result["radarr"], sonarr=result["sonarr"], dryRun=payload.dry_run)


@router.get("/api/mdblist/history")
def mdblist_history(_=Depends(current_user_or_service)):
    db = SessionLocal()
    try:
        runs = recent_sync_logs(db)
    finally:
        db.close()
    return ok(f"{len(runs)} recent sync run(s).", runs=runs)


class TrackRequest(BaseModel):
    url: str
    app: str = "radarr"
    sonarr_app: str = "sonarr"
    label: str | None = None
    radarr_root_folder: str | None = None
    radarr_quality_profile: str | None = None
    sonarr_root_folder: str | None = None
    sonarr_quality_profile: str | None = None


@router.post("/api/mdblist/track")
def mdblist_track(payload: TrackRequest, _=Depends(current_user)):
    _radarr_cfg(payload.app)
    _sonarr_cfg(payload.sonarr_app)
    db = SessionLocal()
    try:
        existing = db.query(MDBListTrackedList).filter_by(url=payload.url).first()
        if existing is not None:
            fail(f"'{payload.url}' is already tracked (id {existing.id}).", status_code=409)
        row = MDBListTrackedList(
            url=payload.url, app=payload.app, sonarr_app=payload.sonarr_app, label=payload.label,
            radarr_root_folder=payload.radarr_root_folder, radarr_quality_profile=payload.radarr_quality_profile,
            sonarr_root_folder=payload.sonarr_root_folder, sonarr_quality_profile=payload.sonarr_quality_profile,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return ok(f"Now tracking '{payload.url}'.", id=row.id)
    finally:
        db.close()


class UntrackRequest(BaseModel):
    url: str


@router.post("/api/mdblist/untrack")
def mdblist_untrack(payload: UntrackRequest, _=Depends(current_user)):
    db = SessionLocal()
    try:
        row = db.query(MDBListTrackedList).filter_by(url=payload.url).first()
        if row is None:
            fail(f"'{payload.url}' isn't tracked.", status_code=404)
        db.delete(row)
        db.commit()
        return ok(f"Stopped tracking '{payload.url}'.")
    finally:
        db.close()


@router.get("/api/mdblist/tracked")
def mdblist_tracked(_=Depends(current_user_or_service)):
    db = SessionLocal()
    try:
        rows = db.query(MDBListTrackedList).order_by(MDBListTrackedList.created_at).all()
        lists = [
            {"id": r.id, "url": r.url, "app": r.app, "sonarrApp": r.sonarr_app, "label": r.label,
             "lastSyncedAt": r.last_synced_at.isoformat() if r.last_synced_at else None}
            for r in rows
        ]
        return ok(f"{len(lists)} tracked list(s).", lists=lists)
    finally:
        db.close()


@router.post("/api/mdblist/sync-tick")
# current_user_or_service, not current_user: scripts/mdblist-sync.py calls
# this unattended via the CONTROL_PANEL_SERVICE_API_KEY, same documented
# automation exception as services/letterboxd/router.py's sync-tick.
def mdblist_sync_tick(_=Depends(current_user_or_service)):
    db = SessionLocal()
    try:
        tracked = db.query(MDBListTrackedList).all()
        results = []
        for row in tracked:
            try:
                result = _run_import(
                    row.url, app=row.app, sonarr_app=row.sonarr_app, radarr_root_folder=row.radarr_root_folder,
                    radarr_quality_profile=row.radarr_quality_profile, sonarr_root_folder=row.sonarr_root_folder,
                    sonarr_quality_profile=row.sonarr_quality_profile,
                )
                record_sync_log(
                    db, row.url,
                    radarr_added=len(result["radarr"]["added"]) if result["radarr"] else 0,
                    radarr_already=result["radarr"]["alreadyCount"] if result["radarr"] else 0,
                    radarr_failed=len(result["radarr"]["failed"]) if result["radarr"] else 0,
                    sonarr_added=len(result["sonarr"]["added"]) if result["sonarr"] else 0,
                    sonarr_already=result["sonarr"]["alreadyCount"] if result["sonarr"] else 0,
                    sonarr_failed=len(result["sonarr"]["failed"]) if result["sonarr"] else 0,
                )
                row.last_synced_at = datetime.now(timezone.utc)
                db.commit()
                results.append({
                    "url": row.url,
                    "radarrAdded": result["radarr"]["added"] if result["radarr"] else [],
                    "sonarrAdded": result["sonarr"]["added"] if result["sonarr"] else [],
                })
            except Exception as e:
                record_sync_log(db, row.url, error_detail=str(e))
                results.append({"url": row.url, "radarrAdded": [], "sonarrAdded": [], "error": str(e)})
        return ok(f"Synced {len(tracked)} tracked list(s).", results=results)
    finally:
        db.close()

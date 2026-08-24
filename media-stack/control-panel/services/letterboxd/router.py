"""Letterboxd -> Radarr/Sonarr integration routes. Owns every
/api/arr/*letterboxd* and /api/arr/letterboxd/* route - the single-film
and list/watchlist/filmography/collection adds (originally in
services/radarr/router.py, moved here 2026-08-06 once this became a
first-class integration spanning both Radarr and Sonarr).
"""
import json as _json
import os
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.arr_client import (
    ARR_APPS,
    RADARR_APPS,
    SONARR_APPS,
    radarr_add_movie,
    radarr_ensure_tags,
    radarr_quality_profile_id_by_name,
    radarr_root_folder_and_profile,
    sonarr_add_series,
    sonarr_root_folder_and_profile,
)
from core.db import SessionLocal
from core.responses import fail, ok
from core.security import current_user, current_user_or_service
from models.letterboxd_cache import LetterboxdTmdbCache
from models.letterboxd_tracked_list import LetterboxdTrackedList
from services.letterboxd.cache import resolve_tmdb_ids, resolve_tv_crossovers
from services.letterboxd.sync import record_sync_log, recent_sync_logs
from services.letterboxd.scraping import (
    LETTERBOXD_DISALLOWED_RE,
    LETTERBOXD_GRID_RE,
    LETTERBOXD_ITEM_SLUG_RE,
    LETTERBOXD_LIST_PAGE_RE,
    LETTERBOXD_TMDB_RE,
    fetch_page,
    fetch_page_or_none,
    scrape_slugs_with_ratings,
    scrape_tags,
)

router = APIRouter(tags=["letterboxd"])

SERVICE_META = {"label": "Letterboxd", "health_check": None}

METACACHE_URL = os.getenv("METACACHE_URL", "http://metacache:8765").rstrip("/")
METACACHE_API_KEY = os.getenv("METACACHE_API_KEY", "")


def _radarr_cfg(app: str) -> dict:
    if app not in RADARR_APPS:
        fail(f"Unknown Radarr app '{app}' - expected one of {list(RADARR_APPS)}.", status_code=400)
    return ARR_APPS[app]


def _sonarr_cfg(app: str) -> dict:
    if app not in SONARR_APPS:
        fail(f"Unknown Sonarr app '{app}' - expected one of {list(SONARR_APPS)}.", status_code=400)
    return ARR_APPS[app]


class LetterboxdAddRequest(BaseModel):
    url: str
    app: str = "radarr"
    monitored: bool = True
    search: bool = True
    root_folder: str | None = None
    quality_profile: str | None = None
    dry_run: bool = False


@router.post("/api/arr/radarr/add-from-letterboxd")
# current_user_or_service, not current_user: stack-letterboxd-radarr.fish
# calls this unattended via __stack_api's service key (2026-08-06, carried
# over unchanged from services/radarr/router.py).
def radarr_add_from_letterboxd(payload: LetterboxdAddRequest, _=Depends(current_user_or_service)):
    cfg = _radarr_cfg(payload.app)
    url = payload.url.strip()
    if "letterboxd.com/film/" not in url:
        fail("Not a Letterboxd film URL - expected something like https://letterboxd.com/film/<slug>/.", status_code=400)
    page_text = fetch_page(url)
    match = LETTERBOXD_TMDB_RE.search(page_text)
    if not match:
        fail("No TMDb link found on that Letterboxd page - it may be unmatched to TMDb.", status_code=404)
    tmdb_id = int(match.group(1))

    try:
        existing = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie", params={"tmdbId": tmdb_id},
                              headers={"X-Api-Key": cfg["key"]}, timeout=20)
        existing.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Couldn't check whether Radarr already has this movie: {e}")
    existing_movies = existing.json()
    if existing_movies:
        m = existing_movies[0]
        return ok(f'"{m["title"]}" ({m.get("year")}) is already in Radarr.', tmdbId=tmdb_id, radarrId=m["id"], alreadyAdded=True)

    try:
        lookup = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie/lookup/tmdb", params={"tmdbId": tmdb_id},
                            headers={"X-Api-Key": cfg["key"]}, timeout=20)
        lookup.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Radarr's TMDb lookup failed: {e}")
    movie = lookup.json()
    if not movie or not movie.get("title"):
        fail(f"Radarr has no TMDb match for id {tmdb_id}.", status_code=404)

    root_folder_path, quality_profile_id = radarr_root_folder_and_profile(cfg, payload.root_folder, payload.quality_profile)
    movie["qualityProfileId"] = quality_profile_id
    movie["rootFolderPath"] = root_folder_path
    movie["monitored"] = payload.monitored
    movie["addOptions"] = {"searchForMovie": payload.search}

    if payload.dry_run:
        return ok(f'Would add "{movie["title"]}" ({movie.get("year")}) to Radarr - dry run, nothing written.',
                   tmdbId=tmdb_id, dryRun=True)

    try:
        add = httpx.post(f"{cfg['url']}/api/{cfg['api']}/movie", json=movie, headers={"X-Api-Key": cfg["key"]}, timeout=30)
        add.raise_for_status()
    except httpx.HTTPStatusError as e:
        fail(f"Radarr rejected the add: {e.response.text.strip() or e}")
    except httpx.HTTPError as e:
        fail(f"Radarr add failed: {e}")

    added = add.json()
    return ok(f'Added "{added.get("title", movie["title"])}" ({added.get("year", movie.get("year"))}) to Radarr.',
              tmdbId=tmdb_id, radarrId=added.get("id"))


class LetterboxdListAddRequest(BaseModel):
    url: str
    app: str = "radarr"
    monitored: bool = True
    search: bool = True
    root_folder: str | None = None
    quality_profile: str | None = None
    limit: int | None = None
    dry_run: bool = False
    rating_quality_map: dict[str, str] | None = None
    tags_as_radarr_tags: bool = False
    sonarr_crossover: bool = False
    sonarr_app: str = "sonarr"


def _run_list_sync(url: str, *, app: str = "radarr", monitored: bool = True, search: bool = True,
                    root_folder: str | None = None, quality_profile: str | None = None, limit: int | None = None,
                    dry_run: bool = False, rating_quality_map: dict[str, str] | None = None,
                    tags_as_radarr_tags: bool = False, sonarr_crossover: bool = False,
                    sonarr_app: str = "sonarr") -> dict:
    """The add-from-letterboxd-list flow, callable from both that HTTP
    route and sync-tick (Task 8's tracked-list scheduler) - both need the
    identical scrape/resolve/add logic, just with the request payload's
    fields coming from different sources (a LetterboxdListAddRequest body
    vs a LetterboxdTrackedList row). Returns a plain dict (not the ok()
    envelope) so callers can build their own summary/telemetry from it -
    added, already, failed, unmatched, tvAdded, tvAlready, tvFailed,
    matched."""
    cfg = _radarr_cfg(app)
    base_url = url.strip().rstrip("/")
    if LETTERBOXD_DISALLOWED_RE.search(base_url + "/"):
        fail(
            "That URL includes a sort/filter option Letterboxd's robots.txt disallows scraping "
            "(by/, genre/, decade/, year/, this/week/, size/large/, etc). Use the plain, unsorted URL.",
            status_code=400,
        )
    if not LETTERBOXD_GRID_RE.match(base_url):
        fail(
            "Not a recognized Letterboxd list/watchlist/filmography/collection URL - expected something like "
            "https://letterboxd.com/<user>/list/<slug>/, https://letterboxd.com/<user>/watchlist/, "
            "https://letterboxd.com/<user>/films/, https://letterboxd.com/actor/<slug>/, "
            "https://letterboxd.com/films/in/<collection>/, or https://letterboxd.com/films/popular/.",
            status_code=400,
        )

    first_page = fetch_page(base_url + "/")
    last_page = min(max((int(n) for n in LETTERBOXD_LIST_PAGE_RE.findall(first_page)), default=1), 10)

    if rating_quality_map:
        slug_ratings: dict[str, int | None] = dict(scrape_slugs_with_ratings(first_page))
        for page_num in range(2, last_page + 1):
            page_html = fetch_page_or_none(f"{base_url}/page/{page_num}/")
            if page_html is None:
                break
            slug_ratings.update(dict(scrape_slugs_with_ratings(page_html)))
            time.sleep(0.2)
        slugs = list(slug_ratings.keys())
    else:
        slug_ratings = {}
        slugs = list(dict.fromkeys(LETTERBOXD_ITEM_SLUG_RE.findall(first_page)))
        for page_num in range(2, last_page + 1):
            page_html = fetch_page_or_none(f"{base_url}/page/{page_num}/")
            if page_html is None:
                break
            slugs.extend(LETTERBOXD_ITEM_SLUG_RE.findall(page_html))
            time.sleep(0.2)
        slugs = list(dict.fromkeys(slugs))
    if not slugs:
        fail(
            "No films found on that Letterboxd page. Some pages (e.g. /films/popular/) render their "
            "poster grid client-side in JS and have no scrapeable server-rendered film data.",
            status_code=404,
        )

    slug_limit = min(limit, 720) if limit else 720
    slugs = slugs[:slug_limit]

    db = SessionLocal()
    try:
        tmdb_ids, unmatched = resolve_tmdb_ids(db, slugs)
    finally:
        db.close()
    tmdb_ids = list(dict.fromkeys(tmdb_ids))
    print(f"letterboxd-list: resolved {len(tmdb_ids)} tmdb id(s), {len(unmatched)} unmatched, out of {len(slugs)} slug(s)")

    tv_added, tv_already, tv_failed = [], [], []
    if sonarr_crossover and unmatched:
        sonarr_cfg = _sonarr_cfg(sonarr_app)
        db = SessionLocal()
        try:
            tv_matches, unmatched = resolve_tv_crossovers(db, unmatched)
        finally:
            db.close()
        if tv_matches:
            try:
                sonarr_library = httpx.get(f"{sonarr_cfg['url']}/api/{sonarr_cfg['api']}/series",
                                            headers={"X-Api-Key": sonarr_cfg["key"]}, timeout=30)
                sonarr_library.raise_for_status()
            except httpx.HTTPError as e:
                fail(f"Couldn't read Sonarr's library: {e}")
            existing_tvdb_ids = {s["tvdbId"] for s in sonarr_library.json()}
            sonarr_root_folder_path, sonarr_quality_profile_id = sonarr_root_folder_and_profile(sonarr_cfg, None, None)
            for tv_match in tv_matches:
                result = sonarr_add_series(sonarr_cfg, tv_match["tvdb_id"], monitored, search,
                                            sonarr_root_folder_path, sonarr_quality_profile_id, existing_tvdb_ids,
                                            dry_run=dry_run)
                if result["status"] == "already":
                    tv_already.append(tv_match["title"])
                elif result["status"] == "added":
                    tv_added.append(result["title"])
                else:
                    tv_failed.append(result["reason"])

    try:
        library = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie", headers={"X-Api-Key": cfg["key"]}, timeout=30)
        library.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Couldn't read Radarr's library: {e}")
    existing_tmdb_ids = {m["tmdbId"] for m in library.json()}

    root_folder_path, quality_profile_id = radarr_root_folder_and_profile(cfg, root_folder, quality_profile)

    rating_profile_ids: dict[str, int] = {}
    if rating_quality_map:
        for rating_str, profile_name in rating_quality_map.items():
            pid = radarr_quality_profile_id_by_name(cfg, profile_name)
            if pid is not None:
                rating_profile_ids[rating_str] = pid

    # slug -> resolved tmdb_id, needed to look back up a film's rating (for
    # quality-profile mapping) or its owner-page tags - resolve_tmdb_ids
    # only returns the ids, not which slug produced which id, so track
    # that mapping here too whenever either feature needs it.
    slug_to_tmdb: dict[str, int] = {}
    if rating_quality_map or tags_as_radarr_tags:
        db = SessionLocal()
        try:
            for slug in slugs:
                cached = db.query(LetterboxdTmdbCache).filter_by(slug=slug).first()
                if cached and cached.tmdb_id is not None:
                    slug_to_tmdb[slug] = cached.tmdb_id
        finally:
            db.close()

    slug_to_tag_ids: dict[int, list[int]] = {}
    if tags_as_radarr_tags:
        # base_url is like https://letterboxd.com/<user>/list/<slug> or
        # https://letterboxd.com/<user>/watchlist - the owner segment is
        # always the first path component, valid for every URL shape
        # LETTERBOXD_GRID_RE allows except the bare films/popular/collection
        # ones (which have no single owner - tags_as_radarr_tags on those
        # scrapes zero tags, not an error, since a film with no scraped
        # tags is a normal outcome for this feature).
        owner = base_url.replace("https://letterboxd.com/", "").split("/")[0]
        for slug, tmdb_id in slug_to_tmdb.items():
            user_film_html = fetch_page_or_none(f"https://letterboxd.com/{owner}/film/{slug}/")
            if not user_film_html:
                continue
            tag_names = scrape_tags(user_film_html)
            if tag_names:
                slug_to_tag_ids[tmdb_id] = radarr_ensure_tags(cfg, tag_names)
            time.sleep(0.2)

    added, already, failed = [], [], []
    total_movies = len(tmdb_ids)
    for i, tmdb_id in enumerate(tmdb_ids, 1):
        film_quality_profile_id = quality_profile_id
        if rating_quality_map:
            slug = next((s for s, t in slug_to_tmdb.items() if t == tmdb_id), None)
            rating = slug_ratings.get(slug) if slug else None
            if rating is not None and str(rating) in rating_profile_ids:
                film_quality_profile_id = rating_profile_ids[str(rating)]
        result = radarr_add_movie(cfg, tmdb_id, monitored, search, root_folder_path, film_quality_profile_id,
                                   existing_tmdb_ids, dry_run=dry_run, tag_ids=slug_to_tag_ids.get(tmdb_id))
        if result["status"] == "already":
            already.append(tmdb_id)
            print(f"letterboxd-list: [{i}/{total_movies}] tmdb {tmdb_id} already in Radarr")
        elif result["status"] == "added":
            added.append(result["title"])
            verb = "would add" if dry_run else "added"
            print(f'letterboxd-list: [{i}/{total_movies}] {verb} "{result["title"]}"')
        else:
            failed.append(result["reason"])
            print(f"letterboxd-list: [{i}/{total_movies}] failed - {result['reason']}")

    # Trigger Metacache warm for newly added movies (non-blocking)
    if added and not dry_run:
        try:
            headers = {"Content-Type": "application/json"}
            if METACACHE_API_KEY:
                headers["Authorization"] = f"Bearer {METACACHE_API_KEY}"
            httpx.post(f"{METACACHE_URL}/warm/movies", headers=headers, timeout=5.0)
        except Exception as e:
            print(f"metacache warm trigger failed: {e}", file=__import__('sys').stderr)

    return {
        "added": added, "already": already, "failed": failed, "unmatched": unmatched,
        "tvAdded": tv_added, "tvAlready": tv_already, "tvFailed": tv_failed,
        "matched": len(tmdb_ids),
    }


@router.post("/api/arr/radarr/add-from-letterboxd-list")
# current_user_or_service, not current_user: stack-letterboxd-radarr-list.fish
# calls this unattended via __stack_api's service key (2026-08-06, carried
# over unchanged from services/radarr/router.py).
def radarr_add_from_letterboxd_list(payload: LetterboxdListAddRequest, _=Depends(current_user_or_service)):
    result = _run_list_sync(
        payload.url, app=payload.app, monitored=payload.monitored, search=payload.search,
        root_folder=payload.root_folder, quality_profile=payload.quality_profile, limit=payload.limit,
        dry_run=payload.dry_run, rating_quality_map=payload.rating_quality_map,
        tags_as_radarr_tags=payload.tags_as_radarr_tags, sonarr_crossover=payload.sonarr_crossover,
        sonarr_app=payload.sonarr_app,
    )
    db = SessionLocal()
    try:
        record_sync_log(
            db, payload.url, matched=result["matched"], unmatched=len(result["unmatched"]),
            added=len(result["added"]), already=len(result["already"]), failed=len(result["failed"]),
            tv_crossover=len(result["tvAdded"]) + len(result["tvAlready"]),
        )
    finally:
        db.close()

    verb = "would be added" if payload.dry_run else "added"
    summary = f"{len(result['added'])} {verb}, {len(result['already'])} already in Radarr, {len(result['failed'])} failed"
    if result["unmatched"]:
        summary += f", {len(result['unmatched'])} had no TMDb match"
    if result["tvAdded"] or result["tvAlready"] or result["tvFailed"]:
        summary += (f"; {len(result['tvAdded'])} TV crossover {verb} to Sonarr, "
                     f"{len(result['tvAlready'])} already in Sonarr, {len(result['tvFailed'])} failed")
    return ok(summary, added=result["added"], alreadyCount=len(result["already"]), failed=result["failed"],
              unmatched=result["unmatched"], dryRun=payload.dry_run, tvCrossoverAdded=result["tvAdded"],
              tvCrossoverAlready=result["tvAlready"], tvCrossoverFailed=result["tvFailed"],
              tvCrossoverCount=len(result["tvAdded"]) + len(result["tvAlready"]))


@router.get("/api/arr/letterboxd/history")
def letterboxd_history(_=Depends(current_user_or_service)):
    db = SessionLocal()
    try:
        runs = recent_sync_logs(db)
    finally:
        db.close()
    return ok(f"{len(runs)} recent sync run(s).", runs=runs)


class TrackRequest(BaseModel):
    url: str
    app: str = "radarr"
    label: str | None = None
    root_folder: str | None = None
    quality_profile: str | None = None
    rating_quality_map: dict[str, str] | None = None
    tags_as_radarr_tags: bool = False
    sonarr_app: str = "sonarr"


@router.post("/api/arr/letterboxd/track")
def letterboxd_track(payload: TrackRequest, _=Depends(current_user)):
    _radarr_cfg(payload.app)
    _sonarr_cfg(payload.sonarr_app)
    db = SessionLocal()
    try:
        existing = db.query(LetterboxdTrackedList).filter_by(url=payload.url).first()
        if existing is not None:
            fail(f"'{payload.url}' is already tracked (id {existing.id}).", status_code=409)
        row = LetterboxdTrackedList(
            url=payload.url, app=payload.app, label=payload.label, root_folder=payload.root_folder,
            quality_profile=payload.quality_profile, tags_as_radarr_tags=payload.tags_as_radarr_tags,
            sonarr_app=payload.sonarr_app,
            rating_quality_map_json=_json.dumps(payload.rating_quality_map) if payload.rating_quality_map else None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return ok(f"Now tracking '{payload.url}'.", id=row.id)
    finally:
        db.close()


class UntrackRequest(BaseModel):
    url: str


@router.post("/api/arr/letterboxd/untrack")
def letterboxd_untrack(payload: UntrackRequest, _=Depends(current_user)):
    db = SessionLocal()
    try:
        row = db.query(LetterboxdTrackedList).filter_by(url=payload.url).first()
        if row is None:
            fail(f"'{payload.url}' isn't tracked.", status_code=404)
        db.delete(row)
        db.commit()
        return ok(f"Stopped tracking '{payload.url}'.")
    finally:
        db.close()


@router.get("/api/arr/letterboxd/tracked")
def letterboxd_tracked(_=Depends(current_user_or_service)):
    db = SessionLocal()
    try:
        rows = db.query(LetterboxdTrackedList).order_by(LetterboxdTrackedList.created_at).all()
        lists = [
            {"id": r.id, "url": r.url, "app": r.app, "sonarrApp": r.sonarr_app, "label": r.label,
             "lastSyncedAt": r.last_synced_at.isoformat() if r.last_synced_at else None}
            for r in rows
        ]
        return ok(f"{len(lists)} tracked list(s).", lists=lists)
    finally:
        db.close()


@router.post("/api/arr/letterboxd/sync-tick")
# current_user_or_service, not current_user: scripts/letterboxd-sync.py
# (Task 9) calls this unattended via the CONTROL_PANEL_SERVICE_API_KEY,
# same documented automation exception as the other mutating routes in
# this file.
def letterboxd_sync_tick(_=Depends(current_user_or_service)):
    db = SessionLocal()
    try:
        tracked = db.query(LetterboxdTrackedList).all()
        results = []
        for row in tracked:
            rating_quality_map = _json.loads(row.rating_quality_map_json) if row.rating_quality_map_json else None
            try:
                result = _run_list_sync(
                    row.url, app=row.app, root_folder=row.root_folder, quality_profile=row.quality_profile,
                    rating_quality_map=rating_quality_map, tags_as_radarr_tags=row.tags_as_radarr_tags,
                    sonarr_crossover=False, sonarr_app=row.sonarr_app,
                )
                record_sync_log(
                    db, row.url, matched=result["matched"], unmatched=len(result["unmatched"]),
                    added=len(result["added"]), already=len(result["already"]), failed=len(result["failed"]),
                    tv_crossover=len(result["tvAdded"]) + len(result["tvAlready"]),
                )
                row.last_synced_at = datetime.now(timezone.utc)
                db.commit()
                results.append({"url": row.url, "added": result["added"], "failed": result["failed"]})
            except Exception as e:
                record_sync_log(db, row.url, matched=0, unmatched=0, added=0, already=0, failed=0, error_detail=str(e))
                results.append({"url": row.url, "added": [], "failed": [str(e)]})
        return ok(f"Synced {len(tracked)} tracked list(s).", results=results)
    finally:
        db.close()

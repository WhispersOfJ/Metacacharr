"""Letterboxd -> Radarr/Sonarr integration, ported from the FastAPI-era
control-panel/services/letterboxd/router.py (+ sync.py folded in) for the
Django/DRF rewrite.

Owns the single-film add (add_from_url), the list/watchlist/filmography/
collection add (add_from_list, backed by the shared _run_list_sync helper
also used by sync_tick), and the tracked-list registration/nightly-sync
loop (track/untrack/list_tracked/sync_tick).

Transforms applied vs. the FastAPI-era source:

1. core.responses.fail() (which raised a fastapi.HTTPException) is replaced
   with core.api_base.ServiceError, matching every other ported app.
2. services/letterboxd/sync.py's record_sync_log/recent_sync_logs
   (SQLAlchemy Session-based) are folded in directly as
   `_record_sync_log()`/`get_history()`, now writing/reading
   core.models.LetterboxdSyncLog via the Django ORM instead of
   SQLAlchemy's SessionLocal().
3. models.letterboxd_cache.LetterboxdTmdbCache /
   models.letterboxd_tracked_list.LetterboxdTrackedList (SQLAlchemy) become
   core.models.LetterboxdTmdbCache / core.models.LetterboxdTrackedList
   (Django ORM) - already defined in core/models.py, not created here.
4. _radarr_cfg/_sonarr_cfg validate against RADARR_APPS/SONARR_APPS - same
   behavior, `raise ServiceError(..., status=400)` instead of `fail()`.
5. Every SessionLocal()-scoped `db` argument (resolve_tmdb_ids,
   resolve_tv_crossovers, the per-slug LetterboxdTmdbCache lookup inline in
   _run_list_sync) is dropped - the Django ORM manages its own connection,
   no session object needs threading through call sites.
6. The 7 router entry points are renamed to the plan's interface names:
   radarr_add_from_letterboxd -> add_from_url, radarr_add_from_letterboxd_list
   -> add_from_list, letterboxd_history -> get_history, letterboxd_track ->
   track, letterboxd_untrack -> untrack, letterboxd_tracked -> list_tracked,
   letterboxd_sync_tick -> sync_tick. Each returns a plain dict (message +
   payload) instead of calling ok() directly - the API view layer pops
   "message" and passes the rest through EnvelopeAPIView.ok(), same pattern
   as every other ported app.
"""
import json
import time
from datetime import datetime, timezone

import httpx

from core.api_base import ServiceError
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
from core.models import LetterboxdSyncLog, LetterboxdTmdbCache, LetterboxdTrackedList
from letterboxd.cache import resolve_tmdb_ids, resolve_tv_crossovers
from letterboxd.scraping import (
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

HISTORY_PAGE_SIZE = 100


def _radarr_cfg(app: str) -> dict:
    if app not in RADARR_APPS:
        raise ServiceError(f"Unknown Radarr app '{app}' - expected one of {list(RADARR_APPS)}.", status=400)
    return ARR_APPS[app]


def _sonarr_cfg(app: str) -> dict:
    if app not in SONARR_APPS:
        raise ServiceError(f"Unknown Sonarr app '{app}' - expected one of {list(SONARR_APPS)}.", status=400)
    return ARR_APPS[app]


def add_from_url(url: str, *, app: str = "radarr", monitored: bool = True, search: bool = True,
                  root_folder: str | None = None, quality_profile: str | None = None,
                  dry_run: bool = False) -> dict:
    """POST /api/v2/letterboxd/add - a single Letterboxd film page ->
    Radarr add."""
    cfg = _radarr_cfg(app)
    url = url.strip()
    if "letterboxd.com/film/" not in url:
        raise ServiceError(
            "Not a Letterboxd film URL - expected something like https://letterboxd.com/film/<slug>/.",
            status=400,
        )
    page_text = fetch_page(url)
    match = LETTERBOXD_TMDB_RE.search(page_text)
    if not match:
        raise ServiceError("No TMDb link found on that Letterboxd page - it may be unmatched to TMDb.", status=404)
    tmdb_id = int(match.group(1))

    try:
        existing = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie", params={"tmdbId": tmdb_id},
                              headers={"X-Api-Key": cfg["key"]}, timeout=20)
        existing.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"Couldn't check whether Radarr already has this movie: {e}") from e
    existing_movies = existing.json()
    if existing_movies:
        m = existing_movies[0]
        return {
            "message": f'"{m["title"]}" ({m.get("year")}) is already in Radarr.',
            "tmdbId": tmdb_id, "radarrId": m["id"], "alreadyAdded": True,
        }

    try:
        lookup = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie/lookup/tmdb", params={"tmdbId": tmdb_id},
                            headers={"X-Api-Key": cfg["key"]}, timeout=20)
        lookup.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"Radarr's TMDb lookup failed: {e}") from e
    movie = lookup.json()
    if not movie or not movie.get("title"):
        raise ServiceError(f"Radarr has no TMDb match for id {tmdb_id}.", status=404)

    root_folder_path, quality_profile_id = radarr_root_folder_and_profile(cfg, root_folder, quality_profile)
    movie["qualityProfileId"] = quality_profile_id
    movie["rootFolderPath"] = root_folder_path
    movie["monitored"] = monitored
    movie["addOptions"] = {"searchForMovie": search}

    if dry_run:
        return {
            "message": f'Would add "{movie["title"]}" ({movie.get("year")}) to Radarr - dry run, nothing written.',
            "tmdbId": tmdb_id, "dryRun": True,
        }

    try:
        add = httpx.post(f"{cfg['url']}/api/{cfg['api']}/movie", json=movie, headers={"X-Api-Key": cfg["key"]}, timeout=30)
        add.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise ServiceError(f"Radarr rejected the add: {e.response.text.strip() or e}") from e
    except httpx.HTTPError as e:
        raise ServiceError(f"Radarr add failed: {e}") from e

    added = add.json()
    return {
        "message": f'Added "{added.get("title", movie["title"])}" ({added.get("year", movie.get("year"))}) to Radarr.',
        "tmdbId": tmdb_id, "radarrId": added.get("id"),
    }


def _run_list_sync(url: str, *, app: str = "radarr", monitored: bool = True, search: bool = True,
                    root_folder: str | None = None, quality_profile: str | None = None,
                    limit: int | None = None, dry_run: bool = False,
                    rating_quality_map: dict[str, str] | None = None, tags_as_radarr_tags: bool = False,
                    sonarr_crossover: bool = False, sonarr_app: str = "sonarr") -> dict:
    """The add-from-letterboxd-list flow, callable from both add_from_list()
    and sync_tick() (the tracked-list scheduler) - both need the identical
    scrape/resolve/add logic, just with the request's fields coming from
    different sources (an add_from_list() call vs. a LetterboxdTrackedList
    row). Returns a plain dict (not the ok()-shaped envelope) so callers can
    build their own summary/telemetry from it - added, already, failed,
    unmatched, tvAdded, tvAlready, tvFailed, matched."""
    cfg = _radarr_cfg(app)
    base_url = url.strip().rstrip("/")
    if LETTERBOXD_DISALLOWED_RE.search(base_url + "/"):
        raise ServiceError(
            "That URL includes a sort/filter option Letterboxd's robots.txt disallows scraping "
            "(by/, genre/, decade/, year/, this/week/, size/large/, etc). Use the plain, unsorted URL.",
            status=400,
        )
    if not LETTERBOXD_GRID_RE.match(base_url):
        raise ServiceError(
            "Not a recognized Letterboxd list/watchlist/filmography/collection URL - expected something like "
            "https://letterboxd.com/<user>/list/<slug>/, https://letterboxd.com/<user>/watchlist/, "
            "https://letterboxd.com/<user>/films/, https://letterboxd.com/actor/<slug>/, "
            "https://letterboxd.com/films/in/<collection>/, or https://letterboxd.com/films/popular/.",
            status=400,
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
        raise ServiceError(
            "No films found on that Letterboxd page. Some pages (e.g. /films/popular/) render their "
            "poster grid client-side in JS and have no scrapeable server-rendered film data.",
            status=404,
        )

    slug_limit = min(limit, 720) if limit else 720
    slugs = slugs[:slug_limit]

    tmdb_ids, unmatched = resolve_tmdb_ids(slugs)
    tmdb_ids = list(dict.fromkeys(tmdb_ids))
    print(f"letterboxd-list: resolved {len(tmdb_ids)} tmdb id(s), {len(unmatched)} unmatched, out of {len(slugs)} slug(s)")

    tv_added, tv_already, tv_failed = [], [], []
    if sonarr_crossover and unmatched:
        sonarr_cfg = _sonarr_cfg(sonarr_app)
        tv_matches, unmatched = resolve_tv_crossovers(unmatched)
        if tv_matches:
            try:
                sonarr_library = httpx.get(f"{sonarr_cfg['url']}/api/{sonarr_cfg['api']}/series",
                                            headers={"X-Api-Key": sonarr_cfg["key"]}, timeout=30)
                sonarr_library.raise_for_status()
            except httpx.HTTPError as e:
                raise ServiceError(f"Couldn't read Sonarr's library: {e}") from e
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
        raise ServiceError(f"Couldn't read Radarr's library: {e}") from e
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
        for slug in slugs:
            cached = LetterboxdTmdbCache.objects.filter(slug=slug).first()
            if cached and cached.tmdb_id is not None:
                slug_to_tmdb[slug] = cached.tmdb_id

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

    return {
        "added": added, "already": already, "failed": failed, "unmatched": unmatched,
        "tvAdded": tv_added, "tvAlready": tv_already, "tvFailed": tv_failed,
        "matched": len(tmdb_ids),
    }


def _record_sync_log(list_url: str, *, matched: int, unmatched: int, added: int, already: int, failed: int,
                      tv_crossover: int = 0, error_detail: str | None = None) -> None:
    """Mirrors services/letterboxd/sync.py's record_sync_log, now via the ORM."""
    LetterboxdSyncLog.objects.create(
        list_url=list_url, matched=matched, unmatched=unmatched, added=added, already=already, failed=failed,
        tv_crossover=tv_crossover, error_detail=error_detail,
    )


def add_from_list(url: str, *, app: str = "radarr", monitored: bool = True, search: bool = True,
                   root_folder: str | None = None, quality_profile: str | None = None,
                   limit: int | None = None, dry_run: bool = False,
                   rating_quality_map: dict[str, str] | None = None, tags_as_radarr_tags: bool = False,
                   sonarr_crossover: bool = False, sonarr_app: str = "sonarr") -> dict:
    """POST /api/v2/letterboxd/add-from-list - one-off (or manually
    re-triggered) import of a Letterboxd list/watchlist/filmography/
    collection's films into Radarr (optionally cross-adding unmatched
    titles to Sonarr)."""
    result = _run_list_sync(
        url, app=app, monitored=monitored, search=search, root_folder=root_folder, quality_profile=quality_profile,
        limit=limit, dry_run=dry_run, rating_quality_map=rating_quality_map,
        tags_as_radarr_tags=tags_as_radarr_tags, sonarr_crossover=sonarr_crossover, sonarr_app=sonarr_app,
    )
    _record_sync_log(
        url, matched=result["matched"], unmatched=len(result["unmatched"]),
        added=len(result["added"]), already=len(result["already"]), failed=len(result["failed"]),
        tv_crossover=len(result["tvAdded"]) + len(result["tvAlready"]),
    )

    verb = "would be added" if dry_run else "added"
    summary = f"{len(result['added'])} {verb}, {len(result['already'])} already in Radarr, {len(result['failed'])} failed"
    if result["unmatched"]:
        summary += f", {len(result['unmatched'])} had no TMDb match"
    if result["tvAdded"] or result["tvAlready"] or result["tvFailed"]:
        summary += (f"; {len(result['tvAdded'])} TV crossover {verb} to Sonarr, "
                     f"{len(result['tvAlready'])} already in Sonarr, {len(result['tvFailed'])} failed")
    return {
        "message": summary,
        "added": result["added"], "alreadyCount": len(result["already"]), "failed": result["failed"],
        "unmatched": result["unmatched"], "dryRun": dry_run, "tvCrossoverAdded": result["tvAdded"],
        "tvCrossoverAlready": result["tvAlready"], "tvCrossoverFailed": result["tvFailed"],
        "tvCrossoverCount": len(result["tvAdded"]) + len(result["tvAlready"]),
    }


def get_history() -> dict:
    """GET /api/v2/letterboxd/history - recent sync-log rows, newest first."""
    rows = LetterboxdSyncLog.objects.order_by("-id")[:HISTORY_PAGE_SIZE]
    runs = [
        {
            "listUrl": r.list_url, "runAt": r.run_at.isoformat() if r.run_at else None,
            "matched": r.matched, "unmatched": r.unmatched, "added": r.added, "already": r.already,
            "failed": r.failed, "tvCrossover": r.tv_crossover, "errorDetail": r.error_detail,
        }
        for r in rows
    ]
    return {"message": f"{len(runs)} recent sync run(s).", "runs": runs}


def track(url: str, *, app: str = "radarr", label: str | None = None, root_folder: str | None = None,
          quality_profile: str | None = None, rating_quality_map: dict[str, str] | None = None,
          tags_as_radarr_tags: bool = False, sonarr_app: str = "sonarr") -> dict:
    """POST /api/v2/letterboxd/track - register a list for the nightly
    diff-only sync driven by sync_tick()."""
    _radarr_cfg(app)
    _sonarr_cfg(sonarr_app)
    existing = LetterboxdTrackedList.objects.filter(url=url).first()
    if existing is not None:
        raise ServiceError(f"'{url}' is already tracked (id {existing.id}).", status=409)
    row = LetterboxdTrackedList.objects.create(
        url=url, app=app, label=label, root_folder=root_folder, quality_profile=quality_profile,
        tags_as_radarr_tags=tags_as_radarr_tags, sonarr_app=sonarr_app,
        rating_quality_map_json=json.dumps(rating_quality_map) if rating_quality_map else None,
    )
    return {"message": f"Now tracking '{url}'.", "id": row.id}


def untrack(url: str) -> dict:
    """POST /api/v2/letterboxd/untrack - stop syncing a tracked list."""
    row = LetterboxdTrackedList.objects.filter(url=url).first()
    if row is None:
        raise ServiceError(f"'{url}' isn't tracked.", status=404)
    row.delete()
    return {"message": f"Stopped tracking '{url}'."}


def list_tracked() -> dict:
    """GET /api/v2/letterboxd/tracked - every list currently registered for sync."""
    rows = LetterboxdTrackedList.objects.order_by("created_at")
    lists = [
        {"id": r.id, "url": r.url, "app": r.app, "sonarrApp": r.sonarr_app, "label": r.label,
         "lastSyncedAt": r.last_synced_at.isoformat() if r.last_synced_at else None}
        for r in rows
    ]
    return {"message": f"{len(lists)} tracked list(s).", "lists": lists}


def sync_tick() -> dict:
    """POST /api/v2/letterboxd/sync-tick - run every tracked list's sync,
    once each, collecting per-row errors without aborting the loop (a
    failure on one list must not stop the rest from syncing). Always runs
    with sonarr_crossover=False, matching the FastAPI-era route - the
    scheduled sync never does the crossover pass."""
    tracked = list(LetterboxdTrackedList.objects.all())
    results = []
    for row in tracked:
        rating_quality_map = json.loads(row.rating_quality_map_json) if row.rating_quality_map_json else None
        try:
            result = _run_list_sync(
                row.url, app=row.app, root_folder=row.root_folder, quality_profile=row.quality_profile,
                rating_quality_map=rating_quality_map, tags_as_radarr_tags=row.tags_as_radarr_tags,
                sonarr_crossover=False, sonarr_app=row.sonarr_app,
            )
            _record_sync_log(
                row.url, matched=result["matched"], unmatched=len(result["unmatched"]),
                added=len(result["added"]), already=len(result["already"]), failed=len(result["failed"]),
                tv_crossover=len(result["tvAdded"]) + len(result["tvAlready"]),
            )
            row.last_synced_at = datetime.now(timezone.utc)
            row.save(update_fields=["last_synced_at"])
            results.append({"url": row.url, "added": result["added"], "failed": result["failed"]})
        except Exception as e:
            _record_sync_log(row.url, matched=0, unmatched=0, added=0, already=0, failed=0, error_detail=str(e))
            results.append({"url": row.url, "added": [], "failed": [str(e)]})
    return {"message": f"Synced {len(tracked)} tracked list(s).", "results": results}

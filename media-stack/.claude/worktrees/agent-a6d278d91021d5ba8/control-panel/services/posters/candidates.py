"""Poster-candidate resolution across TMDb/Fanart/TheTVDB/OMDb/TVmaze,
ported from app.py (lines 54-60, 91, 756-1062) - Phase 4 of
.claude/plans/evolved-control-panel-backend.plan.md.

Pure lookup logic, no job/state - "given Plex metadata, return candidate
poster URLs." Reused by both the auto-sync worker and the manual-review
worker in router.py.
"""
import os
import threading
import time

import httpx
from core.responses import fail

TMDB_KEY = os.environ.get("TMDB_KEY")
TMDB_URL = "https://api.themoviedb.org/3"
FANART_KEY = os.environ.get("FANART_KEY")
FANART_URL = "https://webservice.fanart.tv/v3"
TVDB_KEY = os.environ.get("TVDB_KEY")
TVDB_URL = "https://api4.thetvdb.com/v4"


def omdb_key() -> str | None:
    return os.environ.get("OMDB_KEY") or None


def tmdb_get(path: str, **params) -> dict:
    if not TMDB_KEY:
        fail("TMDb isn't configured (TMDB_KEY not set)", status_code=503)
    r = httpx.get(f"{TMDB_URL}{path}", params={"api_key": TMDB_KEY, **params}, timeout=15)
    r.raise_for_status()
    return r.json()


def tmdb_id_for_item(meta: dict, media_type: str) -> int | None:
    """media_type is Plex's own section type ("movie"/"show") for the item
    this Guid list came from. Prefers a direct tmdb:// Guid (present on
    both movies and shows under Plex's new agent, confirmed live against
    this library) and only falls back to TMDb's /find endpoint (external
    ID lookup, not scraping) for items still on an older match."""
    guids = {}
    for g in meta.get("Guid", []):
        gid = g.get("id", "")
        if "://" in gid:
            source, value = gid.split("://", 1)
            guids[source] = value

    if "tmdb" in guids:
        try:
            return int(guids["tmdb"])
        except ValueError:
            pass

    kind = "movie" if media_type == "movie" else "tv"
    if "tvdb" in guids and media_type == "show":
        try:
            found = tmdb_get(f"/find/{guids['tvdb']}", external_source="tvdb_id")
            results = found.get("tv_results") or []
            if results:
                return results[0]["id"]
        except httpx.HTTPError:
            pass
    if "imdb" in guids:
        try:
            found = tmdb_get(f"/find/{guids['imdb']}", external_source="imdb_id")
            results = found.get(f"{kind}_results") or []
            if results:
                return results[0]["id"]
        except httpx.HTTPError:
            pass
    return None


def tmdb_top_posters(tmdb_id: int, media_type: str, limit: int = 3) -> list[dict]:
    """Best-first list of up to `limit` candidate posters, ranked the same
    way tmdb_best_poster_url picks its single winner (vote_average, then
    vote_count) - candidate #1 here is always identical to what auto mode
    would have picked."""
    kind = "movie" if media_type == "movie" else "tv"
    try:
        data = tmdb_get(f"/{kind}/{tmdb_id}/images", include_image_language="en,null")
    except httpx.HTTPError:
        return []
    posters = data.get("posters") or []
    posters.sort(key=lambda p: (p.get("vote_average") or 0, p.get("vote_count") or 0), reverse=True)
    return [
        {
            "url": f"https://image.tmdb.org/t/p/original{p['file_path']}",
            "label": f"★{p.get('vote_average') or 0:.1f} ({p.get('vote_count') or 0} votes)",
        }
        for p in posters[:limit]
    ]


def fanart_ids_for_item(meta: dict) -> tuple[int | None, int | None]:
    """(tmdb_id, tvdb_id) pulled straight from Plex's own Guid list - no
    extra lookups needed, unlike tmdb_id_for_item's TMDb /find fallback,
    since Fanart's own endpoints key movies by TMDb id and shows by
    TheTVDB id directly (confirmed against fanart.tv's v3 API - movies
    endpoint takes a TMDb/IMDb id, tv endpoint takes a TheTVDB id, not
    interchangeable)."""
    tmdb_id = tvdb_id = None
    for g in meta.get("Guid", []):
        gid = g.get("id", "")
        if gid.startswith("tmdb://"):
            try:
                tmdb_id = int(gid.split("://", 1)[1])
            except ValueError:
                pass
        elif gid.startswith("tvdb://"):
            try:
                tvdb_id = int(gid.split("://", 1)[1])
            except ValueError:
                pass
    return tmdb_id, tvdb_id


def imdb_id_for_item(meta: dict) -> str | None:
    """IMDb id pulled straight from Plex's own Guid list, same no-extra-
    lookups approach as fanart_ids_for_item - both OMDb and TVmaze key
    directly off imdb://, no /find-style fallback needed."""
    for g in meta.get("Guid", []):
        gid = g.get("id", "")
        if gid.startswith("imdb://"):
            return gid.split("://", 1)[1]
    return None


def fanart_top_posters(media_type: str, tmdb_id: int | None, tvdb_id: int | None, limit: int = 3) -> list[dict]:
    """Fanart.tv v3: movies keyed by TMDb id (webservice.fanart.tv/v3/movies/{tmdb_id}),
    shows keyed by TheTVDB id (webservice.fanart.tv/v3/tv/{tvdb_id}) - confirmed
    live against the real API (unauthenticated requests to both paths return
    a "missing api_key" error rather than 404, proving the path shape) and
    against Kodi's own themoviedb.org scraper source. Poster arrays are
    "movieposter"/"tvposter", each entry carrying id/url/lang/likes (all
    strings except id). No vote_average like TMDb - likes is the only
    quality signal, so rank by highest-liked, preferring an untranslated
    (lang "en" or "00") poster on a tie. Best-first list of up to `limit`
    candidates - empty (never raises) on a missing id, 404 (title not in
    Fanart's database - common, not an error), or any other request
    failure, so callers always treat "no candidates" as a skip."""
    if media_type == "movie":
        media_id, kind, field = tmdb_id, "movies", "movieposter"
    else:
        media_id, kind, field = tvdb_id, "tv", "tvposter"
    if media_id is None:
        return []
    try:
        r = httpx.get(f"{FANART_URL}/{kind}/{media_id}", params={"api_key": FANART_KEY}, timeout=15)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError:
        return []
    posters = data.get(field) or []
    posters.sort(key=lambda p: (int(p.get("likes") or 0), p.get("lang") in ("en", "00")), reverse=True)
    return [
        {"url": p.get("url"), "label": f"♥{p.get('likes') or 0} ({p.get('lang') or '?'})"}
        for p in posters[:limit]
    ]


# TheTVDB v4 auth is a login-for-a-token flow, not a per-request api_key
# query param like TMDb/Fanart - POST /login with the project api key
# returns a bearer token valid 1 month (confirmed live against the real
# key). Cached in-process and refreshed 5 minutes before expiry so normal
# poster-sync runs (a few times/day) essentially never re-login; a fresh
# container start just re-logs-in once on first use.
_TVDB_TOKEN: dict = {"value": None, "expires_at": 0}
_TVDB_TOKEN_LOCK = threading.Lock()


def tvdb_token() -> str | None:
    if not TVDB_KEY:
        return None
    with _TVDB_TOKEN_LOCK:
        if _TVDB_TOKEN["value"] and time.time() < _TVDB_TOKEN["expires_at"]:
            return _TVDB_TOKEN["value"]
        try:
            r = httpx.post(f"{TVDB_URL}/login", json={"apikey": TVDB_KEY}, timeout=15)
            r.raise_for_status()
            token = r.json()["data"]["token"]
        except (httpx.HTTPError, KeyError):
            return None
        _TVDB_TOKEN["value"] = token
        # Real tokens are valid 1 month; refreshing after 25 days leaves a
        # comfortable margin without needing to parse the JWT's own exp.
        _TVDB_TOKEN["expires_at"] = time.time() + 25 * 24 * 3600
        return token


def tvdb_top_posters(media_type: str, tvdb_id: int | None, limit: int = 3) -> list[dict]:
    """TheTVDB v4: shows keyed by their own numeric id via a dedicated
    GET /series/{id}/artworks?type=2 endpoint (type 2 = series poster,
    confirmed live via /artwork/types - not guessed); movies have no
    equivalent dedicated endpoint, their posters come bundled in
    GET /movies/{id}/extended's own artworks array, filtered client-side to
    type 14 = movie poster (also confirmed live). Each artwork carries a
    "score" (community popularity, same role as Fanart's "likes" - no
    vote_average-style rating exists here) - best-first list ranked by
    that score. Empty (never raises) on a missing id, no login token
    (TVDB_KEY unset), 404, or any other request failure."""
    if tvdb_id is None:
        return []
    token = tvdb_token()
    if not token:
        return []
    headers = {"Authorization": f"Bearer {token}"}
    try:
        if media_type == "movie":
            r = httpx.get(f"{TVDB_URL}/movies/{tvdb_id}/extended", headers=headers, timeout=15)
            if r.status_code == 404:
                return []
            r.raise_for_status()
            artworks = [a for a in (r.json()["data"].get("artworks") or []) if a.get("type") == 14]
        else:
            r = httpx.get(f"{TVDB_URL}/series/{tvdb_id}/artworks", params={"type": 2}, headers=headers, timeout=15)
            if r.status_code == 404:
                return []
            r.raise_for_status()
            artworks = r.json()["data"].get("artworks") or []
    except (httpx.HTTPError, KeyError):
        return []
    artworks.sort(key=lambda a: a.get("score") or 0, reverse=True)
    return [
        {"url": a.get("image"), "label": f"★{a.get('score') or 0} ({a.get('language') or '?'})"}
        for a in artworks[:limit]
    ]


def omdb_top_posters(imdb_id: str | None, limit: int = 3) -> list[dict]:
    """OMDb (reuses the OMDB_KEY already configured for /api/ratings/imdb -
    no separate key needed) returns exactly one poster per title, no
    ranking/list endpoint like TMDb/Fanart/TVDB - so this is always a
    single-candidate list regardless of `limit`. Empty (never raises) on a
    missing id, no key configured, an unmatched id ("Response": "False",
    confirmed live - not an error, just no data for that id), a "N/A"
    poster field (a real, common OMDb value meaning no poster on file), or
    any other request failure."""
    key = omdb_key()
    if imdb_id is None or not key:
        return []
    try:
        r = httpx.get("https://www.omdbapi.com/", params={"i": imdb_id, "apikey": key}, timeout=15)
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError:
        return []
    if data.get("Response") == "False":
        return []
    poster = data.get("Poster")
    if not poster or poster == "N/A":
        return []
    return [{"url": poster, "label": "OMDb"}]


def tvmaze_top_posters(media_type: str, imdb_id: str | None, limit: int = 3) -> list[dict]:
    """TVmaze: free, no API key, shows only - confirmed live it has no
    /lookup/movies route at all (404, "Invalid Route"), so movies always
    return empty here regardless of id. GET /lookup/shows?imdb={id} 301s to
    the real show record (needs a redirect-following client - confirmed
    live the raw redirect response body is a bare "null", not the show,
    if redirects aren't followed); like OMDb, TVmaze has no poster-ranking
    endpoint, always a single-candidate list. Empty (never raises) on a
    missing id, a movie media_type, no match (a real, common outcome - not
    every show is cross-referenced by IMDb id in TVmaze's own database), or
    any other request failure."""
    if media_type != "show" or imdb_id is None:
        return []
    try:
        r = httpx.get("https://api.tvmaze.com/lookup/shows", params={"imdb": imdb_id}, timeout=15, follow_redirects=True)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError:
        return []
    if not data:
        return []
    image = (data.get("image") or {}).get("original")
    if not image:
        return []
    return [{"url": image, "label": "TVmaze"}]


def resolve_poster_candidates(meta: dict, media_type: str, primary_source: str, limit: int = 3) -> tuple[str | None, list[dict]]:
    """Best-first candidates from `primary_source`, falling back through
    the other configured sources (TMDb/Fanart/TVDB/OMDb/TVmaze, fixed
    priority order) if the primary has nothing for this item - so a poster
    missing from one catalog doesn't mean the item gets skipped outright
    when another catalog would have covered it. Skips a source entirely
    (rather than erroring) if its key is missing (OMDb) or it structurally
    can't cover this item (TVmaze on a movie). Returns (source actually
    used, candidates) - source is None only when every configured source
    found nothing, so callers can tell a real all-source miss apart from a
    normal single-source pick."""
    fallback_order = [s for s in ("tmdb", "fanart", "tvdb", "omdb", "tvmaze") if s != primary_source]
    for src in (primary_source, *fallback_order):
        if src == "fanart":
            if not FANART_KEY:
                continue
            tmdb_id, tvdb_id = fanart_ids_for_item(meta)
            candidates = fanart_top_posters(media_type, tmdb_id, tvdb_id, limit=limit)
        elif src == "tvdb":
            if not TVDB_KEY:
                continue
            _, tvdb_id = fanart_ids_for_item(meta)
            candidates = tvdb_top_posters(media_type, tvdb_id, limit=limit)
        elif src == "omdb":
            if not omdb_key():
                continue
            candidates = omdb_top_posters(imdb_id_for_item(meta), limit=limit)
        elif src == "tvmaze":
            candidates = tvmaze_top_posters(media_type, imdb_id_for_item(meta), limit=limit)
        else:
            if not TMDB_KEY:
                continue
            tmdb_id = tmdb_id_for_item(meta, media_type)
            candidates = tmdb_top_posters(tmdb_id, media_type, limit=limit) if tmdb_id is not None else []
        if candidates:
            return src, candidates
    return None, []

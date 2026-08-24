"""Slug -> TMDb id dedup cache, ported from
control-panel/services/letterboxd/cache.py for the Django/DRF rewrite - a
re-scraped list/watchlist skips the per-slug Letterboxd film-page fetch for
any slug a prior run already resolved. A slug with no TMDb match gets
cached too (tmdb_id=None), so re-runs don't keep re-fetching known dead
ends. Also owns the TV-crossover lookup (resolve_tv_crossovers) for slugs
that remain unmatched after the cache pass.

Transform vs. the FastAPI-era source: SQLAlchemy `Session`-based queries
(`db.query(...).filter(...)`, `db.add`/`db.commit`) become Django ORM calls
against core.models.LetterboxdTmdbCache; resolve_tmdb_ids/
resolve_tv_crossovers no longer take a `db` argument - the FastAPI-era
resolve_tv_crossovers accepted `db` only for call-signature symmetry with
resolve_tmdb_ids and never actually queried it (per its own docstring), and
Django's ORM doesn't need a session object threaded through call sites."""
import httpx

from core.arr_client import ARR_APPS
from core.models import LetterboxdTmdbCache
from letterboxd.scraping import LETTERBOXD_TMDB_RE, fetch_page, scrape_title_year


def resolve_tmdb_ids(slugs: list[str]) -> tuple[list[int], list[str]]:
    """Returns (tmdb_ids, unmatched_slugs). Order of tmdb_ids follows
    `slugs`' order, not cache-hit-then-miss order."""
    cached_rows = {row.slug: row for row in LetterboxdTmdbCache.objects.filter(slug__in=slugs)}

    tmdb_ids: list[int] = []
    unmatched: list[str] = []
    for slug in slugs:
        row = cached_rows.get(slug)
        if row is None:
            match = LETTERBOXD_TMDB_RE.search(fetch_page(f"https://letterboxd.com/film/{slug}/"))
            tmdb_id = int(match.group(1)) if match else None
            row = LetterboxdTmdbCache.objects.create(slug=slug, tmdb_id=tmdb_id, media_type="movie")
        if row.tmdb_id is not None:
            tmdb_ids.append(row.tmdb_id)
        else:
            unmatched.append(slug)
    return tmdb_ids, unmatched


_TV_CROSSOVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
}


def resolve_tv_crossovers(unmatched_slugs: list[str]) -> tuple[list[dict], list[str]]:
    """For each slug with no TMDb movie match, checks Sonarr's own
    series-lookup-by-title to catch titles Letterboxd carries as a film
    entry that are actually a miniseries/TV special - no TMDB API call
    needed, Sonarr's /series/lookup?term= does its own title search.
    Returns (matches, still_unmatched); matches is
    [{"slug", "title", "year", "tvdb_id"}, ...]."""
    cfg = ARR_APPS["sonarr"]
    matches: list[dict] = []
    still_unmatched: list[str] = []
    for slug in unmatched_slugs:
        try:
            r = httpx.get(f"https://letterboxd.com/film/{slug}/", headers=_TV_CROSSOVER_HEADERS,
                          timeout=15, follow_redirects=True)
            r.raise_for_status()
            film_html = r.text
        except httpx.HTTPError:
            still_unmatched.append(slug)
            continue
        title_year = scrape_title_year(film_html)
        if title_year is None:
            still_unmatched.append(slug)
            continue
        title, year = title_year
        try:
            lookup = httpx.get(f"{cfg['url']}/api/{cfg['api']}/series/lookup", params={"term": title},
                                headers={"X-Api-Key": cfg["key"]}, timeout=20)
            lookup.raise_for_status()
            results = lookup.json()
        except httpx.HTTPError:
            still_unmatched.append(slug)
            continue
        # Require an exact title AND year match - series/lookup is a fuzzy
        # title search and can return unrelated shows for a generic title.
        exact = next((s for s in results if s.get("title") == title and s.get("year") == year), None)
        if exact is None or not exact.get("tvdbId"):
            still_unmatched.append(slug)
            continue
        matches.append({"slug": slug, "title": title, "year": year, "tvdb_id": exact["tvdbId"]})
    return matches, still_unmatched

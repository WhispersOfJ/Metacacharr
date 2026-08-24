"""Slug -> TMDb id dedup cache (models.letterboxd_cache.LetterboxdTmdbCache)
- a re-scraped list/watchlist skips the per-slug Letterboxd film-page fetch
for any slug a prior run already resolved. A slug with no TMDb match gets
cached too (tmdb_id=None), so re-runs don't keep re-fetching known dead
ends. Also owns the TV-crossover lookup (resolve_tv_crossovers) for slugs
that remain unmatched after the cache pass.
"""
import httpx
from sqlalchemy.orm import Session

from core.arr_client import ARR_APPS
from models.letterboxd_cache import LetterboxdTmdbCache
from services.letterboxd.scraping import LETTERBOXD_TMDB_RE, fetch_page, scrape_title_year


def resolve_tmdb_ids(db: Session, slugs: list[str]) -> tuple[list[int], list[str]]:
    """Returns (tmdb_ids, unmatched_slugs), same shape the caller
    previously built inline in the fetch loop. Order of tmdb_ids follows
    `slugs`' order, not cache-hit-then-miss order."""
    cached_rows = {
        row.slug: row
        for row in db.query(LetterboxdTmdbCache).filter(LetterboxdTmdbCache.slug.in_(slugs)).all()
    }

    tmdb_ids: list[int] = []
    unmatched: list[str] = []
    for slug in slugs:
        row = cached_rows.get(slug)
        if row is None:
            match = LETTERBOXD_TMDB_RE.search(fetch_page(f"https://letterboxd.com/film/{slug}/"))
            tmdb_id = int(match.group(1)) if match else None
            row = LetterboxdTmdbCache(slug=slug, tmdb_id=tmdb_id, media_type="movie")
            db.add(row)
            db.commit()
        if row.tmdb_id is not None:
            tmdb_ids.append(row.tmdb_id)
        else:
            unmatched.append(slug)
    return tmdb_ids, unmatched


_TV_CROSSOVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
}


def resolve_tv_crossovers(db: Session, unmatched_slugs: list[str]) -> tuple[list[dict], list[str]]:
    """For each slug with no TMDb movie match, checks Sonarr's own
    series-lookup-by-title to catch titles Letterboxd carries as a film
    entry that are actually a miniseries/TV special - no TMDB API call
    needed, Sonarr's /series/lookup?term= does its own title search.
    Returns (matches, still_unmatched); matches is
    [{"slug", "title", "year", "tvdb_id"}, ...]. `db` is accepted for
    signature symmetry with resolve_tmdb_ids (Task 8's tracked-list sync
    calls both against the same session) but isn't queried here."""
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

#!/usr/bin/env python3
"""Audits a Plex movie library for missing/broken TMDb metadata links.

Read-only: never modifies or deletes anything in Plex. For every movie it
checks whether Plex already carries a tmdb:// Guid (or the legacy
com.plexapp.agents.themoviedb agent id). If not, it searches TMDb by
title/year and scores the best candidate. Every item ends up in exactly one
of four buckets, written to a CSV plus a console summary:

  matched      - already has a TMDb id, nothing to do
  fixable      - no TMDb id, but a high/medium-confidence candidate was
                 found; needs a human to confirm and apply it (this script
                 never applies it - see "Applying a fix" below)
  unmatched    - no TMDb id, and no reasonable candidate after two search
                 attempts (exact title+year, then title alone); a real
                 candidate for a bad rip/wrong-title/or deletion review
  search_error - TMDb was unreachable/rate-limited past the retry budget;
                 kept separate from "unmatched" so a TMDb outage never
                 gets misread as "this movie doesn't exist"

Note on the requested libraries: tmdb3 (PyPI) is an abandoned, Python
2-era wrapper around a TMDb API version that no longer exists - it's not
usable against the current v3 REST API. This script uses `requests`
directly against https://api.themoviedb.org/3, the same approach already
used by control-panel/app.py's poster-sync feature in this repo.

Install:
    pip install plexapi requests

Run:
    export PLEX_URL=http://192.168.4.20:32400
    export PLEX_TOKEN=xxxx
    export TMDB_KEY=xxxx
    python3 audit-tmdb-links.py
    python3 audit-tmdb-links.py --library Movies --csv report.csv --limit 50
"""
import argparse
import csv
import os
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

try:
    from plexapi.server import PlexServer
except ImportError:
    print("Missing dependency: pip install plexapi requests", file=sys.stderr)
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Missing dependency: pip install plexapi requests", file=sys.stderr)
    sys.exit(1)

TMDB_API = "https://api.themoviedb.org/3"
STACK_DIR = Path(__file__).resolve().parent.parent
LEGACY_TMDB_RE = re.compile(r"com\.plexapp\.agents\.themoviedb://(\d+)")

HIGH_CONFIDENCE_RATIO = 0.92
MIN_CANDIDATE_RATIO = 0.60
MAX_YEAR_DELTA_HIGH = 1


class TMDbUnavailable(Exception):
    pass


def env_get(key):
    """Falls back to this repo's .env file if the var isn't already
    exported - lets the script run either standalone (real env vars) or
    from inside this stack's checkout without a separate export step."""
    val = os.environ.get(key)
    if val:
        return val
    env_path = STACK_DIR / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


def existing_tmdb_id(movie):
    """None if the item has no TMDb link yet. Checks the new agent's Guid
    list first (tmdb://<id>), then falls back to the legacy
    com.plexapp.agents.themoviedb guid still present on older matches."""
    for g in getattr(movie, "guids", []) or []:
        gid = g.id or ""
        if gid.startswith("tmdb://"):
            try:
                return int(gid.split("://", 1)[1])
            except ValueError:
                pass
    m = LEGACY_TMDB_RE.search(movie.guid or "")
    if m:
        return int(m.group(1))
    return None


def normalize_title(title):
    title = title.lower()
    title = re.sub(r"[^a-z0-9 ]", "", title)
    title = re.sub(r"^(the|a|an) ", "", title)
    return title.strip()


def tmdb_search(session, api_key, title, year=None, retries=3):
    """Two-pass search: title+year first, then title alone if that comes
    back empty (release-year drift between Plex's cache and TMDb is
    common). Raises TMDbUnavailable only after retries are exhausted on a
    network error or a persistent rate limit - a real "no results" comes
    back as an empty list, not an exception."""
    for query_year in ([year, None] if year else [None]):
        params = {"api_key": api_key, "query": title}
        if query_year:
            params["year"] = query_year
        results = _get_with_retry(session, "/search/movie", params, retries)
        if results:
            return results
    return []


def _get_with_retry(session, path, params, retries):
    last_err = None
    for attempt in range(retries):
        try:
            r = session.get(f"{TMDB_API}{path}", params=params, timeout=15)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_err = e
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 2 ** attempt))
            time.sleep(wait)
            continue
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            last_err = e
            time.sleep(2 ** attempt)
            continue
        return r.json().get("results", [])
    raise TMDbUnavailable(str(last_err) if last_err else f"exhausted retries on {path}")


def best_candidate(results, title, year):
    """Returns (candidate_dict, ratio, year_delta) for the best-scoring
    result, or None if nothing clears MIN_CANDIDATE_RATIO."""
    norm_title = normalize_title(title)
    scored = []
    for cand in results:
        cand_title = cand.get("title") or cand.get("original_title") or ""
        ratio = SequenceMatcher(None, norm_title, normalize_title(cand_title)).ratio()
        cand_year_str = (cand.get("release_date") or "")[:4]
        year_delta = None
        if year and cand_year_str.isdigit():
            year_delta = abs(int(cand_year_str) - year)
        score = ratio - (0.05 * year_delta if year_delta else 0)
        scored.append((score, ratio, year_delta, cand))
    if not scored:
        return None
    scored.sort(key=lambda t: t[0], reverse=True)
    score, ratio, year_delta, cand = scored[0]
    if ratio < MIN_CANDIDATE_RATIO:
        return None
    return cand, ratio, year_delta


def confidence_label(ratio, year_delta):
    if ratio >= HIGH_CONFIDENCE_RATIO and (year_delta is None or year_delta <= MAX_YEAR_DELTA_HIGH):
        return "high"
    return "medium"


def audit(plex_url, plex_token, tmdb_key, library_name, limit, delay):
    plex = PlexServer(plex_url, plex_token, timeout=30)
    section = plex.library.section(library_name)
    movies = section.all()
    if limit:
        movies = movies[:limit]

    session = requests.Session()
    rows = []
    counts = {"matched": 0, "fixable": 0, "unmatched": 0, "search_error": 0}
    total = len(movies)

    for i, movie in enumerate(movies, 1):
        title, year = movie.title, movie.year
        print(f"[{i}/{total}] {title} ({year or '?'})", file=sys.stderr)

        tmdb_id = existing_tmdb_id(movie)
        if tmdb_id is not None:
            counts["matched"] += 1
            rows.append({
                "status": "matched", "title": title, "year": year,
                "rating_key": movie.ratingKey, "existing_tmdb_id": tmdb_id,
                "candidate_tmdb_id": "", "candidate_title": "",
                "confidence": "", "notes": "",
            })
            continue

        try:
            results = tmdb_search(session, tmdb_key, title, year)
        except TMDbUnavailable as e:
            counts["search_error"] += 1
            rows.append({
                "status": "search_error", "title": title, "year": year,
                "rating_key": movie.ratingKey, "existing_tmdb_id": "",
                "candidate_tmdb_id": "", "candidate_title": "",
                "confidence": "", "notes": f"TMDb unreachable: {e}",
            })
            continue

        match = best_candidate(results, title, year)
        if match is None:
            counts["unmatched"] += 1
            rows.append({
                "status": "unmatched", "title": title, "year": year,
                "rating_key": movie.ratingKey, "existing_tmdb_id": "",
                "candidate_tmdb_id": "", "candidate_title": "",
                "confidence": "", "notes": "no candidate above similarity threshold",
            })
        else:
            cand, ratio, year_delta = match
            counts["fixable"] += 1
            rows.append({
                "status": "fixable", "title": title, "year": year,
                "rating_key": movie.ratingKey, "existing_tmdb_id": "",
                "candidate_tmdb_id": cand.get("id"),
                "candidate_title": cand.get("title") or cand.get("original_title"),
                "confidence": confidence_label(ratio, year_delta),
                "notes": f"title_similarity={ratio:.2f} year_delta={year_delta}",
            })

        if delay:
            time.sleep(delay)

    return rows, counts


def write_csv(rows, path):
    fieldnames = [
        "status", "title", "year", "rating_key", "existing_tmdb_id",
        "candidate_tmdb_id", "candidate_title", "confidence", "notes",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows, counts, total):
    print()
    print("=" * 60)
    print("TMDb Audit Summary")
    print("=" * 60)
    print(f"Total movies scanned:      {total}")
    print(f"Already matched:           {counts['matched']}")
    print(f"Potential fixes (review):  {counts['fixable']}")
    print(f"Unmatched (review/delete): {counts['unmatched']}")
    print(f"Search errors (retry):     {counts['search_error']}")
    print("=" * 60)

    fixable = [r for r in rows if r["status"] == "fixable"]
    if fixable:
        print("\nPotential Fixes (needs manual confirmation, none applied):")
        for r in fixable:
            print(
                f"  {r['title']} ({r['year']}) -> "
                f"TMDb #{r['candidate_tmdb_id']} \"{r['candidate_title']}\" "
                f"[{r['confidence']}] {r['notes']}"
            )

    unmatched = [r for r in rows if r["status"] == "unmatched"]
    if unmatched:
        print("\nUnmatched / deletion candidates:")
        for r in unmatched:
            print(f"  {r['title']} ({r['year']})")

    errors = [r for r in rows if r["status"] == "search_error"]
    if errors:
        print("\nSearch errors (re-run to retry these, TMDb was unreachable):")
        for r in errors:
            print(f"  {r['title']} ({r['year']}) - {r['notes']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--library", default="Movies", help="Plex library name (default: Movies)")
    parser.add_argument("--csv", default="tmdb_audit_report.csv", help="Output CSV path")
    parser.add_argument("--limit", type=int, default=None, help="Only scan the first N movies (testing)")
    parser.add_argument("--delay", type=float, default=0.25, help="Seconds to sleep between TMDb calls")
    args = parser.parse_args()

    plex_url = env_get("PLEX_URL")
    plex_token = env_get("PLEX_TOKEN")
    tmdb_key = env_get("TMDB_KEY")

    missing = [n for n, v in (("PLEX_URL", plex_url), ("PLEX_TOKEN", plex_token), ("TMDB_KEY", tmdb_key)) if not v]
    if missing:
        print(f"Missing required env var(s): {', '.join(missing)}", file=sys.stderr)
        return 1

    rows, counts = audit(plex_url, plex_token, tmdb_key, args.library, args.limit, args.delay)
    write_csv(rows, args.csv)
    print_summary(rows, counts, len(rows))
    print(f"\nFull report written to {args.csv}")
    print("No Plex data was modified. Review 'fixable' rows and apply matches")
    print("manually via Plex's own \"Fix Match\" UI using the candidate TMDb id.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

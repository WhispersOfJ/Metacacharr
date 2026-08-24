#!/usr/bin/env python3
"""Registers every list on mdblist.com/toplists/ as a native Radarr/Sonarr
import list, via Control Panel's existing /api/arr/{app}/import-list/add.

Radarr's build here has no native "MDBList" import-list implementation, but
neither does it need one: MDBList's own docs (docs.mdblist.com/docs/howto/
mdblist_to_radarr, docs.mdblist.com/docs/third-party/sonarr) confirm a plain
mdblist.com list URL is added straight into Radarr's "Custom Lists"
(RadarrListImport) and Sonarr's "Custom List" (CustomImport) - no MDBListarr
or other shim required. MDBListarr is a different tool (syncs an existing
Radarr/Sonarr library's watched-state back to MDBList) and doesn't apply to
this direction.

Each toplist gets classified by MDBList's own list-metadata endpoint
(movies/shows counts) rather than guessed from its URL or name, and routed
to Radarr and/or Sonarr accordingly - confirmed live that handing a
show-only list to Radarr's RadarrListImport (or a movie-only list to
Sonarr's CustomImport) fails validation outright ("no results were
returned"), it does not silently skip the mismatched items.

Registered lists are added with search_on_add=False, monitor="none" - items
sync into the library unmonitored, no automatic search is ever triggered.
Radarr/Sonarr then poll each list on their own schedule (RadarrListImport:
every 12h, CustomImport: every 6h) - this script only needs to run once (or
whenever mdblist.com/toplists/ picks up new lists), not continuously.
"""
import argparse
import re
import sys
import time
import urllib.parse

import requests

CONTROL_PANEL_URL = "http://localhost:8420"
TOPLISTS_URL = "https://mdblist.com/toplists/"
MDBLIST_API = "https://api.mdblist.com"

# mdblist.com's main site is Cloudflare-fronted - confirmed live a bare
# requests/urllib default User-Agent gets a real block, a browser-shaped
# header set does not.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# api.mdblist.com is a Django REST Framework API - confirmed live that
# sending the browser Accept header above (which prefers text/html) makes
# DRF's content negotiation return its browsable-API HTML page instead of
# JSON. Same User-Agent, but Accept must ask for JSON explicitly.
API_HEADERS = {**HEADERS, "Accept": "application/json"}

# Only the exact <user>/<slug> shape this script (and this repo's existing
# MDBLIST_URL_RE in control-panel/app.py) knows how to register - a handful
# of toplists.html links don't match this (e.g. /lists/official on its own,
# or three-segment /lists/official/movies/<slug> paths) and are skipped with
# a warning rather than guessed at.
LIST_HREF_RE = re.compile(r'href="(/lists/[^/"]+/[^/"]+)"')
LIST_URL_RE = re.compile(r"^https://mdblist\.com/lists/([^/]+)/([^/]+)/?$")


def mdblist_key() -> str:
    import os

    key = os.environ.get("MDBLIST_KEY")
    if not key:
        sys.exit("MDBLIST_KEY not set - source .env first (source .env && scripts/mdblist_toplists_import.py ...).")
    return key


def scrape_toplist_urls() -> list[str]:
    resp = requests.get(TOPLISTS_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    hrefs = sorted(set(LIST_HREF_RE.findall(resp.text)))
    if not hrefs:
        sys.exit(f"No list links found on {TOPLISTS_URL} - page structure may have changed.")
    return [urllib.parse.urljoin(TOPLISTS_URL, h) for h in hrefs]


def list_meta(url: str, key: str) -> dict | None:
    m = LIST_URL_RE.match(url)
    if not m:
        return None
    username, slug = m.groups()
    try:
        r = requests.get(f"{MDBLIST_API}/lists/{username}/{slug}", params={"apikey": key}, headers=API_HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        print(f"  ! metadata lookup failed for {url}: {e}", file=sys.stderr)
        return None
    if isinstance(data, dict) and data.get("error"):
        print(f"  ! {url}: {data['error']}", file=sys.stderr)
        return None
    if isinstance(data, list):
        if not data:
            print(f"  ! no metadata returned for {url}", file=sys.stderr)
            return None
        data = data[0]
    return data


def existing_import_lists(app: str) -> list[dict]:
    r = requests.get(f"{CONTROL_PANEL_URL}/api/arr/{app}/import-lists", timeout=20)
    r.raise_for_status()
    return r.json().get("items", [])


def already_registered(existing: list[dict], url_field: str, url: str) -> bool:
    target = url.rstrip("/")
    return any(
        f["name"] == url_field and (f.get("value") or "").rstrip("/") == target
        for lst in existing
        for f in lst.get("fields", [])
    )


def register(app: str, implementation: str, name: str, url_field: str, url: str) -> str:
    body = {
        "implementation": implementation,
        "name": name,
        "fields": {url_field: url},
        "search_on_add": False,
        "monitor": "none",
    }
    r = requests.post(f"{CONTROL_PANEL_URL}/api/arr/{app}/import-list/add", json=body, timeout=30)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", {}).get("message", r.text)
        except ValueError:
            detail = r.text
        raise RuntimeError(detail)
    return r.json().get("message", "added")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print what would be added, write nothing")
    args = ap.parse_args()

    key = mdblist_key()
    urls = scrape_toplist_urls()
    print(f"Found {len(urls)} candidate toplist URLs on {TOPLISTS_URL}.")

    radarr_existing = existing_import_lists("radarr")
    sonarr_existing = existing_import_lists("sonarr")

    added = skipped = unrecognized = failed = 0
    for url in urls:
        meta = list_meta(url, key)
        if meta is None:
            unrecognized += 1
            continue

        # user_name/slug (not just the list's display "name") disambiguate -
        # confirmed live that two different toplists.html entries both
        # render as "Latest TV Shows" (hdlists vs snoak), and Radarr/Sonarr
        # both reject a duplicate import-list name outright.
        title = meta.get("name") or meta.get("slug")
        name = f"MDBList Toplist: {title} ({meta.get('user_name')}/{meta.get('slug')})"
        movies, shows = meta.get("movies", 0), meta.get("shows", 0)
        if not movies and not shows:
            print(f"  = skip (empty list): {name}")
            skipped += 1
            continue

        targets = []
        if movies:
            targets.append(("radarr", "RadarrListImport", "url", radarr_existing))
        if shows:
            targets.append(("sonarr", "CustomImport", "baseUrl", sonarr_existing))

        for app, implementation, url_field, existing in targets:
            if already_registered(existing, url_field, url):
                print(f"  = skip (already on {app}): {name}")
                skipped += 1
                continue
            if args.dry_run:
                print(f"  + [dry-run] would add to {app}: {name} ({movies} movies, {shows} shows)")
                added += 1
                continue
            try:
                msg = register(app, implementation, name, url_field, url)
                print(f"  + {app}: {msg}")
                added += 1
            except RuntimeError as e:
                print(f"  ! {app} failed for {name}: {e}", file=sys.stderr)
                failed += 1

        time.sleep(0.3)  # polite pacing against mdblist.com's API

    print(f"\nDone: {added} added, {skipped} already present, {unrecognized} unrecognized URL shape, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

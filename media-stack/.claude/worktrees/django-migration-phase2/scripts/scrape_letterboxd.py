#!/usr/bin/env python3
"""Scrapes list URLs off Letterboxd's featured-lists page into a flat text
file, one absolute URL per line, for stack-letterboxd-radarr-list-random to
pick from.

/lists/featured/ is not in robots.txt's Disallow set (checked live:
User-agent: * only blocks sort/filter path segments - /by/, /on/, /tag/,
/genre/, /country/, /language/, /decade/, /films/year/, /films/*/size/large/,
/friends/, /popular/this/*, none of which apply here). The page is fully
server-rendered with no Cloudflare JS challenge (confirmed live), unlike
some other Letterboxd paths this stack's own Letterboxd-to-Radarr feature
already had to work around (control-panel/app.py's LETTERBOXD_HEADERS
comment) - still using the same full browser-shaped header set anyway,
since a bare requests default UA is the one thing confirmed to trip a
challenge on other paths.
"""
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

FEATURED_URL = "https://letterboxd.com/lists/featured/"
OUTPUT_FILE = Path.home() / ".cache" / "letterboxd_lists.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def list_urls_on_page(soup: BeautifulSoup, base_url: str) -> set[str]:
    urls = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # /<user>/list/<slug>/ - the shape every featured list link uses.
        # Anchored with leading/trailing slashes so this doesn't also match
        # a list's own sort/filter sub-paths (.../list/<slug>/by/rating/,
        # which robots.txt disallows) or a list's detail/edit sub-pages.
        parts = href.strip("/").split("/")
        if len(parts) == 3 and parts[1] == "list":
            urls.add(urljoin(base_url, href))
    return urls


def next_page_url(soup: BeautifulSoup, base_url: str) -> str | None:
    nxt = soup.find("a", class_="next")
    if nxt and nxt.get("href"):
        return urljoin(base_url, nxt["href"])
    return None


def scrape_all_featured_lists() -> list[str]:
    all_urls: set[str] = set()
    url = FEATURED_URL
    page_num = 1
    while url and page_num <= 10:  # same page-count discipline as the rest of this stack's Letterboxd scraping
        soup = fetch(url)
        found = list_urls_on_page(soup, url)
        if not found and page_num == 1:
            sys.exit(f"No list links found on {url} - Letterboxd's page structure may have changed.")
        all_urls |= found
        url = next_page_url(soup, url)
        page_num += 1
    return sorted(all_urls)


def main() -> None:
    urls = scrape_all_featured_lists()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text("\n".join(urls) + "\n")
    print(f"Wrote {len(urls)} list URLs to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

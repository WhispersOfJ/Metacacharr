"""Tests for letterboxd/scraping.py - the pure HTML-parsing/regex helpers
ported from control-panel/services/letterboxd/scraping.py. These functions
have no FastAPI dependency, so the only behavioral change to verify is
core.responses.fail() -> core.api_base.ServiceError on fetch_page's error
path."""
import pytest

from core.api_base import ServiceError
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
    scrape_title_year,
)


def test_letterboxd_tmdb_re_extracts_id():
    html = '<a href="https://www.themoviedb.org/movie/603-the-matrix">TMDb</a>'
    match = LETTERBOXD_TMDB_RE.search(html)
    assert match.group(1) == "603"


def test_letterboxd_tmdb_re_no_match_returns_none():
    assert LETTERBOXD_TMDB_RE.search("<html>no tmdb link here</html>") is None


def test_letterboxd_item_slug_re_extracts_slugs():
    html = '<li data-item-slug="oppenheimer"></li><li data-item-slug="the-matrix"></li>'
    assert LETTERBOXD_ITEM_SLUG_RE.findall(html) == ["oppenheimer", "the-matrix"]


def test_letterboxd_list_page_re_extracts_page_numbers():
    html = '<a href="/user/list/foo/page/2/">2</a><a href="/user/list/foo/page/5/">5</a>'
    assert LETTERBOXD_LIST_PAGE_RE.findall(html) == ["2", "5"]


@pytest.mark.parametrize("url", [
    "https://letterboxd.com/bear/list/my-list/",
    "https://letterboxd.com/bear/watchlist/",
    "https://letterboxd.com/bear/films/",
    "https://letterboxd.com/actor/some-actor/",
    "https://letterboxd.com/films/in/some-collection/",
    "https://letterboxd.com/films/",
])
def test_letterboxd_grid_re_matches_recognized_shapes(url):
    assert LETTERBOXD_GRID_RE.match(url)


def test_letterboxd_grid_re_rejects_unrecognized_shape():
    # A bare domain root, or a path with no owner/list segment at all,
    # doesn't match any of the recognized grid-page shapes.
    assert LETTERBOXD_GRID_RE.match("https://letterboxd.com/") is None
    assert LETTERBOXD_GRID_RE.match("https://example.com/bear/watchlist/") is None


@pytest.mark.parametrize("url", [
    "https://letterboxd.com/bear/list/my-list/by/rating/",
    "https://letterboxd.com/bear/list/my-list/genre/horror/",
    "https://letterboxd.com/bear/list/my-list/decade/1990s/",
    "https://letterboxd.com/films/popular/this/week/",
    "https://letterboxd.com/films/year/2024/",
    "https://letterboxd.com/bear/films/year/2024/",
    "https://letterboxd.com/bear/films/rated/size/large/",
])
def test_letterboxd_disallowed_re_flags_sort_filter_urls(url):
    assert LETTERBOXD_DISALLOWED_RE.search(url + "/")


def test_letterboxd_disallowed_re_allows_plain_url():
    assert LETTERBOXD_DISALLOWED_RE.search("https://letterboxd.com/bear/watchlist//") is None


def test_scrape_slugs_with_ratings_matches_per_item_segment():
    html = (
        '<li data-item-slug="rated-film">'
        '<span class="rating -micro -darker rated-8"></span>'
        '</li>'
        '<li data-item-slug="unrated-film"></li>'
    )
    result = scrape_slugs_with_ratings(html)
    assert result == [("rated-film", 8), ("unrated-film", None)]


def test_scrape_slugs_with_ratings_dedupes_repeated_slugs():
    html = (
        '<li data-item-slug="dup-film"></li>'
        '<li data-item-slug="dup-film"></li>'
    )
    result = scrape_slugs_with_ratings(html)
    assert result == [("dup-film", None)]


def test_scrape_title_year_extracts_from_og_title():
    html = '<meta property="og:title" content="Oppenheimer (2023)">'
    assert scrape_title_year(html) == ("Oppenheimer", 2023)


def test_scrape_title_year_no_match_returns_none():
    assert scrape_title_year("<html>no og:title here</html>") is None


def test_scrape_tags_extracts_and_dedupes():
    html = (
        '<ul class="tags">'
        '<li><a href="/bear/tag/press-screening/films/"></a></li>'
        '<li><a href="/bear/tag/rewatch/films/"></a></li>'
        '<li><a href="/bear/tag/press-screening/films/"></a></li>'
        '</ul>'
    )
    assert scrape_tags(html) == ["press-screening", "rewatch"]


def test_scrape_tags_empty_when_no_tags():
    assert scrape_tags("<html>no tags here</html>") == []


def test_fetch_page_returns_html(httpx_mock):
    httpx_mock.add_response(url="https://letterboxd.com/film/oppenheimer/", text="<html>ok</html>")
    assert fetch_page("https://letterboxd.com/film/oppenheimer/") == "<html>ok</html>"


def test_fetch_page_raises_service_error_on_http_failure(httpx_mock):
    httpx_mock.add_response(url="https://letterboxd.com/film/nonexistent/", status_code=404)
    with pytest.raises(ServiceError):
        fetch_page("https://letterboxd.com/film/nonexistent/")


def test_fetch_page_or_none_returns_none_on_failure(httpx_mock):
    httpx_mock.add_response(url="https://letterboxd.com/film/nonexistent/", status_code=404)
    assert fetch_page_or_none("https://letterboxd.com/film/nonexistent/") is None


def test_fetch_page_or_none_returns_html_on_success(httpx_mock):
    httpx_mock.add_response(url="https://letterboxd.com/film/oppenheimer/", text="<html>ok</html>")
    assert fetch_page_or_none("https://letterboxd.com/film/oppenheimer/") == "<html>ok</html>"

"""Tests for letterboxd/cache.py - the slug -> TMDb id dedup cache and the
TV-crossover lookup, ported from control-panel/services/letterboxd/cache.py
onto the Django ORM."""
import pytest

from core.models import LetterboxdTmdbCache
from letterboxd.cache import resolve_tmdb_ids, resolve_tv_crossovers


@pytest.mark.django_db
def test_resolve_tmdb_ids_uses_cache_hit_without_fetching(monkeypatch):
    LetterboxdTmdbCache.objects.create(slug="oppenheimer", tmdb_id=872585, media_type="movie")

    def fail_if_called(url):
        raise AssertionError("fetch_page should not be called for a cached slug")

    monkeypatch.setattr("letterboxd.cache.fetch_page", fail_if_called)

    tmdb_ids, unmatched = resolve_tmdb_ids(["oppenheimer"])

    assert tmdb_ids == [872585]
    assert unmatched == []


@pytest.mark.django_db
def test_resolve_tmdb_ids_fetches_and_caches_on_miss(monkeypatch):
    monkeypatch.setattr(
        "letterboxd.cache.fetch_page",
        lambda url: '<a href="https://www.themoviedb.org/movie/603">TMDb</a>',
    )

    tmdb_ids, unmatched = resolve_tmdb_ids(["the-matrix"])

    assert tmdb_ids == [603]
    assert unmatched == []
    row = LetterboxdTmdbCache.objects.get(slug="the-matrix")
    assert row.tmdb_id == 603


@pytest.mark.django_db
def test_resolve_tmdb_ids_caches_unmatched_slug_as_none(monkeypatch):
    monkeypatch.setattr("letterboxd.cache.fetch_page", lambda url: "<html>no tmdb link</html>")

    tmdb_ids, unmatched = resolve_tmdb_ids(["obscure-film"])

    assert tmdb_ids == []
    assert unmatched == ["obscure-film"]
    row = LetterboxdTmdbCache.objects.get(slug="obscure-film")
    assert row.tmdb_id is None


@pytest.mark.django_db
def test_resolve_tmdb_ids_reuses_cached_unmatched_without_refetch(monkeypatch):
    LetterboxdTmdbCache.objects.create(slug="obscure-film", tmdb_id=None, media_type="movie")

    def fail_if_called(url):
        raise AssertionError("fetch_page should not be called for a cached-unmatched slug")

    monkeypatch.setattr("letterboxd.cache.fetch_page", fail_if_called)

    tmdb_ids, unmatched = resolve_tmdb_ids(["obscure-film"])

    assert tmdb_ids == []
    assert unmatched == ["obscure-film"]


@pytest.mark.django_db
def test_resolve_tmdb_ids_preserves_slug_order():
    LetterboxdTmdbCache.objects.create(slug="b-film", tmdb_id=2)
    LetterboxdTmdbCache.objects.create(slug="a-film", tmdb_id=1)

    tmdb_ids, _ = resolve_tmdb_ids(["b-film", "a-film"])

    assert tmdb_ids == [2, 1]


def test_resolve_tv_crossovers_matches_exact_title_and_year(httpx_mock, monkeypatch):
    monkeypatch.setattr(
        "letterboxd.cache.scrape_title_year",
        lambda html: ("Chernobyl", 2019),
    )
    httpx_mock.add_response(url="https://letterboxd.com/film/chernobyl/", text="<html>ok</html>")
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/series/lookup?term=Chernobyl",
        json=[{"title": "Chernobyl", "year": 2019, "tvdbId": 361744}],
    )

    matches, still_unmatched = resolve_tv_crossovers(["chernobyl"])

    assert matches == [{"slug": "chernobyl", "title": "Chernobyl", "year": 2019, "tvdb_id": 361744}]
    assert still_unmatched == []


def test_resolve_tv_crossovers_page_fetch_failure_stays_unmatched(httpx_mock):
    httpx_mock.add_response(url="https://letterboxd.com/film/some-film/", status_code=404)

    matches, still_unmatched = resolve_tv_crossovers(["some-film"])

    assert matches == []
    assert still_unmatched == ["some-film"]


def test_resolve_tv_crossovers_no_og_title_stays_unmatched(httpx_mock):
    httpx_mock.add_response(url="https://letterboxd.com/film/no-og-title/", text="<html>nothing</html>")

    matches, still_unmatched = resolve_tv_crossovers(["no-og-title"])

    assert matches == []
    assert still_unmatched == ["no-og-title"]


def test_resolve_tv_crossovers_sonarr_lookup_no_exact_match_stays_unmatched(httpx_mock, monkeypatch):
    monkeypatch.setattr("letterboxd.cache.scrape_title_year", lambda html: ("Some Show", 2020))
    httpx_mock.add_response(url="https://letterboxd.com/film/some-show/", text="<html>ok</html>")
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/series/lookup?term=Some+Show",
        json=[{"title": "Some Show", "year": 2019, "tvdbId": 12345}],  # wrong year
    )

    matches, still_unmatched = resolve_tv_crossovers(["some-show"])

    assert matches == []
    assert still_unmatched == ["some-show"]

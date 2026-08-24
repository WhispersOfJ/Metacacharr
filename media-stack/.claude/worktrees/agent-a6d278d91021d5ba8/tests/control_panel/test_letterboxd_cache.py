from unittest.mock import MagicMock

import httpx


def test_resolve_tmdb_ids_skips_cached_slugs(cp_main_app, monkeypatch):
    from models.letterboxd_cache import LetterboxdTmdbCache
    from services.letterboxd.cache import resolve_tmdb_ids

    db = cp_main_app.SessionLocal()
    db.add(LetterboxdTmdbCache(slug="the-matrix", tmdb_id=603, media_type="movie"))
    db.commit()

    fetch_calls = []

    def fake_get(url, headers=None, timeout=None, follow_redirects=None, **kwargs):
        fetch_calls.append(url)
        return MagicMock(text='themoviedb.org/movie/27205', raise_for_status=MagicMock())

    monkeypatch.setattr(httpx, "get", fake_get)

    tmdb_ids, unmatched = resolve_tmdb_ids(db, ["the-matrix", "inception"])

    assert tmdb_ids == [603, 27205]
    assert unmatched == []
    # only "inception" should have triggered a real fetch - "the-matrix" was cached
    assert len(fetch_calls) == 1
    assert "inception" in fetch_calls[0]

    cached = db.query(LetterboxdTmdbCache).filter_by(slug="inception").one()
    assert cached.tmdb_id == 27205
    db.close()


def test_resolve_tmdb_ids_caches_unmatched_slugs_too(cp_main_app, monkeypatch):
    from models.letterboxd_cache import LetterboxdTmdbCache
    from services.letterboxd.cache import resolve_tmdb_ids

    db = cp_main_app.SessionLocal()

    def fake_get(url, headers=None, timeout=None, follow_redirects=None, **kwargs):
        return MagicMock(text='<html>no tmdb link here</html>', raise_for_status=MagicMock())

    monkeypatch.setattr(httpx, "get", fake_get)

    tmdb_ids, unmatched = resolve_tmdb_ids(db, ["some-unmatched-short"])

    assert tmdb_ids == []
    assert unmatched == ["some-unmatched-short"]
    cached = db.query(LetterboxdTmdbCache).filter_by(slug="some-unmatched-short").one()
    assert cached.tmdb_id is None
    db.close()

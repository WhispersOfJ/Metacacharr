"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/posters/candidates.py, ported from app.py. Pure unit tests
against each provider's lookup function plus resolve_poster_candidates'
fallback-order logic - no FastAPI/auth involved.
"""
import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

CONTROL_PANEL_DIR = Path(__file__).resolve().parent.parent.parent / "control-panel"


@pytest.fixture
def candidates(monkeypatch):
    sys.path.insert(0, str(CONTROL_PANEL_DIR))
    sys.modules.pop("services.posters.candidates", None)
    try:
        module = importlib.import_module("services.posters.candidates")
        monkeypatch.setattr(module, "TMDB_KEY", "test-tmdb-key")
        monkeypatch.setattr(module, "FANART_KEY", "test-fanart-key")
        monkeypatch.setattr(module, "TVDB_KEY", "test-tvdb-key")
        yield module
    finally:
        sys.modules.pop("services.posters.candidates", None)
        sys.path.remove(str(CONTROL_PANEL_DIR))


def _resp(data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("err", request=None, response=resp)
    return resp


def _meta(tmdb=None, tvdb=None, imdb=None):
    guids = []
    if tmdb is not None:
        guids.append({"id": f"tmdb://{tmdb}"})
    if tvdb is not None:
        guids.append({"id": f"tvdb://{tvdb}"})
    if imdb is not None:
        guids.append({"id": f"imdb://{imdb}"})
    return {"Guid": guids}


def test_tmdb_id_for_item_prefers_direct_guid(candidates):
    assert candidates.tmdb_id_for_item(_meta(tmdb=123), "movie") == 123


def test_tmdb_id_for_item_falls_back_to_imdb_find(candidates, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _resp({"movie_results": [{"id": 999}]}))
    assert candidates.tmdb_id_for_item(_meta(imdb="tt123"), "movie") == 999


def test_tmdb_id_for_item_returns_none_when_no_guid_matches(candidates, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _resp({}))
    assert candidates.tmdb_id_for_item(_meta(), "movie") is None


def test_tmdb_top_posters_ranks_by_votes(candidates, monkeypatch):
    data = {"posters": [
        {"file_path": "/low.jpg", "vote_average": 5.0, "vote_count": 10},
        {"file_path": "/high.jpg", "vote_average": 9.0, "vote_count": 100},
    ]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _resp(data))
    top = candidates.tmdb_top_posters(1, "movie", limit=3)
    assert top[0]["url"].endswith("/high.jpg")


def test_tmdb_top_posters_empty_on_http_error(candidates, monkeypatch):
    def fake_get(*a, **k):
        raise httpx.HTTPError("boom")
    monkeypatch.setattr(httpx, "get", fake_get)
    assert candidates.tmdb_top_posters(1, "movie") == []


def test_fanart_ids_for_item_extracts_both(candidates):
    tmdb_id, tvdb_id = candidates.fanart_ids_for_item(_meta(tmdb=1, tvdb=2))
    assert (tmdb_id, tvdb_id) == (1, 2)


def test_imdb_id_for_item_extracts_imdb(candidates):
    assert candidates.imdb_id_for_item(_meta(imdb="tt42")) == "tt42"


def test_fanart_top_posters_returns_empty_without_id(candidates):
    assert candidates.fanart_top_posters("movie", None, None) == []


def test_fanart_top_posters_returns_empty_on_404(candidates, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _resp({}, status_code=404))
    assert candidates.fanart_top_posters("movie", 1, None) == []


def test_fanart_top_posters_ranks_by_likes_preferring_english(candidates, monkeypatch):
    data = {"movieposter": [
        {"url": "a.jpg", "likes": "5", "lang": "de"},
        {"url": "b.jpg", "likes": "5", "lang": "en"},
    ]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _resp(data))
    top = candidates.fanart_top_posters("movie", 1, None, limit=2)
    assert top[0]["url"] == "b.jpg"


def test_tvdb_top_posters_returns_empty_without_id(candidates):
    assert candidates.tvdb_top_posters("show", None) == []


def test_tvdb_top_posters_returns_empty_without_token(candidates, monkeypatch):
    monkeypatch.setattr(candidates, "TVDB_KEY", None)
    assert candidates.tvdb_top_posters("show", 5) == []


def test_tvdb_top_posters_shows_uses_series_artworks(candidates, monkeypatch):
    def fake_post(*a, **k):
        return _resp({"data": {"token": "tok"}})

    def fake_get(url, headers=None, params=None, timeout=None):
        return _resp({"data": {"artworks": [{"image": "poster.jpg", "score": 10, "language": "en"}]}})

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)
    top = candidates.tvdb_top_posters("show", 5)
    assert top[0]["url"] == "poster.jpg"


def test_omdb_top_posters_empty_without_key(candidates, monkeypatch):
    monkeypatch.delenv("OMDB_KEY", raising=False)
    assert candidates.omdb_top_posters("tt1") == []


def test_omdb_top_posters_empty_on_na_poster(candidates, monkeypatch):
    monkeypatch.setenv("OMDB_KEY", "test-omdb-key")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _resp({"Response": "True", "Poster": "N/A"}))
    assert candidates.omdb_top_posters("tt1") == []


def test_omdb_top_posters_returns_single_candidate(candidates, monkeypatch):
    monkeypatch.setenv("OMDB_KEY", "test-omdb-key")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _resp({"Response": "True", "Poster": "http://x/p.jpg"}))
    top = candidates.omdb_top_posters("tt1")
    assert top == [{"url": "http://x/p.jpg", "label": "OMDb"}]


def test_tvmaze_top_posters_empty_for_movies(candidates):
    assert candidates.tvmaze_top_posters("movie", "tt1") == []


def test_tvmaze_top_posters_returns_image(candidates, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _resp({"image": {"original": "show.jpg"}}))
    top = candidates.tvmaze_top_posters("show", "tt1")
    assert top == [{"url": "show.jpg", "label": "TVmaze"}]


def test_resolve_poster_candidates_uses_primary_source(candidates, monkeypatch):
    monkeypatch.setattr(candidates, "tmdb_id_for_item", lambda meta, mt: 1)
    monkeypatch.setattr(candidates, "tmdb_top_posters", lambda tmdb_id, mt, limit=3: [{"url": "tmdb.jpg", "label": "x"}])
    src, cands = candidates.resolve_poster_candidates(_meta(), "movie", "tmdb")
    assert src == "tmdb"
    assert cands[0]["url"] == "tmdb.jpg"


def test_resolve_poster_candidates_falls_back_when_primary_empty(candidates, monkeypatch):
    monkeypatch.setattr(candidates, "tmdb_id_for_item", lambda meta, mt: None)
    monkeypatch.setattr(candidates, "fanart_ids_for_item", lambda meta: (1, None))
    monkeypatch.setattr(candidates, "fanart_top_posters", lambda mt, tmdb_id, tvdb_id, limit=3: [{"url": "fanart.jpg", "label": "x"}])
    src, cands = candidates.resolve_poster_candidates(_meta(), "movie", "tmdb")
    assert src == "fanart"


def test_resolve_poster_candidates_returns_none_when_all_sources_empty(candidates, monkeypatch):
    monkeypatch.setattr(candidates, "TMDB_KEY", None)
    monkeypatch.setattr(candidates, "FANART_KEY", None)
    monkeypatch.setattr(candidates, "TVDB_KEY", None)
    monkeypatch.delenv("OMDB_KEY", raising=False)
    src, cands = candidates.resolve_poster_candidates(_meta(), "movie", "tmdb")
    assert src is None
    assert cands == []

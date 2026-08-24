import pytest

from core.api_base import ServiceError
from posters import candidates


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    """TMDB_KEY/FANART_KEY/TVDB_KEY/OMDB_KEY are empty by default in the
    test environment (module-level os.environ.get() at import time) -
    patch the posters.candidates module attributes directly, same pattern
    as plex/tests/test_services.py's _plex_config fixture."""
    monkeypatch.setattr(candidates, "TMDB_KEY", "test-tmdb-key")
    monkeypatch.setattr(candidates, "FANART_KEY", "test-fanart-key")
    monkeypatch.setattr(candidates, "TVDB_KEY", "test-tvdb-key")
    monkeypatch.delenv("OMDB_KEY", raising=False)


def test_omdb_key_reads_env(monkeypatch):
    monkeypatch.delenv("OMDB_KEY", raising=False)
    assert candidates.omdb_key() is None
    monkeypatch.setenv("OMDB_KEY", "x")
    assert candidates.omdb_key() == "x"


class TestTmdbGet:
    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(candidates, "TMDB_KEY", None)
        with pytest.raises(ServiceError):
            candidates.tmdb_get("/movie/1")

    def test_success(self, httpx_mock):
        httpx_mock.add_response(url="https://api.themoviedb.org/3/movie/1?api_key=test-tmdb-key", json={"id": 1})
        assert candidates.tmdb_get("/movie/1") == {"id": 1}

    def test_raises_on_http_error(self, httpx_mock):
        httpx_mock.add_response(url="https://api.themoviedb.org/3/movie/1?api_key=test-tmdb-key", status_code=500)
        with pytest.raises(Exception):
            candidates.tmdb_get("/movie/1")


class TestTmdbIdForItem:
    def test_direct_tmdb_guid(self):
        meta = {"Guid": [{"id": "tmdb://123"}]}
        assert candidates.tmdb_id_for_item(meta, "movie") == 123

    def test_invalid_tmdb_guid_falls_through(self):
        meta = {"Guid": [{"id": "tmdb://not-a-number"}]}
        assert candidates.tmdb_id_for_item(meta, "movie") is None

    def test_tvdb_fallback_for_show(self, httpx_mock):
        meta = {"Guid": [{"id": "tvdb://55"}]}
        httpx_mock.add_response(
            url="https://api.themoviedb.org/3/find/55?api_key=test-tmdb-key&external_source=tvdb_id",
            json={"tv_results": [{"id": 999}]},
        )
        assert candidates.tmdb_id_for_item(meta, "show") == 999

    def test_tvdb_fallback_http_error_is_swallowed(self, httpx_mock):
        meta = {"Guid": [{"id": "tvdb://55"}]}
        httpx_mock.add_response(
            url="https://api.themoviedb.org/3/find/55?api_key=test-tmdb-key&external_source=tvdb_id",
            status_code=500,
        )
        assert candidates.tmdb_id_for_item(meta, "show") is None

    def test_imdb_fallback_for_movie(self, httpx_mock):
        meta = {"Guid": [{"id": "imdb://tt1"}]}
        httpx_mock.add_response(
            url="https://api.themoviedb.org/3/find/tt1?api_key=test-tmdb-key&external_source=imdb_id",
            json={"movie_results": [{"id": 42}]},
        )
        assert candidates.tmdb_id_for_item(meta, "movie") == 42

    def test_no_guids_returns_none(self):
        assert candidates.tmdb_id_for_item({}, "movie") is None


class TestTmdbTopPosters:
    def test_success_sorted_best_first(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.themoviedb.org/3/movie/1/images?api_key=test-tmdb-key&include_image_language=en%2Cnull",
            json={"posters": [
                {"file_path": "/low.jpg", "vote_average": 1.0, "vote_count": 2},
                {"file_path": "/high.jpg", "vote_average": 9.0, "vote_count": 20},
            ]},
        )
        result = candidates.tmdb_top_posters(1, "movie", limit=3)
        assert result[0]["url"] == "https://image.tmdb.org/t/p/original/high.jpg"
        assert "★9.0" in result[0]["label"]

    def test_http_error_returns_empty(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.themoviedb.org/3/tv/1/images?api_key=test-tmdb-key&include_image_language=en%2Cnull",
            status_code=500,
        )
        assert candidates.tmdb_top_posters(1, "show", limit=3) == []


class TestFanartIdsForItem:
    def test_extracts_both_ids(self):
        meta = {"Guid": [{"id": "tmdb://1"}, {"id": "tvdb://2"}]}
        assert candidates.fanart_ids_for_item(meta) == (1, 2)

    def test_invalid_ids_are_skipped(self):
        meta = {"Guid": [{"id": "tmdb://bad"}, {"id": "tvdb://also-bad"}]}
        assert candidates.fanart_ids_for_item(meta) == (None, None)


class TestImdbIdForItem:
    def test_found(self):
        assert candidates.imdb_id_for_item({"Guid": [{"id": "imdb://tt5"}]}) == "tt5"

    def test_missing(self):
        assert candidates.imdb_id_for_item({}) is None


class TestFanartTopPosters:
    def test_no_id_returns_empty(self):
        assert candidates.fanart_top_posters("movie", None, None) == []

    def test_movie_success(self, httpx_mock):
        httpx_mock.add_response(
            url="https://webservice.fanart.tv/v3/movies/1?api_key=test-fanart-key",
            json={"movieposter": [
                {"url": "https://a", "likes": "1", "lang": "de"},
                {"url": "https://b", "likes": "5", "lang": "en"},
            ]},
        )
        result = candidates.fanart_top_posters("movie", 1, None, limit=3)
        assert result[0]["url"] == "https://b"

    def test_show_success_uses_tvdb_id(self, httpx_mock):
        httpx_mock.add_response(
            url="https://webservice.fanart.tv/v3/tv/2?api_key=test-fanart-key",
            json={"tvposter": [{"url": "https://c", "likes": "3", "lang": "en"}]},
        )
        result = candidates.fanart_top_posters("show", None, 2, limit=3)
        assert result[0]["url"] == "https://c"

    def test_404_returns_empty(self, httpx_mock):
        httpx_mock.add_response(url="https://webservice.fanart.tv/v3/movies/1?api_key=test-fanart-key", status_code=404)
        assert candidates.fanart_top_posters("movie", 1, None) == []

    def test_http_error_returns_empty(self, httpx_mock):
        httpx_mock.add_response(url="https://webservice.fanart.tv/v3/movies/1?api_key=test-fanart-key", status_code=500)
        assert candidates.fanart_top_posters("movie", 1, None) == []


class TestTvdbToken:
    def test_no_key_returns_none(self, monkeypatch):
        monkeypatch.setattr(candidates, "TVDB_KEY", None)
        assert candidates.tvdb_token() is None

    def test_login_success_caches(self, httpx_mock, monkeypatch):
        monkeypatch.setattr(candidates, "_TVDB_TOKEN", {"value": None, "expires_at": 0})
        httpx_mock.add_response(
            url="https://api4.thetvdb.com/v4/login", method="POST", json={"data": {"token": "tok"}},
        )
        assert candidates.tvdb_token() == "tok"
        # Second call reuses the cached token - no second HTTP request queued.
        assert candidates.tvdb_token() == "tok"

    def test_login_failure_returns_none(self, httpx_mock, monkeypatch):
        monkeypatch.setattr(candidates, "_TVDB_TOKEN", {"value": None, "expires_at": 0})
        httpx_mock.add_response(url="https://api4.thetvdb.com/v4/login", method="POST", status_code=500)
        assert candidates.tvdb_token() is None


class TestTvdbTopPosters:
    def test_no_id_returns_empty(self):
        assert candidates.tvdb_top_posters("show", None) == []

    def test_no_token_returns_empty(self, monkeypatch):
        monkeypatch.setattr(candidates, "tvdb_token", lambda: None)
        assert candidates.tvdb_top_posters("show", 5) == []

    def test_movie_success(self, httpx_mock, monkeypatch):
        monkeypatch.setattr(candidates, "tvdb_token", lambda: "tok")
        httpx_mock.add_response(
            url="https://api4.thetvdb.com/v4/movies/5/extended",
            json={"data": {"artworks": [
                {"type": 14, "image": "https://poster", "score": 3, "language": "eng"},
                {"type": 1, "image": "https://other", "score": 99},
            ]}},
        )
        result = candidates.tvdb_top_posters("movie", 5)
        assert result == [{"url": "https://poster", "label": "★3 (eng)"}]

    def test_show_success(self, httpx_mock, monkeypatch):
        monkeypatch.setattr(candidates, "tvdb_token", lambda: "tok")
        httpx_mock.add_response(
            url="https://api4.thetvdb.com/v4/series/5/artworks?type=2",
            json={"data": {"artworks": [{"image": "https://s", "score": 7, "language": "eng"}]}},
        )
        result = candidates.tvdb_top_posters("show", 5)
        assert result == [{"url": "https://s", "label": "★7 (eng)"}]

    def test_404_returns_empty(self, httpx_mock, monkeypatch):
        monkeypatch.setattr(candidates, "tvdb_token", lambda: "tok")
        httpx_mock.add_response(url="https://api4.thetvdb.com/v4/movies/5/extended", status_code=404)
        assert candidates.tvdb_top_posters("movie", 5) == []

    def test_http_error_returns_empty(self, httpx_mock, monkeypatch):
        monkeypatch.setattr(candidates, "tvdb_token", lambda: "tok")
        httpx_mock.add_response(url="https://api4.thetvdb.com/v4/movies/5/extended", status_code=500)
        assert candidates.tvdb_top_posters("movie", 5) == []


class TestOmdbTopPosters:
    def test_no_id_returns_empty(self, monkeypatch):
        monkeypatch.setenv("OMDB_KEY", "x")
        assert candidates.omdb_top_posters(None) == []

    def test_no_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("OMDB_KEY", raising=False)
        assert candidates.omdb_top_posters("tt1") == []

    def test_success(self, httpx_mock, monkeypatch):
        monkeypatch.setenv("OMDB_KEY", "x")
        httpx_mock.add_response(
            url="https://www.omdbapi.com/?i=tt1&apikey=x",
            json={"Response": "True", "Poster": "https://p"},
        )
        assert candidates.omdb_top_posters("tt1") == [{"url": "https://p", "label": "OMDb"}]

    def test_unmatched_returns_empty(self, httpx_mock, monkeypatch):
        monkeypatch.setenv("OMDB_KEY", "x")
        httpx_mock.add_response(url="https://www.omdbapi.com/?i=tt1&apikey=x", json={"Response": "False"})
        assert candidates.omdb_top_posters("tt1") == []

    def test_na_poster_returns_empty(self, httpx_mock, monkeypatch):
        monkeypatch.setenv("OMDB_KEY", "x")
        httpx_mock.add_response(url="https://www.omdbapi.com/?i=tt1&apikey=x", json={"Response": "True", "Poster": "N/A"})
        assert candidates.omdb_top_posters("tt1") == []

    def test_http_error_returns_empty(self, httpx_mock, monkeypatch):
        monkeypatch.setenv("OMDB_KEY", "x")
        httpx_mock.add_response(url="https://www.omdbapi.com/?i=tt1&apikey=x", status_code=500)
        assert candidates.omdb_top_posters("tt1") == []


class TestTvmazeTopPosters:
    def test_movie_returns_empty(self):
        assert candidates.tvmaze_top_posters("movie", "tt1") == []

    def test_no_id_returns_empty(self):
        assert candidates.tvmaze_top_posters("show", None) == []

    def test_success(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.tvmaze.com/lookup/shows?imdb=tt1",
            json={"image": {"original": "https://img"}},
        )
        assert candidates.tvmaze_top_posters("show", "tt1") == [{"url": "https://img", "label": "TVmaze"}]

    def test_404_returns_empty(self, httpx_mock):
        httpx_mock.add_response(url="https://api.tvmaze.com/lookup/shows?imdb=tt1", status_code=404)
        assert candidates.tvmaze_top_posters("show", "tt1") == []

    def test_no_image_returns_empty(self, httpx_mock):
        httpx_mock.add_response(url="https://api.tvmaze.com/lookup/shows?imdb=tt1", json={"image": None})
        assert candidates.tvmaze_top_posters("show", "tt1") == []

    def test_empty_body_returns_empty(self, httpx_mock):
        httpx_mock.add_response(url="https://api.tvmaze.com/lookup/shows?imdb=tt1", text="null")
        assert candidates.tvmaze_top_posters("show", "tt1") == []

    def test_http_error_returns_empty(self, httpx_mock):
        httpx_mock.add_response(url="https://api.tvmaze.com/lookup/shows?imdb=tt1", status_code=500)
        assert candidates.tvmaze_top_posters("show", "tt1") == []


class TestResolvePosterCandidates:
    def test_primary_source_hit(self, monkeypatch):
        monkeypatch.setattr(candidates, "tmdb_id_for_item", lambda meta, mt: 1)
        monkeypatch.setattr(candidates, "tmdb_top_posters", lambda tmdb_id, mt, limit=3: [{"url": "https://x", "label": "l"}])
        used, result = candidates.resolve_poster_candidates({}, "movie", "tmdb")
        assert used == "tmdb"
        assert result == [{"url": "https://x", "label": "l"}]

    def test_falls_back_when_primary_empty(self, monkeypatch):
        monkeypatch.setattr(candidates, "tmdb_id_for_item", lambda meta, mt: None)
        monkeypatch.setattr(candidates, "fanart_ids_for_item", lambda meta: (1, None))
        monkeypatch.setattr(candidates, "fanart_top_posters", lambda mt, t, v, limit=3: [{"url": "https://f", "label": "l"}])
        used, result = candidates.resolve_poster_candidates({}, "movie", "tmdb")
        assert used == "fanart"
        assert result

    def test_missing_key_source_is_skipped(self, monkeypatch):
        monkeypatch.setattr(candidates, "TMDB_KEY", None)
        monkeypatch.setattr(candidates, "FANART_KEY", None)
        monkeypatch.setattr(candidates, "TVDB_KEY", None)
        monkeypatch.delenv("OMDB_KEY", raising=False)
        monkeypatch.setattr(candidates, "tvmaze_top_posters", lambda mt, imdb, limit=3: [])
        used, result = candidates.resolve_poster_candidates({}, "movie", "tmdb")
        assert used is None
        assert result == []

    def test_no_source_has_candidates_returns_none(self, monkeypatch):
        monkeypatch.setattr(candidates, "tmdb_id_for_item", lambda meta, mt: None)
        monkeypatch.setattr(candidates, "fanart_ids_for_item", lambda meta: (None, None))
        monkeypatch.setattr(candidates, "fanart_top_posters", lambda mt, t, v, limit=3: [])
        monkeypatch.setattr(candidates, "tvdb_top_posters", lambda mt, t, limit=3: [])
        monkeypatch.setenv("OMDB_KEY", "x")
        monkeypatch.setattr(candidates, "omdb_top_posters", lambda imdb, limit=3: [])
        monkeypatch.setattr(candidates, "tvmaze_top_posters", lambda mt, imdb, limit=3: [])
        used, result = candidates.resolve_poster_candidates({}, "movie", "tmdb")
        assert used is None
        assert result == []

    def test_omdb_as_primary_source(self, monkeypatch):
        monkeypatch.setenv("OMDB_KEY", "x")
        monkeypatch.setattr(candidates, "imdb_id_for_item", lambda meta: "tt1")
        monkeypatch.setattr(candidates, "omdb_top_posters", lambda imdb, limit=3: [{"url": "https://o", "label": "OMDb"}])
        used, result = candidates.resolve_poster_candidates({}, "movie", "omdb")
        assert used == "omdb"

    def test_tvmaze_as_primary_source(self, monkeypatch):
        monkeypatch.setattr(candidates, "imdb_id_for_item", lambda meta: "tt1")
        monkeypatch.setattr(candidates, "tvmaze_top_posters", lambda mt, imdb, limit=3: [{"url": "https://t", "label": "TVmaze"}])
        used, result = candidates.resolve_poster_candidates({}, "show", "tvmaze")
        assert used == "tvmaze"

    def test_tvdb_as_primary_source(self, monkeypatch):
        monkeypatch.setattr(candidates, "fanart_ids_for_item", lambda meta: (None, 2))
        monkeypatch.setattr(candidates, "tvdb_top_posters", lambda mt, tvdb_id, limit=3: [{"url": "https://tv", "label": "l"}])
        used, result = candidates.resolve_poster_candidates({}, "show", "tvdb")
        assert used == "tvdb"

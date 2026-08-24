"""services/letterboxd/router.py - moved out of
test_radarr_sonarr_prowlarr_bazarr_router.py when Letterboxd became its own
package (2026-08-06), spanning Radarr and Sonarr.
"""
from unittest.mock import MagicMock

import httpx
from fastapi.testclient import TestClient


def _login(client, main_module, password="correct-horse-battery-staple"):
    from core.security import hash_password
    from models.user import User

    db = main_module.SessionLocal()
    try:
        db.add(User(username="admin", password_hash=hash_password(password)))
        db.commit()
    finally:
        db.close()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert resp.status_code == 200


def _service_key_header(main_module):
    from core.security import hash_api_key
    from models.api_key import ApiKey

    db = main_module.SessionLocal()
    try:
        db.add(ApiKey(name="healthcheck-cron", key_hash=hash_api_key("raw-service-key")))
        db.commit()
    finally:
        db.close()
    return {"X-Api-Key": "raw-service-key"}


def _json_response(payload, status_code=200, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    return resp


def test_letterboxd_add_short_circuits_when_already_in_radarr(cp_main_app, monkeypatch):
    letterboxd_html = '<html>themoviedb.org/movie/603</html>'

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        if "letterboxd.com" in url:
            return MagicMock(text=letterboxd_html, raise_for_status=MagicMock())
        if "/movie" in url and params and params.get("tmdbId") == 603:
            return _json_response([{"id": 99, "title": "The Matrix", "year": 1999}])
        return _json_response({})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd", json={"url": "https://letterboxd.com/film/the-matrix/"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["alreadyAdded"] is True
    assert body["radarrId"] == 99


def test_letterboxd_add_rejects_non_letterboxd_url(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd", json={"url": "https://example.com/not-letterboxd"})
    assert resp.status_code == 400


def test_letterboxd_add_accepts_service_key(cp_main_app, monkeypatch):
    """stack-letterboxd-radarr.fish calls this unattended via the service
    key (2026-08-06's extend-service-key-auth commit) - was session-only
    before that."""
    letterboxd_html = '<html>themoviedb.org/movie/603</html>'

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        if "letterboxd.com" in url:
            return MagicMock(text=letterboxd_html, raise_for_status=MagicMock())
        if "/movie" in url and params and params.get("tmdbId") == 603:
            return _json_response([{"id": 99, "title": "The Matrix", "year": 1999}])
        return _json_response({})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd", json={"url": "https://letterboxd.com/film/x/"}, headers=headers)
    assert resp.status_code == 200


def test_letterboxd_add_requires_some_auth(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd", json={"url": "https://letterboxd.com/film/x/"})
    assert resp.status_code == 401


def test_letterboxd_list_add_applies_rating_quality_map(cp_main_app, monkeypatch):
    list_html = '''
    <html>
      <a href="/page/1/"></a>
      <li><div data-item-slug="high-rated-film"></div>
        <p class="poster-viewingdata"><span class="rating -micro -darker rated-10">★★★★★</span></p></li>
      <li><div data-item-slug="low-rated-film"></div>
        <p class="poster-viewingdata"><span class="rating -micro -darker rated-2">★</span></p></li>
    </html>
    '''
    film_pages = {
        "high-rated-film": "themoviedb.org/movie/111",
        "low-rated-film": "themoviedb.org/movie/222",
    }
    quality_profiles = [{"id": 5, "name": "Remux-1080p"}, {"id": 9, "name": "HD-1080p"}]
    posted_movies = []

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        if "/bear/films" in url and "/film/" not in url:
            return MagicMock(text=list_html, raise_for_status=MagicMock())
        for slug, tmdb_html in film_pages.items():
            if f"/film/{slug}/" in url and "bear" not in url:
                return MagicMock(text=tmdb_html, raise_for_status=MagicMock())
        if url.endswith("/rootfolder"):
            return MagicMock(json=lambda: [{"path": "/data/movies"}], raise_for_status=MagicMock())
        if url.endswith("/qualityprofile"):
            return MagicMock(json=lambda: quality_profiles, raise_for_status=MagicMock())
        if url.endswith("/movie/lookup/tmdb"):
            tmdb_id = params["tmdbId"]
            return MagicMock(json=lambda tmdb_id=tmdb_id: {"title": f"Film {tmdb_id}", "year": 2020, "tmdbId": tmdb_id},
                              raise_for_status=MagicMock())
        if url.endswith("/movie"):
            return MagicMock(json=lambda: [], raise_for_status=MagicMock())
        return MagicMock(json=lambda: {}, raise_for_status=MagicMock())

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        posted_movies.append(json)
        return MagicMock(json=lambda: {**json, "title": json.get("title")}, raise_for_status=MagicMock())

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd-list", json={
        "url": "https://letterboxd.com/bear/films/",
        "rating_quality_map": {"10": "Remux-1080p", "2": "HD-1080p"},
    })
    assert resp.status_code == 200
    by_tmdb = {m["tmdbId"]: m for m in posted_movies}
    assert by_tmdb[111]["qualityProfileId"] == 5
    assert by_tmdb[222]["qualityProfileId"] == 9


def test_letterboxd_list_add_attaches_scraped_tags(cp_main_app, monkeypatch):
    list_html = '<html><a href="/page/1/"></a><li><div data-item-slug="tagged-film"></div></li></html>'
    user_film_html = '''
    <ul class="tags">
      <li><a href="/bear/tag/rewatch/films/">rewatch</a></li>
      <li><a href="/bear/tag/a24/films/">a24</a></li>
    </ul>
    '''
    tags_in_radarr = [{"id": 1, "label": "rewatch"}]
    posted_movies = []
    created_tags = []

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        if "letterboxd.com/bear/list/tagged-list" in url and "/film/" not in url:
            return MagicMock(text=list_html, raise_for_status=MagicMock())
        if "letterboxd.com/bear/film/tagged-film" in url:
            return MagicMock(text=user_film_html, raise_for_status=MagicMock())
        if "letterboxd.com/film/tagged-film" in url:
            return MagicMock(text="themoviedb.org/movie/500", raise_for_status=MagicMock())
        if url.endswith("/rootfolder"):
            return MagicMock(json=lambda: [{"path": "/data/movies"}], raise_for_status=MagicMock())
        if url.endswith("/qualityprofile"):
            return MagicMock(json=lambda: [{"id": 1, "name": "Unlimited"}], raise_for_status=MagicMock())
        if url.endswith("/tag"):
            return MagicMock(json=lambda: tags_in_radarr, raise_for_status=MagicMock())
        if url.endswith("/movie/lookup/tmdb"):
            return MagicMock(json=lambda: {"title": "Tagged Film", "year": 2021, "tmdbId": 500}, raise_for_status=MagicMock())
        if url.endswith("/movie"):
            return MagicMock(json=lambda: [], raise_for_status=MagicMock())
        return MagicMock(json=lambda: {}, raise_for_status=MagicMock())

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        if url.endswith("/tag"):
            created_tags.append(json["label"])
            return MagicMock(json=lambda: {"id": 2, "label": json["label"]}, raise_for_status=MagicMock())
        posted_movies.append(json)
        return MagicMock(json=lambda: {**json, "title": json.get("title")}, raise_for_status=MagicMock())

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd-list", json={
        "url": "https://letterboxd.com/bear/list/tagged-list/",
        "tags_as_radarr_tags": True,
    })
    assert resp.status_code == 200
    assert created_tags == ["a24"]  # "rewatch" already existed (id 1), only "a24" needed creating
    assert posted_movies[0]["tags"] == [1, 2]


def test_letterboxd_list_add_crosses_over_unmatched_title_to_sonarr(cp_main_app, monkeypatch):
    list_html = '<html><a href="/page/1/"></a><li><div data-item-slug="a-tv-miniseries"></div></li></html>'
    film_page_html = '<html><meta property="og:title" content="A TV Miniseries (2022)"/>no tmdb movie link here</html>'
    sonarr_series_added = []

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        if "letterboxd.com/bear/list/tv-list" in url and "/film/" not in url:
            return MagicMock(text=list_html, raise_for_status=MagicMock())
        if "letterboxd.com/film/a-tv-miniseries" in url:
            return MagicMock(text=film_page_html, raise_for_status=MagicMock())
        if url.endswith("/movie") and "radarr" in url:
            return MagicMock(json=lambda: [], raise_for_status=MagicMock())
        if url.endswith("/rootfolder") and "radarr" in url:
            return MagicMock(json=lambda: [{"path": "/data/movies"}], raise_for_status=MagicMock())
        if url.endswith("/qualityprofile") and "radarr" in url:
            return MagicMock(json=lambda: [{"id": 1, "name": "Unlimited"}], raise_for_status=MagicMock())
        if url.endswith("/rootfolder") and "sonarr" in url:
            return MagicMock(json=lambda: [{"path": "/data/shows"}], raise_for_status=MagicMock())
        if url.endswith("/qualityprofile") and "sonarr" in url:
            return MagicMock(json=lambda: [{"id": 2, "name": "Any"}], raise_for_status=MagicMock())
        if url.endswith("/series") and "sonarr" in url:
            return MagicMock(json=lambda: [], raise_for_status=MagicMock())
        if url.endswith("/series/lookup"):
            # Two callers hit this: resolve_tv_crossovers (Task 6) looks up
            # by title text, then sonarr_add_series's own internal lookup
            # (pre-existing core/arr_client.py helper) re-looks-up by
            # "tvdb:<id>" once it has the tvdbId - both must resolve to the
            # same series for the crossover to complete.
            if params["term"] == "A TV Miniseries":
                return MagicMock(json=lambda: [{"title": "A TV Miniseries", "tvdbId": 777, "year": 2022}], raise_for_status=MagicMock())
            if params["term"] == "tvdb:777":
                return MagicMock(json=lambda: [{"title": "A TV Miniseries", "tvdbId": 777, "year": 2022}], raise_for_status=MagicMock())
            return MagicMock(json=lambda: [], raise_for_status=MagicMock())
        return MagicMock(json=lambda: {}, raise_for_status=MagicMock())

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        if url.endswith("/series"):
            sonarr_series_added.append(json)
            return MagicMock(json=lambda: {**json, "title": json.get("title")}, raise_for_status=MagicMock())
        return MagicMock(json=lambda: {}, raise_for_status=MagicMock())

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd-list", json={
        "url": "https://letterboxd.com/bear/list/tv-list/",
        "sonarr_crossover": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["tvCrossoverCount"] == 1
    assert sonarr_series_added[0]["tvdbId"] == 777


def test_track_untrack_and_list_tracked_letterboxd_lists(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)

    resp = client.post("/api/arr/letterboxd/track", json={"url": "https://letterboxd.com/bear/watchlist/", "label": "Bear's watchlist"})
    assert resp.status_code == 200
    list_id = resp.json()["id"]

    resp = client.get("/api/arr/letterboxd/tracked")
    assert resp.status_code == 200
    lists = resp.json()["lists"]
    assert any(x["id"] == list_id and x["label"] == "Bear's watchlist" for x in lists)

    resp = client.post("/api/arr/letterboxd/untrack", json={"url": "https://letterboxd.com/bear/watchlist/"})
    assert resp.status_code == 200

    resp = client.get("/api/arr/letterboxd/tracked")
    assert resp.json()["lists"] == []


def test_track_rejects_duplicate_url(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/letterboxd/track", json={"url": "https://letterboxd.com/bear/watchlist/"})
    assert resp.status_code == 200
    resp = client.post("/api/arr/letterboxd/track", json={"url": "https://letterboxd.com/bear/watchlist/"})
    assert resp.status_code == 409


def test_sync_tick_requires_service_key_or_session(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/arr/letterboxd/sync-tick")
    assert resp.status_code == 401


def test_sync_tick_runs_every_tracked_list(cp_main_app, monkeypatch):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    client.post("/api/arr/letterboxd/track", json={"url": "https://letterboxd.com/bear/watchlist/"})

    calls = []

    def fake_run_list_sync(url, **kwargs):
        calls.append(url)
        return {"added": [], "already": [], "failed": [], "unmatched": [], "tvAdded": [], "tvAlready": [], "tvFailed": [], "matched": 0}

    monkeypatch.setattr("services.letterboxd.router._run_list_sync", fake_run_list_sync)
    resp = client.post("/api/arr/letterboxd/sync-tick")
    assert resp.status_code == 200
    assert calls == ["https://letterboxd.com/bear/watchlist/"]


def test_letterboxd_add_rejects_unknown_app(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post(
        "/api/arr/radarr/add-from-letterboxd",
        json={"url": "https://letterboxd.com/film/x/", "app": "sonarr"},
    )
    assert resp.status_code == 400


def test_letterboxd_track_rejects_unknown_app(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post(
        "/api/arr/letterboxd/track",
        json={"url": "https://letterboxd.com/bear/watchlist/", "app": "not-a-real-app"},
    )
    assert resp.status_code == 400


def test_letterboxd_track_rejects_unknown_sonarr_app(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post(
        "/api/arr/letterboxd/track",
        json={"url": "https://letterboxd.com/bear/watchlist/", "sonarr_app": "not-a-real-app"},
    )
    assert resp.status_code == 400


def test_track_and_list_tracked_persists_app_and_sonarr_app(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post(
        "/api/arr/letterboxd/track",
        json={"url": "https://letterboxd.com/bear/watchlist/", "app": "radarr", "sonarr_app": "sonarr"},
    )
    assert resp.status_code == 200

    resp = client.get("/api/arr/letterboxd/tracked")
    lists = resp.json()["lists"]
    row = next(x for x in lists if x["url"] == "https://letterboxd.com/bear/watchlist/")
    assert row["app"] == "radarr"
    assert row["sonarrApp"] == "sonarr"


def test_sync_tick_passes_tracked_app_to_list_sync(cp_main_app, monkeypatch):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    client.post(
        "/api/arr/letterboxd/track",
        json={"url": "https://letterboxd.com/bear/watchlist/", "app": "radarr", "sonarr_app": "sonarr"},
    )

    calls = []

    def fake_run_list_sync(url, **kwargs):
        calls.append(kwargs)
        return {"added": [], "already": [], "failed": [], "unmatched": [], "tvAdded": [], "tvAlready": [], "tvFailed": [], "matched": 0}

    monkeypatch.setattr("services.letterboxd.router._run_list_sync", fake_run_list_sync)
    resp = client.post("/api/arr/letterboxd/sync-tick")
    assert resp.status_code == 200
    assert calls[0]["app"] == "radarr"
    assert calls[0]["sonarr_app"] == "sonarr"

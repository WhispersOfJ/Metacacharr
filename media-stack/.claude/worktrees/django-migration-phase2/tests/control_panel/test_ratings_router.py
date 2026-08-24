"""services/ratings/router.py - GET /api/ratings/imdb, /api/ratings/mdblist.
First-ever coverage for this router."""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient


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


def test_imdb_rating_missing_key_fails_500(cp_main_app, monkeypatch):
    monkeypatch.delenv("OMDB_KEY", raising=False)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/ratings/imdb", params={"imdb_id": "tt0111161"}, headers=headers)
    assert resp.status_code == 500


def test_imdb_rating_no_match_fails_404(cp_main_app, monkeypatch):
    monkeypatch.setenv("OMDB_KEY", "test-omdb-key")

    def fake_get(url, params=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"Response": "False", "Error": "Incorrect IMDb ID."}
        return resp

    import services.ratings.router as router_module
    monkeypatch.setattr(router_module.httpx, "get", fake_get)

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/ratings/imdb", params={"imdb_id": "tt0000000"}, headers=headers)
    assert resp.status_code == 404


def test_imdb_rating_returns_score(cp_main_app, monkeypatch):
    monkeypatch.setenv("OMDB_KEY", "test-omdb-key")

    def fake_get(url, params=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "Response": "True", "Title": "The Shawshank Redemption", "Year": "1994",
            "imdbRating": "9.3", "imdbVotes": "2,900,000",
        }
        return resp

    import services.ratings.router as router_module
    monkeypatch.setattr(router_module.httpx, "get", fake_get)

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/ratings/imdb", params={"imdb_id": "tt0111161"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["rating"] == "9.3"


def test_mdblist_rating_missing_key_fails_500(cp_main_app, monkeypatch):
    monkeypatch.delenv("MDBLIST_KEY", raising=False)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/ratings/mdblist", params={"imdb_id": "tt0111161"}, headers=headers)
    assert resp.status_code == 500


def test_mdblist_rating_garbage_match_detected_by_null_votes(cp_main_app, monkeypatch):
    """MDBList fuzzy-matches an unrecognized id instead of erroring - the
    documented tell is a null vote count even with a 0 score, since imdbid
    can't be trusted (see router.py's own comment)."""
    monkeypatch.setenv("MDBLIST_KEY", "test-mdblist-key")

    def fake_get(url, params=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "response": True, "title": "Unrelated Show", "year": 2020,
            "score": -1, "ratings": [{"source": "imdb", "value": None, "votes": None}],
        }
        return resp

    import services.ratings.router as router_module
    monkeypatch.setattr(router_module.httpx, "get", fake_get)

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/ratings/mdblist", params={"imdb_id": "tt0000000"}, headers=headers)
    assert resp.status_code == 404


def test_mdblist_rating_returns_score_and_imdb(cp_main_app, monkeypatch):
    monkeypatch.setenv("MDBLIST_KEY", "test-mdblist-key")

    def fake_get(url, params=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "response": True, "title": "The Shawshank Redemption", "year": 1994,
            "score": 93, "ratings": [{"source": "imdb", "value": 9.3, "votes": 2900000}],
        }
        return resp

    import services.ratings.router as router_module
    monkeypatch.setattr(router_module.httpx, "get", fake_get)

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/ratings/mdblist", params={"imdb_id": "tt0111161"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] == 93
    assert body["imdbRating"] == 9.3

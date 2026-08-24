"""services/radarr/router.py - POST /api/arr/radarr/exclude. First-ever
coverage for this router."""
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


def test_exclude_requires_session_auth(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/arr/radarr/exclude", json={"movieId": 1})
    assert resp.status_code == 401


def test_exclude_movie_not_found_fails_404(cp_main_app, monkeypatch):
    import services.radarr.router as router_module
    monkeypatch.setattr(router_module, "get_movie_or_episode", lambda app, cfg, mid: None)

    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/exclude", json={"movieId": 999})
    assert resp.status_code == 404


def test_exclude_success(cp_main_app, monkeypatch):
    import services.radarr.router as router_module
    monkeypatch.setattr(
        router_module, "get_movie_or_episode",
        lambda app, cfg, mid: {"tmdbId": 42, "title": "Test Movie", "year": 2020},
    )

    def fake_post(url, json=None, headers=None, timeout=None):
        resp = MagicMock()
        resp.status_code = 201
        return resp

    monkeypatch.setattr(router_module.httpx, "post", fake_post)

    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/exclude", json={"movieId": 42})
    assert resp.status_code == 200
    assert "Test Movie" in resp.json()["message"]


def test_exclude_treats_400_409_as_already_excluded(cp_main_app, monkeypatch):
    import services.radarr.router as router_module
    monkeypatch.setattr(
        router_module, "get_movie_or_episode",
        lambda app, cfg, mid: {"tmdbId": 42, "title": "Test Movie", "year": 2020},
    )

    def fake_post(url, json=None, headers=None, timeout=None):
        resp = MagicMock()
        resp.status_code = 409
        return resp

    monkeypatch.setattr(router_module.httpx, "post", fake_post)

    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/exclude", json={"movieId": 42})
    assert resp.status_code == 200


def test_exclude_http_error_fails_502(cp_main_app, monkeypatch):
    import services.radarr.router as router_module
    monkeypatch.setattr(
        router_module, "get_movie_or_episode",
        lambda app, cfg, mid: {"tmdbId": 42, "title": "Test Movie", "year": 2020},
    )

    def raise_error(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(router_module.httpx, "post", raise_error)

    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/exclude", json={"movieId": 42})
    assert resp.status_code == 502

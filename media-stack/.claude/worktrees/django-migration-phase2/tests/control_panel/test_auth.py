"""Phase 1 validation for .claude/plans/evolved-control-panel-backend.plan.md:
login succeeds/fails correctly, a protected route 401s without a session
and 200s with one, and the service-API-key path (for the recurring
health-check cron, which can't do an interactive login) authenticates
correctly without ever storing the raw key.
"""
from fastapi.testclient import TestClient


def _make_user(main_module, username="admin", password="correct-horse-battery-staple"):
    from core.security import hash_password
    from models.user import User

    db = main_module.SessionLocal()
    try:
        user = User(username=username, password_hash=hash_password(password))
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def test_me_without_session_is_401(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_login_with_unknown_username_is_401(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert resp.status_code == 401
    assert "cp_session" not in resp.cookies


def test_login_with_wrong_password_is_401(cp_main_app):
    _make_user(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_login_success_then_me_returns_200(cp_main_app):
    _make_user(cp_main_app)
    client = TestClient(cp_main_app.app)
    login_resp = client.post(
        "/api/auth/login", json={"username": "admin", "password": "correct-horse-battery-staple"}
    )
    assert login_resp.status_code == 200
    assert login_resp.json() == {"username": "admin"}
    assert "cp_session" in login_resp.cookies

    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json() == {"username": "admin", "is_admin": True}


def test_logout_clears_session(cp_main_app):
    _make_user(cp_main_app)
    client = TestClient(cp_main_app.app)
    client.post(
        "/api/auth/login", json={"username": "admin", "password": "correct-horse-battery-staple"}
    )
    logout_resp = client.post("/api/auth/logout")
    assert logout_resp.status_code == 200

    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 401


def test_admin_bootstrap_creates_user_once(cp_main_app, monkeypatch):
    import importlib
    import sys

    monkeypatch.setenv("CONTROL_PANEL_ADMIN_USERNAME", "bear")
    monkeypatch.setenv("CONTROL_PANEL_ADMIN_PASSWORD", "hunter2-but-actually-strong")
    # Re-trigger startup with the env vars now set, mirroring a real boot.
    sys.modules.pop("main", None)
    module = importlib.import_module("main")
    client = TestClient(module.app)

    resp = client.post(
        "/api/auth/login", json={"username": "bear", "password": "hunter2-but-actually-strong"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"username": "bear"}

    # Running startup again (e.g. a container restart) must not create a
    # second admin or break login.
    module._startup()
    resp2 = client.post(
        "/api/auth/login", json={"username": "bear", "password": "hunter2-but-actually-strong"}
    )
    assert resp2.status_code == 200


def test_current_user_or_service_accepts_valid_api_key(cp_main_app):
    from unittest.mock import MagicMock

    from core.security import current_user_or_service, hash_api_key
    from models.api_key import ApiKey

    db = cp_main_app.SessionLocal()
    try:
        db.add(ApiKey(name="healthcheck-cron", key_hash=hash_api_key("raw-service-key")))
        db.commit()

        request = MagicMock()
        request.headers = {"X-Api-Key": "raw-service-key"}
        request.cookies = {}
        result = current_user_or_service(request, db)
        assert result is None  # service-account hit, no User row
    finally:
        db.close()


def test_current_user_or_service_rejects_invalid_api_key(cp_main_app):
    from unittest.mock import MagicMock

    from core.security import current_user_or_service
    from fastapi import HTTPException

    db = cp_main_app.SessionLocal()
    try:
        request = MagicMock()
        request.headers = {"X-Api-Key": "not-a-real-key"}
        request.cookies = {}
        try:
            current_user_or_service(request, db)
            assert False, "expected HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 401
    finally:
        db.close()


def test_login_rate_limited_after_5_failures_from_same_ip(cp_main_app):
    """The sliding-window rate limiter (5 req/60s per IP) must return 429
    on the 6th attempt. The TestClient shares the same in-process bucket
    since rate_limit uses an in-memory defaultdict."""
    _make_user(cp_main_app)
    client = TestClient(cp_main_app.app)
    payload = {"username": "admin", "password": "wrong"}

    # First 5 attempts should be 401 (valid cred check, rate limit not hit).
    for i in range(5):
        resp = client.post("/api/auth/login", json=payload)
        assert resp.status_code == 401, f"attempt {i + 1}: expected 401, got {resp.status_code}"

    # 6th attempt must be 429 (rate limited).
    resp = client.post("/api/auth/login", json=payload)
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.json()["detail"]
    assert "Retry-After" in resp.headers

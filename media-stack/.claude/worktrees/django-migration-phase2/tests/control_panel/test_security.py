"""Gate tests for core/security.py - session tokens, password hashing, and
API key lookup. First-ever coverage for this module."""
import pytest


@pytest.fixture
def security_module(cp_main_app):
    import core.security as module
    return module


def test_hash_and_verify_password_roundtrip(security_module):
    hashed = security_module.hash_password("correct horse battery staple")
    assert security_module.verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_wrong_password(security_module):
    hashed = security_module.hash_password("right-password")
    assert security_module.verify_password("wrong-password", hashed) is False


def test_create_and_read_session_token_roundtrip(security_module):
    token = security_module.create_session_token(user_id=7)
    assert security_module.read_session_token(token) == 7


def test_read_session_token_rejects_garbage(security_module):
    assert security_module.read_session_token("not-a-real-token") is None


def test_read_session_token_rejects_expired(security_module, monkeypatch):
    token = security_module.create_session_token(user_id=1)
    monkeypatch.setattr(security_module, "SESSION_MAX_AGE", -1)
    assert security_module.read_session_token(token) is None


def test_hash_api_key_is_deterministic(security_module):
    assert security_module.hash_api_key("my-key") == security_module.hash_api_key("my-key")


def test_hash_api_key_differs_per_input(security_module):
    assert security_module.hash_api_key("key-a") != security_module.hash_api_key("key-b")


def test_secret_key_missing_raises(security_module, monkeypatch):
    monkeypatch.delenv("CONTROL_PANEL_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        security_module._secret_key()


def test_current_user_no_cookie_raises_401(security_module, cp_main_app):
    from starlette.testclient import TestClient
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/settings")
    assert resp.status_code in (401, 403)

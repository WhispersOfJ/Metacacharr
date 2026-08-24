import pytest
from rest_framework.test import APIRequestFactory

from core.authentication import SessionOrApiKeyAuthentication
from core.models import ApiKey, User
from core.security import hash_api_key


@pytest.mark.django_db
def test_authenticate_returns_none_with_no_credentials():
    request = APIRequestFactory().get("/api/v2/health")
    request.session = {}
    result = SessionOrApiKeyAuthentication().authenticate(request)
    assert result is None


@pytest.mark.django_db
def test_authenticate_via_valid_session():
    user = User.objects.create(username="bear", password_hash="x")
    request = APIRequestFactory().get("/api/v2/health")
    request.session = {"user_id": user.id}
    result = SessionOrApiKeyAuthentication().authenticate(request)
    assert result is not None
    authed_user, _ = result
    assert authed_user.username == "bear"


@pytest.mark.django_db
def test_authenticate_via_valid_api_key():
    ApiKey.objects.create(name="healthcheck-cron", key_hash=hash_api_key("secret-key"))
    request = APIRequestFactory().get("/api/v2/health", HTTP_X_API_KEY="secret-key")
    request.session = {}
    result = SessionOrApiKeyAuthentication().authenticate(request)
    assert result is not None
    authed_user, _ = result
    assert authed_user.is_authenticated is True


@pytest.mark.django_db
def test_authenticate_rejects_invalid_api_key():
    from rest_framework.exceptions import AuthenticationFailed

    request = APIRequestFactory().get("/api/v2/health", HTTP_X_API_KEY="not-a-real-key")
    request.session = {}
    with pytest.raises(AuthenticationFailed):
        SessionOrApiKeyAuthentication().authenticate(request)


@pytest.mark.django_db
def test_authenticate_updates_last_used_at_on_valid_key():
    key_row = ApiKey.objects.create(name="healthcheck-cron", key_hash=hash_api_key("secret-key"))
    assert key_row.last_used_at is None
    request = APIRequestFactory().get("/api/v2/health", HTTP_X_API_KEY="secret-key")
    request.session = {}
    SessionOrApiKeyAuthentication().authenticate(request)
    key_row.refresh_from_db()
    assert key_row.last_used_at is not None


from core.permissions import IsAuthenticatedOrServiceKey


class _FakeRequest:
    def __init__(self, user):
        self.user = user


def test_permission_denies_anonymous():
    from django.contrib.auth.models import AnonymousUser

    assert IsAuthenticatedOrServiceKey().has_permission(_FakeRequest(AnonymousUser()), None) is False


def test_permission_allows_authenticated_duck_type():
    class _Authed:
        is_authenticated = True

    assert IsAuthenticatedOrServiceKey().has_permission(_FakeRequest(_Authed()), None) is True


from core.authentication import AnonymousServiceUser
from core.permissions import IsAuthenticatedSessionOnly


def test_session_only_permission_rejects_service_account():
    assert IsAuthenticatedSessionOnly().has_permission(_FakeRequest(AnonymousServiceUser()), None) is False


def test_session_only_permission_allows_real_user_duck_type():
    class _Authed:
        is_authenticated = True
        is_service_account = False

    assert IsAuthenticatedSessionOnly().has_permission(_FakeRequest(_Authed()), None) is True

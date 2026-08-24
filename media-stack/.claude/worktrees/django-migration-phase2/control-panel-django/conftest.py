import os

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from core.models import ApiKey, User
from core.security import hash_api_key

# core.arr_client reads these via bare os.environ[...] at import time (mirrors
# the FastAPI-era app.py: a missing key is a deployment misconfiguration that
# should fail loudly in production). Tests need *some* value present so the
# module is importable; set defaults here, before any test module imports
# core.arr_client, without clobbering a real value if one is already set.
os.environ.setdefault("RADARR_API_KEY", "test-radarr-key")
os.environ.setdefault("SONARR_API_KEY", "test-sonarr-key")
os.environ.setdefault("PROWLARR_API_KEY", "test-prowlarr-key")
os.environ.setdefault("WS_API_KEY", "test-watchstate-key")
os.environ.setdefault("MDBLIST_KEY", "test-mdblist-key")


@pytest.fixture
def authed_client(db):
    user = User.objects.create(username="bear", password_hash="x")
    client = APIClient()
    session = client.session
    session["user_id"] = user.id
    session.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
    return client


@pytest.fixture
def service_client(db):
    ApiKey.objects.create(name="test-service", key_hash=hash_api_key("test-service-key"))
    client = APIClient()
    client.credentials(HTTP_X_API_KEY="test-service-key")
    return client

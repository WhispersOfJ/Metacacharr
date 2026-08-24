from unittest.mock import patch
import json

import pytest
from rest_framework.test import APIClient

from core.api_base import ServiceError


@pytest.mark.django_db
def test_exclude_movie_view_happy_path(authed_client):
    """POST /api/v2/radarr/exclude excludes a movie via session auth (real pipeline)."""
    with patch("radarr.api.views.services.exclude_movie", return_value={"movieId": 123}):
        response = authed_client.post(
            "/api/v2/radarr/exclude",
            json.dumps({"movieId": 123}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )

    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["ok"] is True
    assert data["movieId"] == 123
    assert data["message"] == "Movie excluded"


@pytest.mark.django_db
def test_exclude_movie_view_service_client_gets_403(service_client):
    """Service key clients are rejected (session-only endpoint)."""
    response = service_client.post("/api/v2/radarr/exclude", {"movieId": 123}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_exclude_movie_view_movie_not_found(authed_client):
    """404 when movie not found in Radarr (real pipeline)."""
    with patch(
        "radarr.api.views.services.exclude_movie",
        side_effect=ServiceError("Movie 999 not found in Radarr", status=404),
    ):
        response = authed_client.post(
            "/api/v2/radarr/exclude",
            json.dumps({"movieId": 999}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )

    assert response.status_code == 404
    data = json.loads(response.content)
    assert data["ok"] is False
    assert "not found" in data["message"]


@pytest.mark.django_db
def test_exclude_movie_view_missing_movie_id(authed_client):
    """400 when movieId missing from request (real pipeline)."""
    response = authed_client.post(
        "/api/v2/radarr/exclude",
        json.dumps({}),
        content_type="application/json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code == 400


def test_exclude_movie_view_rejects_unauthenticated():
    """Unauthenticated requests are rejected."""
    client = APIClient()
    response = client.post("/api/v2/radarr/exclude", {"movieId": 123}, format="json")
    assert response.status_code in (401, 403)

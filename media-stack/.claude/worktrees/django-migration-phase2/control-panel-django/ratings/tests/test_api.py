from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from core.api_base import ServiceError


@pytest.mark.django_db
def test_imdb_view_returns_envelope(authed_client):
    with patch("ratings.api.views.services.get_imdb_rating", return_value={"imdbId": "tt1", "title": "X"}):
        response = authed_client.get("/api/v2/ratings/imdb", {"imdb_id": "tt1"})
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["title"] == "X"


@pytest.mark.django_db
def test_imdb_view_missing_param_returns_400(authed_client):
    response = authed_client.get("/api/v2/ratings/imdb")
    assert response.status_code == 400


@pytest.mark.django_db
def test_imdb_view_service_error_renders_envelope(authed_client):
    with patch("ratings.api.views.services.get_imdb_rating", side_effect=ServiceError("no match", status=404)):
        response = authed_client.get("/api/v2/ratings/imdb", {"imdb_id": "tt0"})
    assert response.status_code == 404
    assert response.data == {"ok": False, "message": "no match"}


@pytest.mark.django_db
def test_mdblist_view_returns_envelope(authed_client):
    with patch("ratings.api.views.services.get_mdblist_rating", return_value={"imdbId": "tt1", "score": 90}):
        response = authed_client.get("/api/v2/ratings/mdblist", {"imdb_id": "tt1"})
    assert response.status_code == 200
    assert response.data["score"] == 90


@pytest.mark.django_db
def test_ratings_endpoints_reject_unauthenticated():
    client = APIClient()
    response = client.get("/api/v2/ratings/imdb", {"imdb_id": "tt1"})
    assert response.status_code in (401, 403)

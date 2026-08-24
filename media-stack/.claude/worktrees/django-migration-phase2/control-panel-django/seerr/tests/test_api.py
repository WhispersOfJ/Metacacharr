from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from core.api_base import ServiceError


@pytest.mark.django_db
def test_seerr_requests_view_returns_envelope(authed_client):
    items = [
        {
            "title": "the-matrix",
            "type": "movie",
            "requestedBy": "Bear",
            "status": 2,
            "createdAt": "2026-01-01T00:00:00.000Z",
        }
    ]
    with patch("seerr.api.views.services.list_requests", return_value=items) as mocked:
        response = authed_client.get("/api/v2/seerr/requests", {"status": "pending"})
    mocked.assert_called_once_with("pending")
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["items"] == items
    assert response.data["message"] == "1 pending request(s) in Seerr."


@pytest.mark.django_db
def test_seerr_requests_view_defaults_status_to_pending(authed_client):
    with patch("seerr.api.views.services.list_requests", return_value=[]) as mocked:
        response = authed_client.get("/api/v2/seerr/requests")
    mocked.assert_called_once_with("pending")
    assert response.status_code == 200
    assert response.data["items"] == []


@pytest.mark.django_db
def test_seerr_requests_view_service_error_renders_envelope(authed_client):
    with patch(
        "seerr.api.views.services.list_requests",
        side_effect=ServiceError(
            "Could not read Seerr's API key from config/seerr/settings.json.", status=503
        ),
    ):
        response = authed_client.get("/api/v2/seerr/requests")
    assert response.status_code == 503
    assert response.data == {
        "ok": False,
        "message": "Could not read Seerr's API key from config/seerr/settings.json.",
    }


@pytest.mark.django_db
def test_seerr_requests_view_works_with_service_client(service_client):
    with patch("seerr.api.views.services.list_requests", return_value=[]):
        response = service_client.get("/api/v2/seerr/requests")
    assert response.status_code == 200
    assert response.data["ok"] is True


def test_seerr_requests_view_rejects_unauthenticated():
    client = APIClient()
    response = client.get("/api/v2/seerr/requests")
    assert response.status_code in (401, 403)

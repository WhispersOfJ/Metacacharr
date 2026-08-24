from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from core.api_base import ServiceError


@pytest.mark.django_db
def test_prowlarr_indexers_view_returns_envelope(authed_client):
    """GET /api/v2/prowlarr/indexers returns indexers in envelope."""
    items = [
        {"name": "Alpha", "enabled": False, "priority": 25},
        {"name": "Beta", "enabled": True, "priority": 30},
    ]
    with patch("prowlarr.api.views.services.list_indexers", return_value=items) as mocked:
        response = authed_client.get("/api/v2/prowlarr/indexers")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["items"] == items
    assert response.data["message"] == "Indexers fetched"


@pytest.mark.django_db
def test_prowlarr_indexers_view_empty_list(authed_client):
    """GET /api/v2/prowlarr/indexers with no indexers returns empty list."""
    with patch("prowlarr.api.views.services.list_indexers", return_value=[]) as mocked:
        response = authed_client.get("/api/v2/prowlarr/indexers")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["items"] == []


@pytest.mark.django_db
def test_prowlarr_indexers_view_service_error_renders_envelope(authed_client):
    """Service errors render envelope with status code."""
    with patch(
        "prowlarr.api.views.services.list_indexers",
        side_effect=ServiceError("PROWLARR_API_KEY is not configured", status=503),
    ):
        response = authed_client.get("/api/v2/prowlarr/indexers")
    assert response.status_code == 503
    assert response.data == {
        "ok": False,
        "message": "PROWLARR_API_KEY is not configured",
    }


@pytest.mark.django_db
def test_prowlarr_indexers_view_works_with_service_client(service_client):
    """Service client authentication also works."""
    with patch("prowlarr.api.views.services.list_indexers", return_value=[]):
        response = service_client.get("/api/v2/prowlarr/indexers")
    assert response.status_code == 200
    assert response.data["ok"] is True


def test_prowlarr_indexers_view_rejects_unauthenticated():
    """Unauthenticated requests are rejected."""
    client = APIClient()
    response = client.get("/api/v2/prowlarr/indexers")
    assert response.status_code in (401, 403)

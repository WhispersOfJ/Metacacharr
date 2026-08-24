from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from core.api_base import ServiceError


@pytest.mark.django_db
def test_instances_view_returns_envelope(authed_client):
    """GET /api/v2/cleanuparr/instances returns connected/gaps in envelope."""
    result = {"message": "1 app(s) have a config placeholder but no connected instance: sonarr",
              "connected": ["radarr"], "gaps": ["sonarr"]}
    with patch("cleanuparr.api.views.services.check_instances", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/cleanuparr/instances")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["connected"] == ["radarr"]
    assert response.data["gaps"] == ["sonarr"]
    assert response.data["message"] == result["message"]


@pytest.mark.django_db
def test_instances_view_missing_db_returns_502(authed_client):
    """A missing cleanuparr.db raises ServiceError(502), which the view
    surfaces as a 502 error envelope, matching router.py's real
    behavior."""
    message = "/host-config/cleanuparr/cleanuparr.db not present."
    with patch(
        "cleanuparr.api.views.services.check_instances",
        side_effect=ServiceError(message, status=502),
    ):
        response = authed_client.get("/api/v2/cleanuparr/instances")
    assert response.status_code == 502
    assert response.data["ok"] is False
    assert response.data["message"] == message


def test_instances_view_rejects_unauthenticated():
    client = APIClient()
    response = client.get("/api/v2/cleanuparr/instances")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_strikes_view_returns_envelope(authed_client):
    """GET /api/v2/cleanuparr/strikes?limit=15 returns items/total in envelope."""
    items = [{"created_at": "2026-08-21T10:00:00", "type": "stalled", "title": "Movie One"}]
    result = {"message": "1 strike(s) total, showing 1 most recent.", "items": items, "total": 1}
    with patch("cleanuparr.api.views.services.recent_strikes", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/cleanuparr/strikes")
    mocked.assert_called_once_with(limit=15)
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["items"] == items
    assert response.data["total"] == 1


@pytest.mark.django_db
def test_strikes_view_respects_limit_query_param(authed_client):
    result = {"message": "0 strike(s) total, showing 0 most recent.", "items": [], "total": 0}
    with patch("cleanuparr.api.views.services.recent_strikes", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/cleanuparr/strikes?limit=5")
    mocked.assert_called_once_with(limit=5)
    assert response.status_code == 200


@pytest.mark.django_db
def test_strikes_view_works_with_service_client(service_client):
    result = {"message": "0 strike(s) total, showing 0 most recent.", "items": [], "total": 0}
    with patch("cleanuparr.api.views.services.recent_strikes", return_value=dict(result)):
        response = service_client.get("/api/v2/cleanuparr/strikes")
    assert response.status_code == 200
    assert response.data["ok"] is True


def test_strikes_view_rejects_unauthenticated():
    client = APIClient()
    response = client.get("/api/v2/cleanuparr/strikes")
    assert response.status_code in (401, 403)

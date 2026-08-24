from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from core.api_base import ServiceError


@pytest.mark.django_db
def test_queue_view_returns_envelope(authed_client):
    items = [{"name": "Movie.One", "category": "movies", "status": "Downloading",
              "percentage": "42", "size_mb": "1000", "size_left_mb": "580"}]
    with patch("nzbdav.api.views.services.get_queue", return_value=list(items)) as mocked:
        response = authed_client.get("/api/v2/nzbdav/queue")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["items"] == items


def test_queue_view_rejects_unauthenticated():
    client = APIClient()
    response = client.get("/api/v2/nzbdav/queue")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_history_view_returns_envelope_and_default_limit(authed_client):
    items = [{"name": "Movie.Two", "category": "movies", "status": "Completed",
              "size": "5.0 MB", "fail_message": None, "path": "/data/Movie.Two"}]
    with patch("nzbdav.api.views.services.get_history", return_value=list(items)) as mocked:
        response = authed_client.get("/api/v2/nzbdav/history")
    mocked.assert_called_once_with(limit=20)
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["items"] == items


@pytest.mark.django_db
def test_history_view_respects_limit_query_param(authed_client):
    with patch("nzbdav.api.views.services.get_history", return_value=[]) as mocked:
        response = authed_client.get("/api/v2/nzbdav/history?limit=5")
    mocked.assert_called_once_with(limit=5)
    assert response.status_code == 200


def test_history_view_rejects_unauthenticated():
    client = APIClient()
    response = client.get("/api/v2/nzbdav/history")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_dedup_config_check_view_returns_envelope(authed_client):
    result = {"message": "NzbDAV dedup config OK (mark-failed).", "value": "mark-failed", "healthy": True}
    with patch("nzbdav.api.views.services.check_dedup_config", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/nzbdav/dedup-config-check")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["healthy"] is True
    assert response.data["value"] == "mark-failed"


@pytest.mark.django_db
def test_dedup_config_check_view_returns_503_when_key_unset(authed_client):
    """NZBDAV_API_KEY unset -> services.check_dedup_config raises
    ServiceError(503), which the view surfaces as a 503 error envelope,
    matching the real core.nzbdav_client.nzbdav_api()/router.py
    behavior."""
    message = "NzbDAV isn't configured (FRONTEND_BACKEND_API_KEY not set)"
    with patch(
        "nzbdav.api.views.services.check_dedup_config",
        side_effect=ServiceError(message, status=503),
    ):
        response = authed_client.get("/api/v2/nzbdav/dedup-config-check")
    assert response.status_code == 503
    assert response.data["ok"] is False
    assert response.data["message"] == message


def test_dedup_config_check_view_rejects_unauthenticated():
    client = APIClient()
    response = client.get("/api/v2/nzbdav/dedup-config-check")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_stats_view_returns_envelope(authed_client):
    result = {"message": "2 queued (150MB left), 3 in recent history (2 failed).",
              "queued": 2, "mb_left": 150, "history_count": 3, "history_failed": 2}
    with patch("nzbdav.api.views.services.get_stats", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/nzbdav/stats")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["queued"] == 2
    assert response.data["history_failed"] == 2


def test_stats_view_rejects_unauthenticated():
    client = APIClient()
    response = client.get("/api/v2/nzbdav/stats")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_delete_failures_view_returns_envelope(authed_client):
    result = {"message": "Deleted 1/2 failed history entries. 1 error(s).",
              "deleted": 1, "errors": ["Job Two: not found"]}
    with patch("nzbdav.api.views.services.delete_failures", return_value=dict(result)) as mocked:
        response = authed_client.post(
            "/api/v2/nzbdav/delete-failures",
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["deleted"] == 1
    assert response.data["errors"] == ["Job Two: not found"]


@pytest.mark.django_db
def test_delete_failures_view_works_with_service_client(service_client):
    result = {"message": "No failed history entries to delete.", "deleted": 0, "errors": []}
    with patch("nzbdav.api.views.services.delete_failures", return_value=dict(result)):
        response = service_client.post(
            "/api/v2/nzbdav/delete-failures",
            format="json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    assert response.status_code == 200
    assert response.data["ok"] is True


def test_delete_failures_view_rejects_unauthenticated():
    client = APIClient()
    response = client.post("/api/v2/nzbdav/delete-failures", format="json")
    assert response.status_code in (401, 403)

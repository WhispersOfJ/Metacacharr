from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from core.api_base import ServiceError


@pytest.mark.django_db
def test_status_view_returns_envelope(authed_client):
    result = {
        "message": "Idle. 42 item(s) tracked, last import never, next None.",
        "version": "1.2.3",
        "tracked": 42,
        "backend": {"name": "plex", "url": "http://plex:32400", "import_enabled": True,
                     "export_enabled": False, "last_sync": None},
        "task": {"enabled": True, "timer": None, "next_run": None, "prev_run": None, "queued": False},
    }
    with patch("watchstate.api.views.services.get_status", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/watchstate/status")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["tracked"] == 42
    assert response.data["backend"]["name"] == "plex"
    assert response.data["task"]["enabled"] is True


def test_status_view_rejects_unauthenticated():
    client = APIClient()
    response = client.get("/api/v2/watchstate/status")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_import_view_returns_envelope(authed_client):
    result = {"message": "Import queued - WatchState's dispatcher runs it within a minute.",
              "event_id": "abc123", "task": "import"}
    with patch("watchstate.api.views.services.queue_import", return_value=dict(result)) as mocked:
        response = authed_client.post(
            "/api/v2/watchstate/import",
            format="json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["event_id"] == "abc123"
    assert response.data["task"] == "import"


@pytest.mark.django_db
def test_import_view_works_with_service_client(service_client):
    result = {"message": "Import queued.", "event_id": None, "task": "import"}
    with patch("watchstate.api.views.services.queue_import", return_value=dict(result)):
        response = service_client.post(
            "/api/v2/watchstate/import",
            format="json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    assert response.status_code == 200
    assert response.data["ok"] is True


def test_import_view_rejects_unauthenticated():
    client = APIClient()
    response = client.post(
        "/api/v2/watchstate/import",
        format="json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_history_view_returns_envelope_and_default_limit(authed_client):
    result = {"message": "0 item(s), showing 0.", "history": [], "total": 0, "shown": 0}
    with patch("watchstate.api.views.services.get_history", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/watchstate/history")
    mocked.assert_called_once_with(item="", limit=20)
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["history"] == []


@pytest.mark.django_db
def test_history_view_passes_item_and_limit_query_params(authed_client):
    with patch("watchstate.api.views.services.get_history", return_value={"message": "x", "history": [], "total": 0, "shown": 0}) as mocked:
        response = authed_client.get("/api/v2/watchstate/history?item=matrix&limit=5")
    mocked.assert_called_once_with(item="matrix", limit=5)
    assert response.status_code == 200


@pytest.mark.django_db
def test_history_view_limit_zero_returns_400(authed_client):
    message = "limit must be a positive integer."
    with patch("watchstate.api.views.services.get_history", side_effect=ServiceError(message, status=400)):
        response = authed_client.get("/api/v2/watchstate/history?limit=0")
    assert response.status_code == 400
    assert response.data["ok"] is False
    assert response.data["message"] == message


def test_history_view_rejects_unauthenticated():
    client = APIClient()
    response = client.get("/api/v2/watchstate/history")
    assert response.status_code in (401, 403)

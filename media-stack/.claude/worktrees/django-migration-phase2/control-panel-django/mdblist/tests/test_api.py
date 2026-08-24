import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from core.api_base import ServiceError


@pytest.mark.django_db
def test_import_list_view_happy_path(authed_client):
    result = {"message": "Radarr: 1 added, 0 already present, 0 failed",
              "radarr": {"added": ["The Matrix"], "alreadyCount": 0, "failed": []}, "sonarr": None, "dryRun": False}
    with patch("mdblist.api.views.services.import_list", return_value=dict(result)) as mocked:
        response = authed_client.post(
            "/api/v2/mdblist/import-list",
            json.dumps({"list_url": "https://mdblist.com/lists/bear/my-list/"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    mocked.assert_called_once_with(
        "https://mdblist.com/lists/bear/my-list/", app="radarr", sonarr_app="sonarr", monitored=True,
        search=True, limit=None, radarr_root_folder=None, radarr_quality_profile=None,
        sonarr_root_folder=None, sonarr_quality_profile=None, dry_run=False,
    )
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["radarr"]["added"] == ["The Matrix"]


@pytest.mark.django_db
def test_import_list_view_works_with_service_client(service_client):
    result = {"message": "x", "radarr": None, "sonarr": None, "dryRun": False}
    with patch("mdblist.api.views.services.import_list", return_value=dict(result)):
        response = service_client.post(
            "/api/v2/mdblist/import-list",
            json.dumps({"list_url": "https://mdblist.com/lists/bear/my-list/"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    assert response.status_code == 200
    assert response.data["ok"] is True


def test_import_list_view_rejects_unauthenticated():
    client = APIClient()
    response = client.post(
        "/api/v2/mdblist/import-list",
        json.dumps({"list_url": "https://mdblist.com/lists/bear/my-list/"}),
        content_type="application/json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_import_list_view_propagates_service_error(authed_client):
    with patch("mdblist.api.views.services.import_list",
               side_effect=ServiceError("Not a recognized MDBList list URL.", status=400)):
        response = authed_client.post(
            "/api/v2/mdblist/import-list",
            json.dumps({"list_url": "https://example.com/nope"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    assert response.status_code == 400
    assert response.data["ok"] is False


@pytest.mark.django_db
def test_history_view_returns_envelope(authed_client):
    result = {"message": "2 recent sync run(s).", "runs": [{"listUrl": "x"}, {"listUrl": "y"}]}
    with patch("mdblist.api.views.services.get_history", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/mdblist/history")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert len(response.data["runs"]) == 2


def test_history_view_rejects_unauthenticated():
    client = APIClient()
    response = client.get(
        "/api/v2/mdblist/history",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_track_view_happy_path(authed_client):
    result = {"message": "Now tracking 'https://mdblist.com/lists/bear/watch/'.", "id": 7}
    with patch("mdblist.api.views.services.track", return_value=dict(result)) as mocked:
        response = authed_client.post(
            "/api/v2/mdblist/track",
            json.dumps({"url": "https://mdblist.com/lists/bear/watch/", "label": "Watch"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    mocked.assert_called_once_with(
        "https://mdblist.com/lists/bear/watch/", app="radarr", sonarr_app="sonarr", label="Watch",
        radarr_root_folder=None, radarr_quality_profile=None, sonarr_root_folder=None, sonarr_quality_profile=None,
    )
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["id"] == 7


@pytest.mark.django_db
def test_track_view_duplicate_returns_409(authed_client):
    with patch("mdblist.api.views.services.track",
               side_effect=ServiceError("already tracked", status=409)):
        response = authed_client.post(
            "/api/v2/mdblist/track",
            json.dumps({"url": "https://mdblist.com/lists/bear/watch/"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    assert response.status_code == 409
    assert response.data["ok"] is False


@pytest.mark.django_db
def test_track_view_rejects_service_client(service_client):
    response = service_client.post(
        "/api/v2/mdblist/track",
        json.dumps({"url": "https://mdblist.com/lists/bear/watch/"}),
        content_type="application/json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code == 403
    assert response.data["detail"]


def test_track_view_rejects_unauthenticated():
    client = APIClient()
    response = client.post(
        "/api/v2/mdblist/track",
        json.dumps({"url": "https://mdblist.com/lists/bear/watch/"}),
        content_type="application/json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_untrack_view_happy_path(authed_client):
    result = {"message": "Stopped tracking 'https://mdblist.com/lists/bear/watch/'."}
    with patch("mdblist.api.views.services.untrack", return_value=dict(result)) as mocked:
        response = authed_client.post(
            "/api/v2/mdblist/untrack",
            json.dumps({"url": "https://mdblist.com/lists/bear/watch/"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    mocked.assert_called_once_with("https://mdblist.com/lists/bear/watch/")
    assert response.status_code == 200
    assert response.data["ok"] is True


@pytest.mark.django_db
def test_untrack_view_unknown_returns_404(authed_client):
    with patch("mdblist.api.views.services.untrack", side_effect=ServiceError("isn't tracked", status=404)):
        response = authed_client.post(
            "/api/v2/mdblist/untrack",
            json.dumps({"url": "https://mdblist.com/lists/nope/nope/"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    assert response.status_code == 404
    assert response.data["ok"] is False


@pytest.mark.django_db
def test_untrack_view_rejects_service_client(service_client):
    response = service_client.post(
        "/api/v2/mdblist/untrack",
        json.dumps({"url": "https://mdblist.com/lists/bear/watch/"}),
        content_type="application/json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code == 403


def test_untrack_view_rejects_unauthenticated():
    client = APIClient()
    response = client.post(
        "/api/v2/mdblist/untrack",
        json.dumps({"url": "https://mdblist.com/lists/bear/watch/"}),
        content_type="application/json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_tracked_view_returns_envelope(authed_client):
    result = {"message": "1 tracked list(s).", "lists": [{"id": 1, "url": "x"}]}
    with patch("mdblist.api.views.services.list_tracked", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/mdblist/tracked")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert len(response.data["lists"]) == 1


def test_tracked_view_rejects_unauthenticated():
    client = APIClient()
    response = client.get(
        "/api/v2/mdblist/tracked",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_sync_tick_view_happy_path(authed_client):
    result = {"message": "Synced 2 tracked list(s).", "results": [{"url": "a"}, {"url": "b"}]}
    with patch("mdblist.api.views.services.sync_tick", return_value=dict(result)) as mocked:
        response = authed_client.post(
            "/api/v2/mdblist/sync-tick",
            format="json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert len(response.data["results"]) == 2


@pytest.mark.django_db
def test_sync_tick_view_works_with_service_client(service_client):
    result = {"message": "Synced 0 tracked list(s).", "results": []}
    with patch("mdblist.api.views.services.sync_tick", return_value=dict(result)):
        response = service_client.post(
            "/api/v2/mdblist/sync-tick",
            format="json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    assert response.status_code == 200
    assert response.data["ok"] is True


def test_sync_tick_view_rejects_unauthenticated():
    client = APIClient()
    response = client.post(
        "/api/v2/mdblist/sync-tick",
        format="json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)

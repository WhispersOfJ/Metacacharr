import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from core.api_base import ServiceError


@pytest.mark.django_db
def test_add_view_happy_path(authed_client):
    result = {"message": 'Added "Oppenheimer" (2023) to Radarr.', "tmdbId": 872585, "radarrId": 99}
    with patch("letterboxd.api.views.services.add_from_url", return_value=dict(result)) as mocked:
        response = authed_client.post(
            "/api/v2/letterboxd/add",
            json.dumps({"url": "https://letterboxd.com/film/oppenheimer/"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    mocked.assert_called_once_with(
        "https://letterboxd.com/film/oppenheimer/", app="radarr", monitored=True, search=True,
        root_folder=None, quality_profile=None, dry_run=False,
    )
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["radarrId"] == 99


@pytest.mark.django_db
def test_add_view_works_with_service_client(service_client):
    result = {"message": "x", "tmdbId": 1, "radarrId": None}
    with patch("letterboxd.api.views.services.add_from_url", return_value=dict(result)):
        response = service_client.post(
            "/api/v2/letterboxd/add",
            json.dumps({"url": "https://letterboxd.com/film/oppenheimer/"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    assert response.status_code == 200
    assert response.data["ok"] is True


def test_add_view_rejects_unauthenticated():
    client = APIClient()
    response = client.post(
        "/api/v2/letterboxd/add",
        json.dumps({"url": "https://letterboxd.com/film/oppenheimer/"}),
        content_type="application/json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_add_view_propagates_service_error(authed_client):
    with patch("letterboxd.api.views.services.add_from_url",
               side_effect=ServiceError("Not a Letterboxd film URL.", status=400)):
        response = authed_client.post(
            "/api/v2/letterboxd/add",
            json.dumps({"url": "https://example.com/nope"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    assert response.status_code == 400
    assert response.data["ok"] is False


@pytest.mark.django_db
def test_add_from_list_view_happy_path(authed_client):
    result = {
        "message": "1 added, 0 already in Radarr, 0 failed", "added": ["Oppenheimer"], "alreadyCount": 0,
        "failed": [], "unmatched": [], "dryRun": False, "tvCrossoverAdded": [], "tvCrossoverAlready": [],
        "tvCrossoverFailed": [], "tvCrossoverCount": 0,
    }
    with patch("letterboxd.api.views.services.add_from_list", return_value=dict(result)) as mocked:
        response = authed_client.post(
            "/api/v2/letterboxd/add-from-list",
            json.dumps({"url": "https://letterboxd.com/bear/watchlist/"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    mocked.assert_called_once_with(
        "https://letterboxd.com/bear/watchlist/", app="radarr", monitored=True, search=True,
        root_folder=None, quality_profile=None, limit=None, dry_run=False, rating_quality_map=None,
        tags_as_radarr_tags=False, sonarr_crossover=False, sonarr_app="sonarr",
    )
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["added"] == ["Oppenheimer"]


@pytest.mark.django_db
def test_add_from_list_view_passes_through_rating_quality_map(authed_client):
    result = {"message": "x", "added": [], "alreadyCount": 0, "failed": [], "unmatched": [], "dryRun": False,
              "tvCrossoverAdded": [], "tvCrossoverAlready": [], "tvCrossoverFailed": [], "tvCrossoverCount": 0}
    with patch("letterboxd.api.views.services.add_from_list", return_value=dict(result)) as mocked:
        authed_client.post(
            "/api/v2/letterboxd/add-from-list",
            json.dumps({"url": "https://letterboxd.com/bear/watchlist/", "rating_quality_map": {"10": "4K"}}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    assert mocked.call_args.kwargs["rating_quality_map"] == {"10": "4K"}


def test_add_from_list_view_rejects_unauthenticated():
    client = APIClient()
    response = client.post(
        "/api/v2/letterboxd/add-from-list",
        json.dumps({"url": "https://letterboxd.com/bear/watchlist/"}),
        content_type="application/json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_history_view_returns_envelope(authed_client):
    result = {"message": "2 recent sync run(s).", "runs": [{"listUrl": "x"}, {"listUrl": "y"}]}
    with patch("letterboxd.api.views.services.get_history", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/letterboxd/history")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert len(response.data["runs"]) == 2


def test_history_view_rejects_unauthenticated():
    client = APIClient()
    response = client.get(
        "/api/v2/letterboxd/history",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_track_view_happy_path(authed_client):
    result = {"message": "Now tracking 'https://letterboxd.com/bear/watchlist/'.", "id": 7}
    with patch("letterboxd.api.views.services.track", return_value=dict(result)) as mocked:
        response = authed_client.post(
            "/api/v2/letterboxd/track",
            json.dumps({"url": "https://letterboxd.com/bear/watchlist/", "label": "Watchlist"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    mocked.assert_called_once_with(
        "https://letterboxd.com/bear/watchlist/", app="radarr", label="Watchlist", root_folder=None,
        quality_profile=None, rating_quality_map=None, tags_as_radarr_tags=False, sonarr_app="sonarr",
    )
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["id"] == 7


@pytest.mark.django_db
def test_track_view_duplicate_returns_409(authed_client):
    with patch("letterboxd.api.views.services.track", side_effect=ServiceError("already tracked", status=409)):
        response = authed_client.post(
            "/api/v2/letterboxd/track",
            json.dumps({"url": "https://letterboxd.com/bear/watchlist/"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    assert response.status_code == 409
    assert response.data["ok"] is False


@pytest.mark.django_db
def test_track_view_rejects_service_client(service_client):
    response = service_client.post(
        "/api/v2/letterboxd/track",
        json.dumps({"url": "https://letterboxd.com/bear/watchlist/"}),
        content_type="application/json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code == 403
    assert response.data["detail"]


def test_track_view_rejects_unauthenticated():
    client = APIClient()
    response = client.post(
        "/api/v2/letterboxd/track",
        json.dumps({"url": "https://letterboxd.com/bear/watchlist/"}),
        content_type="application/json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_untrack_view_happy_path(authed_client):
    result = {"message": "Stopped tracking 'https://letterboxd.com/bear/watchlist/'."}
    with patch("letterboxd.api.views.services.untrack", return_value=dict(result)) as mocked:
        response = authed_client.post(
            "/api/v2/letterboxd/untrack",
            json.dumps({"url": "https://letterboxd.com/bear/watchlist/"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    mocked.assert_called_once_with("https://letterboxd.com/bear/watchlist/")
    assert response.status_code == 200
    assert response.data["ok"] is True


@pytest.mark.django_db
def test_untrack_view_unknown_returns_404(authed_client):
    with patch("letterboxd.api.views.services.untrack", side_effect=ServiceError("isn't tracked", status=404)):
        response = authed_client.post(
            "/api/v2/letterboxd/untrack",
            json.dumps({"url": "https://letterboxd.com/nope/watchlist/"}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    assert response.status_code == 404
    assert response.data["ok"] is False


@pytest.mark.django_db
def test_untrack_view_rejects_service_client(service_client):
    response = service_client.post(
        "/api/v2/letterboxd/untrack",
        json.dumps({"url": "https://letterboxd.com/bear/watchlist/"}),
        content_type="application/json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code == 403


def test_untrack_view_rejects_unauthenticated():
    client = APIClient()
    response = client.post(
        "/api/v2/letterboxd/untrack",
        json.dumps({"url": "https://letterboxd.com/bear/watchlist/"}),
        content_type="application/json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_tracked_view_returns_envelope(authed_client):
    result = {"message": "1 tracked list(s).", "lists": [{"id": 1, "url": "x"}]}
    with patch("letterboxd.api.views.services.list_tracked", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/letterboxd/tracked")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert len(response.data["lists"]) == 1


def test_tracked_view_rejects_unauthenticated():
    client = APIClient()
    response = client.get(
        "/api/v2/letterboxd/tracked",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_sync_tick_view_happy_path(authed_client):
    result = {"message": "Synced 2 tracked list(s).", "results": [{"url": "a"}, {"url": "b"}]}
    with patch("letterboxd.api.views.services.sync_tick", return_value=dict(result)) as mocked:
        response = authed_client.post(
            "/api/v2/letterboxd/sync-tick",
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
    with patch("letterboxd.api.views.services.sync_tick", return_value=dict(result)):
        response = service_client.post(
            "/api/v2/letterboxd/sync-tick",
            format="json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    assert response.status_code == 200
    assert response.data["ok"] is True


def test_sync_tick_view_rejects_unauthenticated():
    client = APIClient()
    response = client.post(
        "/api/v2/letterboxd/sync-tick",
        format="json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)

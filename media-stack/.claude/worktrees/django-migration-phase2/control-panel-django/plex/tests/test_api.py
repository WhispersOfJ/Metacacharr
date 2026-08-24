import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from core.api_base import ServiceError

_HDR = {"HTTP_HOST": "localhost", "REMOTE_ADDR": "127.0.0.1"}


# ---------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_scan_view_happy_path(authed_client):
    with patch("plex.api.views.services.scan", return_value={"message": "Scan started."}) as mocked:
        response = authed_client.post("/api/v2/plex/scan", **_HDR)
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data == {"ok": True, "message": "Scan started.", "time": response.data["time"]}


def test_scan_view_rejects_unauthenticated():
    response = APIClient().post("/api/v2/plex/scan", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# libraries
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_libraries_view_happy_path(authed_client):
    result = {"message": "1 Plex library.", "items": [{"key": "1", "title": "Movies"}]}
    with patch("plex.api.views.services.list_libraries", return_value=dict(result)):
        response = authed_client.get("/api/v2/plex/libraries", **_HDR)
    assert response.status_code == 200
    assert response.data["items"] == [{"key": "1", "title": "Movies"}]


def test_libraries_view_rejects_unauthenticated():
    response = APIClient().get("/api/v2/plex/libraries", **_HDR)
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_libraries_view_works_with_service_client(service_client):
    with patch("plex.api.views.services.list_libraries", return_value={"message": "x", "items": []}):
        response = service_client.get("/api/v2/plex/libraries", **_HDR)
    assert response.status_code == 200


# ---------------------------------------------------------------------
# empty-trash
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_empty_trash_view_happy_path(authed_client):
    with patch("plex.api.views.services.empty_trash", return_value={"message": "Trash emptied."}) as mocked:
        response = authed_client.post("/api/v2/plex/empty-trash?library=Movies", **_HDR)
    mocked.assert_called_once_with("Movies")
    assert response.status_code == 200
    assert response.data["message"] == "Trash emptied."


@pytest.mark.django_db
def test_empty_trash_view_no_library_param_defaults_to_none(authed_client):
    with patch("plex.api.views.services.empty_trash", return_value={"message": "Trash emptied."}) as mocked:
        response = authed_client.post("/api/v2/plex/empty-trash", **_HDR)
    mocked.assert_called_once_with(None)
    assert response.status_code == 200


@pytest.mark.django_db
def test_empty_trash_view_propagates_service_error(authed_client):
    with patch("plex.api.views.services.empty_trash", side_effect=ServiceError("No library found matching 'x'.")):
        response = authed_client.post("/api/v2/plex/empty-trash?library=x", **_HDR)
    assert response.status_code == 502
    assert response.data == {"ok": False, "message": "No library found matching 'x'."}


def test_empty_trash_view_rejects_unauthenticated():
    response = APIClient().post("/api/v2/plex/empty-trash", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_analyze_view_happy_path(authed_client):
    with patch("plex.api.views.services.analyze", return_value={"message": "Analysis queued."}) as mocked:
        response = authed_client.post("/api/v2/plex/analyze?library=Movies", **_HDR)
    mocked.assert_called_once_with("Movies")
    assert response.status_code == 200


def test_analyze_view_rejects_unauthenticated():
    response = APIClient().post("/api/v2/plex/analyze", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# optimize-db / clean-bundles
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_optimize_db_view_happy_path(authed_client):
    with patch("plex.api.views.services.optimize_db", return_value={"message": "Started."}):
        response = authed_client.post("/api/v2/plex/optimize-db", **_HDR)
    assert response.status_code == 200


def test_optimize_db_view_rejects_unauthenticated():
    response = APIClient().post("/api/v2/plex/optimize-db", **_HDR)
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_clean_bundles_view_happy_path(authed_client):
    with patch("plex.api.views.services.clean_bundles", return_value={"message": "Started."}):
        response = authed_client.post("/api/v2/plex/clean-bundles", **_HDR)
    assert response.status_code == 200


def test_clean_bundles_view_rejects_unauthenticated():
    response = APIClient().post("/api/v2/plex/clean-bundles", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# butler/<task>
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_butler_task_view_happy_path(authed_client):
    with patch("plex.api.views.services.butler_task",
               return_value={"message": "Butler task started: refresh-libraries."}) as mocked:
        response = authed_client.post("/api/v2/plex/butler/refresh-libraries", **_HDR)
    mocked.assert_called_once_with("refresh-libraries")
    assert response.status_code == 200


@pytest.mark.django_db
def test_butler_task_view_unknown_task_returns_400(authed_client):
    with patch("plex.api.views.services.butler_task",
               side_effect=ServiceError("Unknown Butler task 'bogus'.", status=400)):
        response = authed_client.post("/api/v2/plex/butler/bogus", **_HDR)
    assert response.status_code == 400
    assert response.data == {"ok": False, "message": "Unknown Butler task 'bogus'."}


def test_butler_task_view_rejects_unauthenticated():
    response = APIClient().post("/api/v2/plex/butler/refresh-libraries", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# updates
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_updates_view_happy_path(authed_client):
    result = {"message": "Plex is up to date.", "running_version": "1.40.0", "update_available": False,
              "releases": []}
    with patch("plex.api.views.services.get_updates", return_value=dict(result)):
        response = authed_client.get("/api/v2/plex/updates", **_HDR)
    assert response.status_code == 200
    assert response.data["running_version"] == "1.40.0"


def test_updates_view_rejects_unauthenticated():
    response = APIClient().get("/api/v2/plex/updates", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# scan-health
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_scan_health_view_happy_path(authed_client):
    result = {"message": "Plex is healthy.", "state": "healthy", "activities": [], "scanner_running": False,
              "dstate_threads": [], "fuse_waiting": 0, "mount_ok": True,
              "container": {"health": "healthy", "restart_count": 0},
              "nzbdav_queue": {"pending": 0, "processing": 0}, "recent_busy_db_errors": 0,
              "recent_busy_db_timestamps": [], "analysis_active": False, "analysis_batches": 0,
              "analysis_last_seconds": None, "log_tail": []}
    with patch("plex.api.views.services.scan_health", return_value=dict(result)):
        response = authed_client.get("/api/v2/plex/scan-health", **_HDR)
    assert response.status_code == 200
    assert response.data["state"] == "healthy"


def test_scan_health_view_rejects_unauthenticated():
    response = APIClient().get("/api/v2/plex/scan-health", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# duplicates
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_duplicates_view_happy_path(authed_client):
    with patch("plex.api.views.services.duplicates", return_value={"message": "1 movie(s).",
                                                                     "items": [{"title": "X"}]}) as mocked:
        response = authed_client.get("/api/v2/plex/duplicates", {"min_gb": "10"}, **_HDR)
    mocked.assert_called_once_with(10.0)
    assert response.status_code == 200
    assert response.data["items"] == [{"title": "X"}]


@pytest.mark.django_db
def test_duplicates_view_defaults_min_gb(authed_client):
    with patch("plex.api.views.services.duplicates", return_value={"message": "0.", "items": []}) as mocked:
        response = authed_client.get("/api/v2/plex/duplicates", **_HDR)
    mocked.assert_called_once_with(5.0)
    assert response.status_code == 200


def test_duplicates_view_rejects_unauthenticated():
    response = APIClient().get("/api/v2/plex/duplicates", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# tmdb-missing
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_tmdb_missing_view_happy_path(authed_client):
    with patch("plex.api.views.services.tmdb_missing", return_value={"message": "0.", "items": []}):
        response = authed_client.get("/api/v2/plex/tmdb-missing", **_HDR)
    assert response.status_code == 200


def test_tmdb_missing_view_rejects_unauthenticated():
    response = APIClient().get("/api/v2/plex/tmdb-missing", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_sessions_view_happy_path(authed_client):
    with patch("plex.api.views.services.sessions",
               return_value={"message": "1 active session(s).", "sessions": [{"title": "X"}]}):
        response = authed_client.get("/api/v2/plex/sessions", **_HDR)
    assert response.status_code == 200
    assert response.data["sessions"] == [{"title": "X"}]


def test_sessions_view_rejects_unauthenticated():
    response = APIClient().get("/api/v2/plex/sessions", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# recently-added
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_recently_added_view_happy_path(authed_client):
    with patch("plex.api.views.services.recently_added",
               return_value={"message": "1 item(s).", "items": [{"title": "X"}]}) as mocked:
        response = authed_client.get("/api/v2/plex/recently-added", {"limit": "5"}, **_HDR)
    mocked.assert_called_once_with(5)
    assert response.status_code == 200


@pytest.mark.django_db
def test_recently_added_view_defaults_limit(authed_client):
    with patch("plex.api.views.services.recently_added", return_value={"message": "0.", "items": []}) as mocked:
        response = authed_client.get("/api/v2/plex/recently-added", **_HDR)
    mocked.assert_called_once_with(15)


def test_recently_added_view_rejects_unauthenticated():
    response = APIClient().get("/api/v2/plex/recently-added", **_HDR)
    assert response.status_code in (401, 403)

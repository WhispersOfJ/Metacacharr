from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from core.api_base import ServiceError

# The Django test client's unauthenticated requests must pass
# HTTP_HOST/REMOTE_ADDR or VerifySameOriginMiddleware 403s them before the
# request ever reaches the permission class - producing a false-positive
# "unauthenticated rejection" pass even with broken auth. See prior tasks'
# reports (4, 7, 11) for the landmine this avoids.
_HDR = {"HTTP_HOST": "localhost", "REMOTE_ADDR": "127.0.0.1"}


def _decode(response):
    return b"".join(response.streaming_content).decode()


# ---------------------------------------------------------------------
# libraries
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_libraries_view_happy_path(authed_client):
    result = {"message": "1 poster-capable Plex libraries.", "items": [{"key": "1", "title": "Movies", "type": "movie"}]}
    with patch("posters.api.views.services.list_libraries", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/posters/libraries", **_HDR)
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["items"] == [{"key": "1", "title": "Movies", "type": "movie"}]


def test_libraries_view_rejects_unauthenticated():
    response = APIClient().get("/api/v2/posters/libraries", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_sync_view_happy_path(authed_client):
    with patch("posters.api.views.services.start_sync", return_value="Poster sync started for 'Movies' via tmdb.") as mocked:
        response = authed_client.post(
            "/api/v2/posters/sync", data={"library": "Movies"}, format="json", **_HDR,
        )
    mocked.assert_called_once_with("Movies", False, "tmdb")
    assert response.status_code == 200
    assert response.data["message"] == "Poster sync started for 'Movies' via tmdb."


@pytest.mark.django_db
def test_sync_view_passes_dry_run_and_source(authed_client):
    with patch("posters.api.views.services.start_sync", return_value="ok") as mocked:
        authed_client.post(
            "/api/v2/posters/sync", data={"library": "Movies", "dry_run": True, "source": "fanart"},
            format="json", **_HDR,
        )
    mocked.assert_called_once_with("Movies", True, "fanart")


@pytest.mark.django_db
def test_sync_view_rejects_invalid_source(authed_client):
    response = authed_client.post(
        "/api/v2/posters/sync", data={"library": "Movies", "source": "bogus"}, format="json", **_HDR,
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_sync_view_returns_409_when_already_running(authed_client):
    with patch("posters.api.views.services.start_sync", side_effect=ServiceError("already running", status=409)):
        response = authed_client.post(
            "/api/v2/posters/sync", data={"library": "Movies"}, format="json", **_HDR,
        )
    assert response.status_code == 409
    assert response.data["ok"] is False


def test_sync_view_rejects_unauthenticated():
    response = APIClient().post("/api/v2/posters/sync", data={"library": "Movies"}, format="json", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# sync/stream
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_sync_stream_view_yields_sse_lines(authed_client):
    def _gen():
        yield "data: line1\n\n"
        yield "data: line2\n\n"

    with patch("posters.api.views.services.sync_stream", return_value=_gen()):
        response = authed_client.get("/api/v2/posters/sync/stream", **_HDR)
    assert response.status_code == 200
    assert response["Content-Type"] == "text/event-stream"
    assert _decode(response) == "data: line1\n\ndata: line2\n\n"


@pytest.mark.django_db
def test_sync_stream_view_returns_404_when_not_started(authed_client):
    with patch("posters.api.views.services.sync_stream", side_effect=ServiceError("No poster sync has been started yet.", status=404)):
        response = authed_client.get("/api/v2/posters/sync/stream", **_HDR)
    assert response.status_code == 404


def test_sync_stream_view_rejects_unauthenticated():
    response = APIClient().get("/api/v2/posters/sync/stream", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# review
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_review_view_happy_path(authed_client):
    with patch("posters.api.views.services.start_review", return_value="Poster review started for 'Movies' via fanart.") as mocked:
        response = authed_client.post(
            "/api/v2/posters/review", data={"library": "Movies"}, format="json", **_HDR,
        )
    mocked.assert_called_once_with("Movies", "fanart")
    assert response.status_code == 200


@pytest.mark.django_db
def test_review_view_returns_409_when_already_running(authed_client):
    with patch("posters.api.views.services.start_review", side_effect=ServiceError("already running", status=409)):
        response = authed_client.post(
            "/api/v2/posters/review", data={"library": "Movies"}, format="json", **_HDR,
        )
    assert response.status_code == 409


def test_review_view_rejects_unauthenticated():
    response = APIClient().post("/api/v2/posters/review", data={"library": "Movies"}, format="json", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# review/stream
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_review_stream_view_yields_sse_lines(authed_client):
    def _gen():
        yield 'data: {"type": "start"}\n\n'

    with patch("posters.api.views.services.review_stream", return_value=_gen()):
        response = authed_client.get("/api/v2/posters/review/stream", **_HDR)
    assert response.status_code == 200
    assert _decode(response) == 'data: {"type": "start"}\n\n'


@pytest.mark.django_db
def test_review_stream_view_returns_404_when_not_started(authed_client):
    with patch("posters.api.views.services.review_stream", side_effect=ServiceError("No poster review has been started yet.", status=404)):
        response = authed_client.get("/api/v2/posters/review/stream", **_HDR)
    assert response.status_code == 404


def test_review_stream_view_rejects_unauthenticated():
    response = APIClient().get("/api/v2/posters/review/stream", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_apply_view_happy_path(authed_client):
    with patch("posters.api.views.services.apply_poster", return_value="Poster updated.") as mocked:
        response = authed_client.post(
            "/api/v2/posters/apply", data={"rating_key": "100", "url": "https://poster"},
            format="json", **_HDR,
        )
    mocked.assert_called_once_with("100", "https://poster")
    assert response.status_code == 200
    assert response.data["message"] == "Poster updated."


@pytest.mark.django_db
def test_apply_view_propagates_service_error(authed_client):
    with patch("posters.api.views.services.apply_poster", side_effect=ServiceError("Poster upload failed: boom")):
        response = authed_client.post(
            "/api/v2/posters/apply", data={"rating_key": "100", "url": "https://poster"},
            format="json", **_HDR,
        )
    assert response.status_code == 502


def test_apply_view_rejects_unauthenticated():
    response = APIClient().post(
        "/api/v2/posters/apply", data={"rating_key": "100", "url": "https://poster"}, format="json", **_HDR,
    )
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# gallery
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_gallery_view_happy_path(authed_client):
    result = {
        "message": "1 of 1 items in 'Movies'.", "items": [{"ratingKey": "100", "title": "Foo", "year": 2020, "thumbUrl": "/api/v2/posters/thumb/100"}],
        "total": 1, "offset": 0, "limit": 60, "library": "Movies", "type": "movie",
    }
    with patch("posters.api.views.services.gallery", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/posters/gallery?library=Movies", **_HDR)
    mocked.assert_called_once_with("Movies", 0, 60)
    assert response.status_code == 200
    assert response.data["total"] == 1


@pytest.mark.django_db
def test_gallery_view_passes_offset_and_limit(authed_client):
    with patch("posters.api.views.services.gallery", return_value={"message": "x", "items": [], "total": 0, "offset": 20, "limit": 10, "library": "Movies", "type": "movie"}) as mocked:
        authed_client.get("/api/v2/posters/gallery?library=Movies&offset=20&limit=10", **_HDR)
    mocked.assert_called_once_with("Movies", 20, 10)


@pytest.mark.django_db
def test_gallery_view_requires_library(authed_client):
    response = authed_client.get("/api/v2/posters/gallery", **_HDR)
    assert response.status_code == 400


@pytest.mark.django_db
def test_gallery_view_rejects_limit_over_max(authed_client):
    response = authed_client.get("/api/v2/posters/gallery?library=Movies&limit=500", **_HDR)
    assert response.status_code == 400


def test_gallery_view_rejects_unauthenticated():
    response = APIClient().get("/api/v2/posters/gallery?library=Movies", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# thumb
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_thumb_view_happy_path(authed_client):
    with patch("posters.api.views.services.thumb", return_value=(b"\xff\xd8", "image/jpeg")) as mocked:
        response = authed_client.get("/api/v2/posters/thumb/100", **_HDR)
    mocked.assert_called_once_with("100")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
    assert response.content == b"\xff\xd8"


@pytest.mark.django_db
def test_thumb_view_returns_404_when_not_found(authed_client):
    with patch("posters.api.views.services.thumb", side_effect=ServiceError("Could not fetch poster for 100: boom", status=404)):
        response = authed_client.get("/api/v2/posters/thumb/100", **_HDR)
    assert response.status_code == 404


def test_thumb_view_rejects_unauthenticated():
    response = APIClient().get("/api/v2/posters/thumb/100", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_scan_view_happy_path(authed_client):
    with patch("posters.api.views.services.start_scan", return_value="Poster quality scan started for 'Movies'.") as mocked:
        response = authed_client.post(
            "/api/v2/posters/scan", data={"library": "Movies"}, format="json", **_HDR,
        )
    mocked.assert_called_once_with("Movies")
    assert response.status_code == 200


@pytest.mark.django_db
def test_scan_view_returns_409_when_already_running(authed_client):
    with patch("posters.api.views.services.start_scan", side_effect=ServiceError("already running", status=409)):
        response = authed_client.post(
            "/api/v2/posters/scan", data={"library": "Movies"}, format="json", **_HDR,
        )
    assert response.status_code == 409


def test_scan_view_rejects_unauthenticated():
    response = APIClient().post("/api/v2/posters/scan", data={"library": "Movies"}, format="json", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# scan/stream
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_scan_stream_view_yields_sse_lines(authed_client):
    def _gen():
        yield 'data: {"type": "done"}\n\n'

    with patch("posters.api.views.services.scan_stream", return_value=_gen()):
        response = authed_client.get("/api/v2/posters/scan/stream", **_HDR)
    assert response.status_code == 200
    assert _decode(response) == 'data: {"type": "done"}\n\n'


@pytest.mark.django_db
def test_scan_stream_view_returns_404_when_not_started(authed_client):
    with patch("posters.api.views.services.scan_stream", side_effect=ServiceError("No poster quality scan has been started yet.", status=404)):
        response = authed_client.get("/api/v2/posters/scan/stream", **_HDR)
    assert response.status_code == 404


def test_scan_stream_view_rejects_unauthenticated():
    response = APIClient().get("/api/v2/posters/scan/stream", **_HDR)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------
# service-account access (X-Api-Key) - matches current_user_or_service
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_libraries_view_works_with_service_client(service_client):
    with patch("posters.api.views.services.list_libraries", return_value={"message": "x", "items": []}):
        response = service_client.get("/api/v2/posters/libraries", **_HDR)
    assert response.status_code == 200

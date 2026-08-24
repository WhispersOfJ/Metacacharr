from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

# See queue_app/tests/test_services.py's module docstring / the
# WatchState-app landmine documented in prior commits: the Django test
# client's unauthenticated requests must pass HTTP_HOST/REMOTE_ADDR or
# VerifySameOriginMiddleware 403s them before the request ever reaches the
# permission class - producing a false-positive "unauthenticated rejection"
# pass even with broken auth.
_HDR = {"HTTP_HOST": "localhost", "REMOTE_ADDR": "127.0.0.1"}


@pytest.mark.django_db
def test_status_view_returns_envelope(authed_client):
    queues = {
        "radarr": {"label": "Radarr", "total": 1, "downloading": [{"title": "Movie A"}],
                   "stalled": [], "queued": [], "importing": []},
        "nzbdav": {"label": "NzbDAV", "error": "unreachable"},
    }
    with patch("queue_app.api.views.services.aggregate_queue_status", return_value=dict(queues)) as mocked:
        response = authed_client.get("/api/v2/queue/status")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["message"] == "Queue status"
    assert response.data["queues"]["radarr"]["total"] == 1
    assert response.data["queues"]["nzbdav"] == {"label": "NzbDAV", "error": "unreachable"}


@pytest.mark.django_db
def test_status_view_works_with_service_client(service_client):
    with patch("queue_app.api.views.services.aggregate_queue_status", return_value={}):
        response = service_client.get("/api/v2/queue/status", **_HDR)
    assert response.status_code == 200
    assert response.data["ok"] is True


def test_status_view_rejects_unauthenticated():
    client = APIClient()
    response = client.get("/api/v2/queue/status", **_HDR)
    assert response.status_code in (401, 403)

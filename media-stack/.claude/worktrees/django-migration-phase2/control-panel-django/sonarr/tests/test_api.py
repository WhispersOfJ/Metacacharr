import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_monitor_episodes_fix_view_happy_path_authed(authed_client):
    """POST /api/v2/sonarr/monitor-episodes-fix succeeds via session auth."""
    with patch(
        "sonarr.api.views.services.fix_monitored_episodes",
        return_value={"fixed": 3, "monitored_series": 2},
    ):
        response = authed_client.post(
            "/api/v2/sonarr/monitor-episodes-fix",
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )

    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["ok"] is True
    assert data["message"] == "Episode monitoring fixed"
    assert data["fixed"] == 3
    assert data["monitored_series"] == 2


@pytest.mark.django_db
def test_monitor_episodes_fix_view_happy_path_service_key(service_client):
    """POST /api/v2/sonarr/monitor-episodes-fix also succeeds via service key
    (default tier - stack-sonarr-monitor-episodes-fix.fish calls this
    unattended)."""
    with patch(
        "sonarr.api.views.services.fix_monitored_episodes",
        return_value={"fixed": 0, "monitored_series": 0},
    ):
        response = service_client.post(
            "/api/v2/sonarr/monitor-episodes-fix",
            format="json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )

    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["ok"] is True
    assert data["fixed"] == 0


def test_monitor_episodes_fix_view_rejects_unauthenticated():
    """Unauthenticated requests are rejected."""
    client = APIClient()
    response = client.post("/api/v2/sonarr/monitor-episodes-fix", format="json")
    assert response.status_code in (401, 403)

"""host/api/views.py tests - one happy-path test per endpoint (services
mocked), service_client 403 on the two session-only routes (patch_settings,
prune_disk), unauthenticated rejection, and the SSE log-stream view test
per the posters streaming_content pattern.
"""
import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from core.api_base import ServiceError

_HDR = {"HTTP_HOST": "localhost", "REMOTE_ADDR": "127.0.0.1"}


@pytest.mark.django_db
def test_status_view_returns_envelope(authed_client):
    result = {"radarr": {"state": "running", "health": "healthy"}}
    with patch("host.api.views.services.get_status", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/host/status")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["containers"] == result


@pytest.mark.django_db
def test_containers_view_returns_envelope(authed_client):
    items = [{"name": "radarr", "label": "Radarr", "is_self": False}]
    with patch("host.api.views.services.list_containers", return_value=list(items)) as mocked:
        response = authed_client.get("/api/v2/host/containers")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["items"] == items


@pytest.mark.django_db
def test_container_restart_view(authed_client):
    with patch("host.api.views.services.restart_container", return_value="Radarr restarted.") as mocked:
        response = authed_client.post("/api/v2/host/container/radarr/restart", format="json", **_HDR)
    mocked.assert_called_once_with("radarr", False)
    assert response.status_code == 200
    assert response.data["message"] == "Radarr restarted."


@pytest.mark.django_db
def test_container_restart_view_activated_query_param(authed_client):
    with patch("host.api.views.services.restart_container", return_value="Plex restarted.") as mocked:
        response = authed_client.post("/api/v2/host/container/plex/restart?activated=true", format="json", **_HDR)
    mocked.assert_called_once_with("plex", True)
    assert response.status_code == 200


@pytest.mark.django_db
def test_container_stop_view(authed_client):
    with patch("host.api.views.services.stop_container", return_value="Radarr stopped.") as mocked:
        response = authed_client.post("/api/v2/host/container/radarr/stop", format="json", **_HDR)
    mocked.assert_called_once_with("radarr")
    assert response.status_code == 200


@pytest.mark.django_db
def test_container_start_view(authed_client):
    with patch("host.api.views.services.start_container", return_value="Radarr started.") as mocked:
        response = authed_client.post("/api/v2/host/container/radarr/start", format="json", **_HDR)
    mocked.assert_called_once_with("radarr")
    assert response.status_code == 200


@pytest.mark.django_db
def test_container_logs_stream_view_yields_sse(authed_client):
    def fake_stream(name, tail):
        assert name == "radarr"
        assert tail == 100

        def gen():
            yield "data: line one\n\n"
            yield "data: line two\n\n"

        return gen()

    with patch("host.api.views.services.stream_container_logs", side_effect=fake_stream):
        response = authed_client.get("/api/v2/host/container/radarr/logs/stream", **_HDR)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/event-stream")
    body = b"".join(response.streaming_content).decode()
    assert body == "data: line one\n\ndata: line two\n\n"


@pytest.mark.django_db
def test_restart_all_view(authed_client):
    with patch("host.api.views.services.restart_all", return_value="Restarting 2 containers: radarr, sonarr") as mocked:
        response = authed_client.post("/api/v2/host/stack/restart-all", format="json", **_HDR)
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["message"].startswith("Restarting 2 containers")


@pytest.mark.django_db
def test_settings_get_view(authed_client):
    settings = {"theme": "amber", "failed_pending_storm_threshold": 15,
                "loop_review_profile_threshold": 8, "recent_values": {}}
    with patch("host.api.views.services.get_settings", return_value=dict(settings)) as mocked:
        response = authed_client.get("/api/v2/host/settings")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["theme"] == "amber"


@pytest.mark.django_db
def test_settings_patch_view_session_only(authed_client):
    settings = {"theme": "green", "failed_pending_storm_threshold": 15,
                "loop_review_profile_threshold": 8, "recent_values": {}}
    with patch("host.api.views.services.patch_settings", return_value=dict(settings)) as mocked:
        response = authed_client.patch(
            "/api/v2/host/settings",
            json.dumps({"theme": "green"}),
            content_type="application/json",
            **_HDR,
        )
    mocked.assert_called_once_with({"theme": "green"})
    assert response.status_code == 200
    assert response.data["theme"] == "green"


@pytest.mark.django_db
def test_settings_patch_service_client_gets_403(service_client):
    """Critical regression test: a service (API-key) client must NEVER be
    able to PATCH settings, even though GET works for it - the same
    current_user-vs-current_user_or_service split as the FastAPI era."""
    response = service_client.patch(
        "/api/v2/host/settings",
        json.dumps({"theme": "green"}),
        content_type="application/json",
        **_HDR,
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_resource_check_view(authed_client):
    result = {"message": "1 container(s) missing mem_limit and/or cpus.", "containers": [{"name": "sonarr"}]}
    with patch("host.api.views.services.resource_check", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/host/resource-check")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["containers"] == [{"name": "sonarr"}]


@pytest.mark.django_db
def test_disk_health_view(authed_client):
    result = {"message": "/mnt: 50.0% used, 1.0GB free.", "mount": {"percent": 50.0}, "reclaimable": {}}
    with patch("host.api.views.services.disk_health", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/host/disk-health")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["mount"]["percent"] == 50.0


@pytest.mark.django_db
def test_prune_disk_view_session_only(authed_client):
    with patch("host.api.views.services.prune_disk", return_value="Reclaimed 300B (1 image(s), 1 volume(s)).") as mocked:
        response = authed_client.post(
            "/api/v2/host/disk-health/prune",
            json.dumps({"confirm": True}),
            content_type="application/json",
            **_HDR,
        )
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert "Reclaimed" in response.data["message"]


@pytest.mark.django_db
def test_prune_disk_rejects_missing_confirm(authed_client):
    with patch("host.api.views.services.prune_disk") as mocked:
        response = authed_client.post(
            "/api/v2/host/disk-health/prune",
            json.dumps({}),
            content_type="application/json",
            **_HDR,
        )
    assert response.status_code == 400
    mocked.assert_not_called()


@pytest.mark.django_db
def test_prune_disk_service_client_gets_403(service_client):
    response = service_client.post(
        "/api/v2/host/disk-health/prune",
        json.dumps({"confirm": True}),
        content_type="application/json",
        **_HDR,
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_host_resources_view(authed_client):
    result = {"message": "CPU 42.0%, RAM 50.0%.", "cpu_percent": 42.0, "mem_percent": 50.0}
    with patch("host.api.views.services.host_resources", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/host/host-resources")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["cpu_percent"] == 42.0


@pytest.mark.django_db
def test_log_levels_view(authed_client):
    result = {"message": "All apps at info (or non-debug).", "levels": {"radarr": "info"}}
    with patch("host.api.views.services.log_levels", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/host/log-levels")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["levels"] == {"radarr": "info"}


@pytest.mark.django_db
def test_reset_log_levels_view(authed_client):
    with patch("host.api.views.services.reset_log_levels", return_value="Reset 1 app(s) to info: radarr") as mocked:
        response = authed_client.post("/api/v2/host/log-levels/reset", format="json", **_HDR)
    mocked.assert_called_once_with()
    assert response.status_code == 200


@pytest.mark.django_db
def test_oom_check_view(authed_client):
    result = {"message": "1 container(s) have been OOM-killed: seerr", "containers": ["seerr"]}
    with patch("host.api.views.services.oom_check", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/host/oom-check")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["containers"] == ["seerr"]


@pytest.mark.django_db
def test_disk_usage_view(authed_client):
    result = {"message": "2 app config directories.", "sizes": [{"app": "radarr", "mb": 1.0}]}
    with patch("host.api.views.services.disk_usage", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/host/disk-usage")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["sizes"][0]["app"] == "radarr"


@pytest.mark.django_db
def test_mount_health_view(authed_client):
    result = {"message": "All known mounts resolve cleanly.", "mounts": [{"mount": "remote/nzbdav", "status": "healthy"}]}
    with patch("host.api.views.services.mount_health", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/host/mount-health")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["mounts"][0]["status"] == "healthy"


@pytest.mark.django_db
def test_perms_check_view(authed_client):
    result = {"message": "1 file(s) unreadable by group/other:", "files": ["config/radarr/locked.conf"]}
    with patch("host.api.views.services.perms_check", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/host/perms-check")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert len(response.data["files"]) == 1


@pytest.mark.django_db
def test_image_check_view(authed_client):
    result = {"message": "No newer digests found.", "images": [{"name": "radarr", "update_available": False}]}
    with patch("host.api.views.services.image_check", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/host/image-check")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["images"][0]["name"] == "radarr"


@pytest.mark.django_db
def test_version_view(authed_client):
    result = {"message": "README declares v11.17.0. 15/15 containers running.",
              "version": "v11.17.0", "running": 15, "total": 15}
    with patch("host.api.views.services.get_version", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/host/version")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["version"] == "v11.17.0"


@pytest.mark.django_db
def test_docs_readme_view(authed_client):
    with patch("host.api.views.services.docs_readme", return_value="# hello stack") as mocked:
        response = authed_client.get("/api/v2/host/docs/readme")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["text"] == "# hello stack"
    assert response.data["message"] == "README.md"


@pytest.mark.django_db
def test_notify_test_view(authed_client):
    with patch("host.api.views.services.notify_test", return_value="Test notification sent.") as mocked:
        response = authed_client.post("/api/v2/host/notify/test", format="json", **_HDR)
    mocked.assert_called_once_with()
    assert response.status_code == 200


@pytest.mark.django_db
def test_top_view(authed_client):
    result = {"message": "Top 2 containers by cpu.", "items": [{"name": "busy", "cpu_percent": 90.0}]}
    with patch("host.api.views.services.stack_top", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/host/top")
    mocked.assert_called_once_with("cpu", 10)
    assert response.status_code == 200
    assert response.data["items"][0]["name"] == "busy"


@pytest.mark.django_db
def test_top_view_respects_query(authed_client):
    result = {"message": "Top 1 containers by mem.", "items": [{"name": "busy", "mem_percent": 90.0}]}
    with patch("host.api.views.services.stack_top", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/host/top?by=mem&limit=1")
    mocked.assert_called_once_with("mem", 1)
    assert response.status_code == 200


@pytest.mark.django_db
def test_top_view_service_error_propagates(authed_client):
    with patch("host.api.views.services.stack_top", side_effect=ServiceError("'by' must be 'cpu' or 'mem'.", status=400)):
        response = authed_client.get("/api/v2/host/top?by=gpu")
    assert response.status_code == 400
    assert response.data["ok"] is False


def test_host_endpoints_reject_unauthenticated():
    client = APIClient()
    checks = [
        ("get", "/api/v2/host/status"),
        ("get", "/api/v2/host/containers"),
        ("get", "/api/v2/host/settings"),
        ("post", "/api/v2/host/stack/restart-all"),
    ]
    for method, url in checks:
        response = getattr(client, method)(url, format="json", **_HDR)
        assert response.status_code in (401, 403), f"{method.upper()} {url} -> {response.status_code}"

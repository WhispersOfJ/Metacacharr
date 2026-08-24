"""arr/api/views.py tests - happy path per endpoint (services mocked),
unauthenticated rejection, and at least one partial-failure/error-branch
test per aggregation route.
"""
import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from core.api_base import ServiceError

_HDR = {"HTTP_HOST": "localhost", "REMOTE_ADDR": "127.0.0.1"}


@pytest.mark.django_db
def test_rss_sync_view(authed_client):
    with patch("arr.api.views.services.rss_sync", return_value="Radarr RSS sync started.") as mocked:
        response = authed_client.post("/api/v2/arr/radarr/rss-sync", format="json", **_HDR)
    mocked.assert_called_once_with("radarr")
    assert response.status_code == 200
    assert response.data["message"] == "Radarr RSS sync started."


@pytest.mark.django_db
def test_search_missing_view(authed_client):
    with patch("arr.api.views.services.search_missing", return_value="Sonarr search started.") as mocked:
        response = authed_client.post("/api/v2/arr/sonarr/search-missing", format="json", **_HDR)
    mocked.assert_called_once_with("sonarr")
    assert response.status_code == 200


@pytest.mark.django_db
def test_search_status_view(authed_client):
    with patch("arr.api.views.services.search_status", return_value={"enabled": True}) as mocked:
        response = authed_client.get("/api/v2/arr/radarr/search-status")
    mocked.assert_called_once_with("radarr")
    assert response.status_code == 200
    assert response.data["enabled"] is True


@pytest.mark.django_db
def test_search_toggle_view(authed_client):
    with patch("arr.api.views.services.search_toggle", return_value="enabled on 1 indexer(s)") as mocked:
        response = authed_client.post("/api/v2/arr/radarr/search-toggle?enabled=true", format="json", **_HDR)
    mocked.assert_called_once_with("radarr", True)
    assert response.status_code == 200


@pytest.mark.django_db
def test_search_toggle_view_missing_enabled_400(authed_client):
    with patch("arr.api.views.services.search_toggle") as mocked:
        response = authed_client.post("/api/v2/arr/radarr/search-toggle", format="json", **_HDR)
    assert response.status_code == 400
    mocked.assert_not_called()


@pytest.mark.django_db
def test_command_backlog_view(authed_client):
    result = {"message": "Radarr: 3 commands total.", "total": 3, "counts": {}, "running": [],
              "queued_total": 0, "oldest_queued": []}
    with patch("arr.api.views.services.command_backlog", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/arr/radarr/command-backlog")
    mocked.assert_called_once_with("radarr")
    assert response.status_code == 200
    assert response.data["total"] == 3


@pytest.mark.django_db
def test_unstick_view(authed_client):
    result = {"message": "Removed, blocklisted, and re-searching 1 stuck download(s) in Radarr.",
              "removed": ["Movie.One"], "errors": []}
    with patch("arr.api.views.services.unstick", return_value=dict(result)) as mocked:
        response = authed_client.post("/api/v2/arr/radarr/unstick", format="json", **_HDR)
    mocked.assert_called_once_with("radarr")
    assert response.status_code == 200
    assert response.data["removed"] == ["Movie.One"]


@pytest.mark.django_db
def test_unstick_importing_view(authed_client):
    result = {"message": "Radarr: checked 1 importing item(s) - 1 broken/blocklisted.",
              "results": [{"title": "Movie", "verdict": "broken-blocklisted"}]}
    with patch("arr.api.views.services.unstick_importing", return_value=dict(result)) as mocked:
        response = authed_client.post("/api/v2/arr/radarr/unstick-importing", format="json", **_HDR)
    mocked.assert_called_once_with("radarr")
    assert response.status_code == 200


@pytest.mark.django_db
def test_import_starvation_view(authed_client):
    result = {"message": "Every app is importing in step with its grabs.", "apps": {},
              "starved": [], "lagging": [], "remediated": {}}
    with patch("arr.api.views.services.import_starvation_status", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/arr/import-starvation")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["ok"] is True


@pytest.mark.django_db
def test_queue_autofix_view(authed_client):
    result = {"message": "Fixed 1 stuck queue item(s) across radarr/sonarr.", "radarr": {},
              "sonarr": {}, "nzbdav": {}, "import_starvation": {}}
    with patch("arr.api.views.services.queue_autofix", return_value=dict(result)) as mocked:
        response = authed_client.post("/api/v2/arr/queue-autofix", format="json", **_HDR)
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert "Fixed 1 stuck queue item(s)" in response.data["message"]


@pytest.mark.django_db
def test_loop_candidates_view(authed_client):
    result = {"message": "Radarr: 2 looping candidate(s) in the last 6h.", "app": "radarr",
              "candidates": [{"id": 1, "occurrences": 2}]}
    with patch("arr.api.views.services.loop_candidates", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/arr/radarr/loop-candidates")
    mocked.assert_called_once_with("radarr", 6.0)
    assert response.status_code == 200
    assert response.data["candidates"][0]["id"] == 1


@pytest.mark.django_db
def test_loop_candidates_view_respects_hours(authed_client):
    result = {"message": "x", "app": "radarr", "candidates": []}
    with patch("arr.api.views.services.loop_candidates", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/arr/radarr/loop-candidates?hours=24")
    mocked.assert_called_once_with("radarr", 24.0)
    assert response.status_code == 200


@pytest.mark.django_db
def test_unmonitor_view(authed_client):
    result = {"message": "Unmonitored 2 item(s) in Radarr.", "ids": [1, 2]}
    with patch("arr.api.views.services.unmonitor", return_value=dict(result)) as mocked:
        response = authed_client.post(
            "/api/v2/arr/radarr/unmonitor",
            json.dumps({"ids": [1, 2]}),
            content_type="application/json",
            **_HDR,
        )
    mocked.assert_called_once_with("radarr", [1, 2])
    assert response.status_code == 200


@pytest.mark.django_db
def test_manual_import_get_view(authed_client):
    items = [{"name": "Movie.One.mkv", "file": {"movieId": 3}}]
    with patch("arr.api.views.services.manual_import_candidates", return_value=list(items)) as mocked:
        response = authed_client.get("/api/v2/arr/radarr/manual-import")
    mocked.assert_called_once_with("radarr")
    assert response.status_code == 200
    assert response.data["items"] == items


@pytest.mark.django_db
def test_manual_import_post_view(authed_client):
    body = {"path": "/data/Movie.One.mkv", "quality": {"quality": {"name": "1080p"}}, "languages": []}
    with patch("arr.api.views.services.manual_import_execute", return_value='Import started for "Movie.One.mkv".') as mocked:
        response = authed_client.post(
            "/api/v2/arr/radarr/manual-import",
            json.dumps(body),
            content_type="application/json",
            **_HDR,
        )
    # None-valued optional fields are dropped by the view before services
    mocked.assert_called_once()
    call_payload = mocked.call_args[0][1]
    assert call_payload["path"] == "/data/Movie.One.mkv"
    assert "movieId" not in call_payload
    assert response.status_code == 200


@pytest.mark.django_db
def test_manual_import_post_view_missing_required_400(authed_client):
    with patch("arr.api.views.services.manual_import_execute") as mocked:
        response = authed_client.post(
            "/api/v2/arr/radarr/manual-import",
            json.dumps({"path": "/x.mkv"}),
            content_type="application/json",
            **_HDR,
        )
    assert response.status_code == 400
    mocked.assert_not_called()


@pytest.mark.django_db
def test_manual_import_all_view(authed_client):
    with patch("arr.api.views.services.manual_import_all", return_value="Import started for 2 file(s) in Radarr.") as mocked:
        response = authed_client.post("/api/v2/arr/radarr/manual-import-all", format="json", **_HDR)
    mocked.assert_called_once_with("radarr")
    assert response.status_code == 200


@pytest.mark.django_db
def test_missing_aired_view(authed_client):
    items = [{"title": "Aired Movie", "year": 2024, "aired": "2024-01-01"}]
    with patch("arr.api.views.services.missing_aired", return_value=list(items)) as mocked:
        response = authed_client.get("/api/v2/arr/radarr/missing-aired")
    mocked.assert_called_once_with("radarr")
    assert response.status_code == 200
    assert response.data["items"] == items


@pytest.mark.django_db
def test_blocklist_view(authed_client):
    result = {"message": "2 total blocklist entry(ies) in Radarr (1 shown).", "total": 2, "records": [{"id": 1}]}
    with patch("arr.api.views.services.blocklist", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/arr/radarr/blocklist")
    mocked.assert_called_once_with("radarr", 50)
    assert response.status_code == 200
    assert response.data["total"] == 2


@pytest.mark.django_db
def test_blocklist_clear_view(authed_client):
    result = {"message": "Cleared 2 blocklist entry(ies) from Radarr.", "cleared": 2}
    with patch("arr.api.views.services.blocklist_clear", return_value=dict(result)) as mocked:
        response = authed_client.post("/api/v2/arr/radarr/blocklist/clear", format="json", **_HDR)
    mocked.assert_called_once_with("radarr")
    assert response.status_code == 200


@pytest.mark.django_db
def test_backlog_status_view(authed_client):
    result = {"message": "2 item(s) missing across 2 apps.", "apps": {"radarr": {"missing": 2}}}
    with patch("arr.api.views.services.backlog_status", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/arr/backlog-status")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["apps"]["radarr"]["missing"] == 2


@pytest.mark.django_db
def test_logs_view(authed_client):
    with patch("arr.api.views.services.logs", return_value="line one\nline two\n") as mocked:
        response = authed_client.get("/api/v2/arr/radarr/logs")
    mocked.assert_called_once_with("radarr", 100)
    assert response.status_code == 200
    assert response.data["log"] == "line one\nline two\n"


@pytest.mark.django_db
def test_command_queue_summary_view(authed_client):
    result = {"message": "2 commands queued across 3 apps.", "apps": {"radarr": {"queued": 1}}}
    with patch("arr.api.views.services.command_queue_summary", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/arr/command-queue-summary")
    mocked.assert_called_once_with()
    assert response.status_code == 200
    assert response.data["apps"]["radarr"]["queued"] == 1


@pytest.mark.django_db
def test_recently_added_view(authed_client):
    result = {"message": "2 most recently added to Radarr.", "items": [{"title": "New"}]}
    with patch("arr.api.views.services.recently_added", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/arr/radarr/recently-added")
    mocked.assert_called_once_with("radarr", 10)
    assert response.status_code == 200


@pytest.mark.django_db
def test_queue_errors_view(authed_client):
    result = {"message": "1 queue item(s) flagged with an error/warning across 2 apps.",
              "apps": {"radarr": [{"title": "Movie.One", "status": "error"}]}}
    with patch("arr.api.views.services.queue_errors", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/arr/queue-errors")
    mocked.assert_called_once_with()
    assert response.status_code == 200


@pytest.mark.django_db
def test_cutoff_unmet_view(authed_client):
    result = {"message": "1 item(s) below quality cutoff in Radarr.", "items": [{"title": "Movie"}], "total": 1}
    with patch("arr.api.views.services.cutoff_unmet", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/arr/radarr/cutoff-unmet")
    mocked.assert_called_once_with("radarr", 20)
    assert response.status_code == 200


@pytest.mark.django_db
def test_import_lists_view(authed_client):
    result = {"message": "1 import list(s) configured for Radarr.", "items": [{"name": "Trakt"}]}
    with patch("arr.api.views.services.import_lists", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/arr/radarr/import-lists")
    mocked.assert_called_once_with("radarr")
    assert response.status_code == 200


@pytest.mark.django_db
def test_import_list_implementations_view(authed_client):
    result = {"message": "2 import-list implementation(s) available on Radarr.", "items": [{"implementation": "PlexImport"}]}
    with patch("arr.api.views.services.import_list_implementations", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/arr/radarr/import-list/implementations")
    mocked.assert_called_once_with("radarr")
    assert response.status_code == 200


@pytest.mark.django_db
def test_import_list_add_view(authed_client):
    result = {"message": "Import list 'My List' (TMDbKeywordImport) added to Radarr.", "id": 5}
    body = {"implementation": "TMDbKeywordImport", "name": "My List", "fields": {"keywordId": "123"}}
    with patch("arr.api.views.services.import_list_add", return_value=dict(result)) as mocked:
        response = authed_client.post(
            "/api/v2/arr/radarr/import-list/add",
            json.dumps(body),
            content_type="application/json",
            **_HDR,
        )
    mocked.assert_called_once_with("radarr", {
        "implementation": "TMDbKeywordImport", "name": "My List", "fields": {"keywordId": "123"},
        "search_on_add": True, "monitor": None, "minimum_availability": "released",
    })
    assert response.status_code == 200
    assert response.data["id"] == 5


@pytest.mark.django_db
def test_customformat_snapshot_view(authed_client):
    result = {"message": "1 custom format(s) across 1 profile(s) on Radarr.", "profiles": {"Any": {}}}
    with patch("arr.api.views.services.customformat_snapshot", return_value=dict(result)) as mocked:
        response = authed_client.get("/api/v2/arr/radarr/customformat-snapshot")
    mocked.assert_called_once_with("radarr")
    assert response.status_code == 200


@pytest.mark.django_db
def test_arr_endpoints_work_with_service_client(service_client):
    """The whole app is default-tier - service (API-key) clients must work
    on both read-only and mutating routes (the unattended cron loop calls
    queue-autofix/unstick via service key)."""
    with patch("arr.api.views.services.queue_autofix", return_value={"message": "Fixed 0 stuck queue item(s)."}):
        response = service_client.post("/api/v2/arr/queue-autofix", format="json", **_HDR)
    assert response.status_code == 200

    with patch("arr.api.views.services.search_missing", return_value="Sonarr search started."):
        response = service_client.post("/api/v2/arr/sonarr/search-missing", format="json", **_HDR)
    assert response.status_code == 200


@pytest.mark.django_db
def test_arr_endpoint_error_branch_renders_envelope(authed_client):
    with patch("arr.api.views.services.search_status",
               side_effect=ServiceError("Unknown app 'nope'.", status=404)):
        response = authed_client.get("/api/v2/arr/nope/search-status")
    assert response.status_code == 404
    assert response.data["ok"] is False
    assert response.data["message"] == "Unknown app 'nope'."


def test_arr_endpoints_reject_unauthenticated():
    client = APIClient()
    checks = [
        ("get", "/api/v2/arr/radarr/search-status"),
        ("post", "/api/v2/arr/radarr/unstick"),
        ("get", "/api/v2/arr/backlog-status"),
        ("post", "/api/v2/arr/queue-autofix"),
    ]
    for method, url in checks:
        response = getattr(client, method)(url, format="json", **_HDR)
        assert response.status_code in (401, 403), f"{method.upper()} {url} -> {response.status_code}"

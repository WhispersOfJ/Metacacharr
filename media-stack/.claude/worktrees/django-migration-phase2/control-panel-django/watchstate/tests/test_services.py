"""Tests for watchstate.services, ported from the FastAPI-era
control-panel/services/watchstate/router.py.

WatchState's own REST API lives at http://watchstate:8080/v1/api and is
mocked here with pytest_httpx rather than exercised for real.
"""
import httpx
import pytest

from core.api_base import ServiceError
from watchstate.services import get_history, get_status, queue_import


def test_get_status_success(httpx_mock):
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/system/version",
        json={"version": "1.2.3"},
    )
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/backends",
        json=[
            {
                "name": "plex",
                "url": "http://plex:32400",
                "import": {"enabled": True, "lastSync": "2026-08-01T00:00:00"},
                "export": {"enabled": False},
            }
        ],
    )
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/tasks/import",
        json={"enabled": True, "timer": "*/10 * * * *", "next_run": "2026-08-22T12:10:00",
              "prev_run": "2026-08-22T12:00:00", "queued": False},
    )
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/history?perpage=1",
        json={"history": [{"id": 1}], "paging": {"total": 42}},
    )

    result = get_status()

    assert result["version"] == "1.2.3"
    assert result["tracked"] == 42
    assert result["backend"] == {
        "name": "plex",
        "url": "http://plex:32400",
        "import_enabled": True,
        "export_enabled": False,
        "last_sync": "2026-08-01T00:00:00",
    }
    assert result["task"] == {
        "enabled": True,
        "timer": "*/10 * * * *",
        "next_run": "2026-08-22T12:10:00",
        "prev_run": "2026-08-22T12:00:00",
        "queued": False,
    }
    assert "42 item(s) tracked" in result["message"]


def test_get_status_no_backend_registered(httpx_mock):
    httpx_mock.add_response(url="http://watchstate:8080/v1/api/system/version", json={"version": "1.2.3"})
    httpx_mock.add_response(url="http://watchstate:8080/v1/api/backends", json=[])
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/tasks/import",
        json={"enabled": False, "timer": None, "next_run": None, "prev_run": None, "queued": False},
    )
    httpx_mock.add_response(url="http://watchstate:8080/v1/api/history?perpage=1", json={"history": [], "paging": {"total": 0}})

    result = get_status()

    assert result["backend"] is None
    assert "scripts/watchstate-provision.py" in result["message"]


def test_get_status_upstream_down_raises_service_error(httpx_mock):
    httpx_mock.add_response(url="http://watchstate:8080/v1/api/system/version", status_code=500, json={})
    with pytest.raises(ServiceError):
        get_status()


def test_get_status_connection_error_raises_service_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    with pytest.raises(ServiceError):
        get_status()


def test_get_status_backends_list_failure_raises_service_error(httpx_mock):
    httpx_mock.add_response(url="http://watchstate:8080/v1/api/system/version", json={"version": "1.2.3"})
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/backends",
        status_code=500,
        json={"error": {"code": 500, "message": "boom"}},
    )
    with pytest.raises(ServiceError):
        get_status()


def test_get_status_import_task_failure_raises_service_error(httpx_mock):
    httpx_mock.add_response(url="http://watchstate:8080/v1/api/system/version", json={"version": "1.2.3"})
    httpx_mock.add_response(url="http://watchstate:8080/v1/api/backends", json=[])
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/tasks/import",
        status_code=404,
        json={"error": {"code": 404, "message": "No Results."}},
    )
    with pytest.raises(ServiceError):
        get_status()


def test_get_status_queued_import_message(httpx_mock):
    httpx_mock.add_response(url="http://watchstate:8080/v1/api/system/version", json={"version": "1.2.3"})
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/backends",
        json=[{"name": "plex", "url": "http://plex:32400", "import": {"enabled": True}, "export": {"enabled": False}}],
    )
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/tasks/import",
        json={"enabled": True, "timer": None, "next_run": None, "prev_run": None, "queued": True},
    )
    httpx_mock.add_response(url="http://watchstate:8080/v1/api/history?perpage=1", json={"history": [], "paging": {"total": 3}})

    result = get_status()

    assert "Import queued, 3 item(s) tracked." == result["message"]
    assert result["task"]["queued"] is True


def test_queue_import_success(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="http://watchstate:8080/v1/api/tasks/import/queue",
        json={"id": "abc123"},
        status_code=200,
    )
    result = queue_import()
    assert result["event_id"] == "abc123"
    assert result["task"] == "import"
    assert "queued" in result["message"].lower()


def test_queue_import_upstream_error_raises_service_error(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="http://watchstate:8080/v1/api/tasks/import/queue",
        status_code=500,
        json={"error": {"code": 500, "message": "boom"}},
    )
    with pytest.raises(ServiceError):
        queue_import()


def test_queue_import_upstream_error_with_non_dict_error_value(httpx_mock):
    """_error() falls back to str(error) when the error field is a bare
    string rather than a {"code", "message"} dict."""
    httpx_mock.add_response(
        method="POST",
        url="http://watchstate:8080/v1/api/tasks/import/queue",
        status_code=500,
        json={"error": "upstream exploded"},
    )
    with pytest.raises(ServiceError, match="upstream exploded"):
        queue_import()


def test_queue_import_non_json_response_body(httpx_mock):
    """_request() tolerates a non-JSON response body (empty dict, not a
    crash) - queue_import() still reports the queue failure cleanly."""
    httpx_mock.add_response(
        method="POST",
        url="http://watchstate:8080/v1/api/tasks/import/queue",
        status_code=500,
        content=b"not json",
    )
    with pytest.raises(ServiceError):
        queue_import()


def test_get_history_success_shapes_rows(httpx_mock):
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/history?perpage=20",
        json={
            "history": [
                {
                    "id": 5,
                    "full_title": "The Matrix",
                    "type": "movie",
                    "year": 1999,
                    "season": None,
                    "episode": None,
                    "watched": 1,
                    "via": "plex",
                    "updated_at": 1735689600,
                }
            ],
            "paging": {"total": 1},
        },
    )
    result = get_history()
    assert result["total"] == 1
    assert result["shown"] == 1
    row = result["history"][0]
    assert row["id"] == 5
    assert row["title"] == "The Matrix"
    assert row["watched"] is True
    assert row["updated_at"] is not None
    assert "1 item(s)" in result["message"]


def test_get_history_filters_by_item(httpx_mock):
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/history?perpage=20&title=matrix",
        json={"history": [], "paging": {"total": 0}},
    )
    result = get_history(item="matrix")
    assert result["history"] == []
    assert "matrix" in result["message"]


def test_get_history_empty_database_returns_404_as_empty(httpx_mock):
    """An empty WatchState database answers 404, not an empty list - this
    must not surface as a failure (see router.py's module docstring)."""
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/history?perpage=20",
        status_code=404,
        json={"error": {"code": 404, "message": "No Results."}},
    )
    result = get_history()
    assert result["history"] == []
    assert result["total"] == 0
    assert "No watch history" in result["message"]


def test_get_history_rejects_non_positive_limit():
    with pytest.raises(ServiceError) as exc_info:
        get_history(limit=0)
    assert exc_info.value.status_code == 400


def test_get_history_rejects_negative_limit():
    with pytest.raises(ServiceError) as exc_info:
        get_history(limit=-5)
    assert exc_info.value.status_code == 400


def test_get_history_timestamp_falls_back_to_string_for_unparseable_value(httpx_mock):
    """_timestamp() passes an already-unparseable value through as a string
    rather than dropping the only timing information the row has."""
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/history?perpage=20",
        json={
            "history": [
                {"id": 1, "title": "Show", "type": "episode", "watched": 0,
                 "via": "webhook", "updated_at": "not-a-number"},
            ],
            "paging": {"total": 1},
        },
    )
    result = get_history()
    assert result["history"][0]["updated_at"] == "not-a-number"
    assert result["history"][0]["watched"] is False


def test_get_history_timestamp_none_when_missing(httpx_mock):
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/history?perpage=20",
        json={"history": [{"id": 1, "title": "Show", "watched": 1}], "paging": {"total": 1}},
    )
    result = get_history()
    assert result["history"][0]["updated_at"] is None


def test_get_history_upstream_error_raises_service_error(httpx_mock):
    httpx_mock.add_response(
        url="http://watchstate:8080/v1/api/history?perpage=20",
        status_code=500,
        json={"error": {"code": 500, "message": "db locked"}},
    )
    with pytest.raises(ServiceError):
        get_history()

import httpx
import pytest

from core import nzbdav_client
from core.api_base import ServiceError
from nzbdav import services


@pytest.fixture(autouse=True)
def _nzbdav_api_key(monkeypatch):
    monkeypatch.setattr(nzbdav_client, "NZBDAV_API_KEY", "test-nzbdav-key")


def test_get_queue_maps_slots(httpx_mock):
    httpx_mock.add_response(
        url="http://nzbdav:3000/api?mode=queue&output=json&apikey=test-nzbdav-key",
        json={"queue": {"slots": [
            {"filename": "Movie.One", "cat": "movies", "status": "Downloading",
             "percentage": "42", "mb": "1000", "mbleft": "580"},
        ]}},
    )
    items = services.get_queue()
    assert items == [{
        "name": "Movie.One", "category": "movies", "status": "Downloading",
        "percentage": "42", "size_mb": "1000", "size_left_mb": "580",
    }]


def test_get_history_maps_slots_and_formats_size(httpx_mock):
    httpx_mock.add_response(
        url="http://nzbdav:3000/api?mode=history&output=json&apikey=test-nzbdav-key&limit=20",
        json={"history": {"slots": [
            {"name": "Movie.Two", "category": "movies", "status": "Completed",
             "bytes": 1024 * 1024 * 5, "fail_message": "", "storage": "/data/Movie.Two"},
        ]}},
    )
    items = services.get_history(limit=20)
    assert items == [{
        "name": "Movie.Two", "category": "movies", "status": "Completed",
        "size": "5.0 MB", "fail_message": None, "path": "/data/Movie.Two",
    }]


def test_check_dedup_config_healthy(httpx_mock):
    httpx_mock.add_response(
        url="http://nzbdav:3000/api/get-config",
        method="POST",
        json={"configItems": [{"configValue": "mark-failed"}]},
    )
    result = services.check_dedup_config()
    assert result["healthy"] is True
    assert result["value"] == "mark-failed"
    assert "OK" in result["message"]


def test_check_dedup_config_unhealthy(httpx_mock):
    httpx_mock.add_response(
        url="http://nzbdav:3000/api/get-config",
        method="POST",
        json={"configItems": [{"configValue": "increment"}]},
    )
    result = services.check_dedup_config()
    assert result["healthy"] is False
    assert result["value"] == "increment"
    assert "importBlocked" in result["message"]


def test_check_dedup_config_missing_key_raises_503(monkeypatch):
    monkeypatch.setattr(nzbdav_client, "NZBDAV_API_KEY", None)
    with pytest.raises(ServiceError) as exc_info:
        services.check_dedup_config()
    assert exc_info.value.status_code == 503


def test_check_dedup_config_upstream_error_raises_service_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    with pytest.raises(ServiceError):
        services.check_dedup_config()


def test_get_stats_aggregates_queue_and_history(httpx_mock):
    httpx_mock.add_response(
        url="http://nzbdav:3000/api?mode=queue&output=json&apikey=test-nzbdav-key",
        json={"queue": {"slots": [{"mbleft": "100"}, {"mbleft": "50"}]}},
    )
    httpx_mock.add_response(
        url="http://nzbdav:3000/api?mode=history&output=json&apikey=test-nzbdav-key&limit=100",
        json={"history": {"slots": [
            {"status": "Completed"}, {"status": "Failed"}, {"status": "failed"},
        ]}},
    )
    result = services.get_stats()
    assert result["queued"] == 2
    assert result["mb_left"] == 150
    assert result["history_count"] == 3
    assert result["history_failed"] == 2
    assert "2 queued" in result["message"]


def test_delete_failures_no_failed_entries(httpx_mock):
    httpx_mock.add_response(
        url="http://nzbdav:3000/api?mode=history&output=json&apikey=test-nzbdav-key&limit=0",
        json={"history": {"slots": [{"status": "Completed", "nzo_id": "1"}]}},
    )
    result = services.delete_failures()
    assert result == {"message": "No failed history entries to delete.", "deleted": 0, "errors": []}


def test_delete_failures_fans_out_and_collects_errors(httpx_mock):
    """Mix of success, a SABnzbd-reported failure, and a transport error
    across the ThreadPoolExecutor fan-out - every delete must still fire,
    and only the failing ones land in `errors` rather than aborting the
    batch."""
    httpx_mock.add_response(
        url="http://nzbdav:3000/api?mode=history&output=json&apikey=test-nzbdav-key&limit=0",
        json={"history": {"slots": [
            {"status": "Failed", "nzo_id": "id-1", "name": "Job One"},
            {"status": "Failed", "nzo_id": "id-2", "name": "Job Two"},
            {"status": "Failed", "nzo_id": "id-3", "name": "Job Three"},
            {"status": "Completed", "nzo_id": "id-4", "name": "Job Four"},
        ]}},
    )
    httpx_mock.add_response(
        url="http://nzbdav:3000/api?mode=history&name=delete&value=id-1"
        "&apikey=test-nzbdav-key&output=json",
        json={"status": True},
    )
    httpx_mock.add_response(
        url="http://nzbdav:3000/api?mode=history&name=delete&value=id-2"
        "&apikey=test-nzbdav-key&output=json",
        json={"status": False, "error": "not found"},
    )
    httpx_mock.add_exception(
        httpx.ConnectError("connection refused"),
        url="http://nzbdav:3000/api?mode=history&name=delete&value=id-3"
        "&apikey=test-nzbdav-key&output=json",
    )
    result = services.delete_failures()
    assert result["deleted"] == 1
    assert len(result["errors"]) == 2
    assert any("Job Two" in e for e in result["errors"])
    assert any("Job Three" in e for e in result["errors"])
    assert "Deleted 1/3 failed history entries." in result["message"]
    assert "2 error(s)" in result["message"]

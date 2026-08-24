"""Tests for core/import_starvation.py - the Radarr/Sonarr import-starvation
detector ported from the FastAPI-era module (mechanism, signals, and
constants are byte-identical to the source). Outbound arr-app API calls are
mocked with pytest-httpx.

Note on URL matching: `refresh_starvation`/`grab_import_lag` hit
`/command` (no query string) and `/history` (with query params that differ
per eventType), so /history responses are matched with a regex on the
eventType param."""

import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from core.api_base import ServiceError
from core.import_starvation import (
    REFRESH_COMMAND,
    check_all,
    clear_search_backlog,
    detect,
    grab_import_lag,
    refresh_starvation,
)

NOW = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

RADARR = "http://radarr:7878/api/v3"
SONARR = "http://sonarr:8989/api/v3"

RADARR_COMMAND = f"{RADARR}/command"
SONARR_COMMAND = f"{SONARR}/command"
RADARR_HISTORY_GRABBED = re.compile(rf"{re.escape(RADARR)}/history\?.*eventType=1")
RADARR_HISTORY_IMPORTED = re.compile(rf"{re.escape(RADARR)}/history\?.*eventType=3")
SONARR_HISTORY_GRABBED = re.compile(rf"{re.escape(SONARR)}/history\?.*eventType=1")
SONARR_HISTORY_IMPORTED = re.compile(rf"{re.escape(SONARR)}/history\?.*eventType=3")


def _queued_at(seconds_ago: int) -> str:
    return (NOW - timedelta(seconds=seconds_ago)).isoformat()


def _iso(seconds_ago: int) -> str:
    return (NOW - timedelta(seconds=seconds_ago)).isoformat()


STARVED_RADARR_COMMANDS = [
    {"id": 1, "name": REFRESH_COMMAND, "status": "queued", "queued": _queued_at(600)},
    {"id": 2, "name": "MoviesSearch", "status": "queued", "queued": _queued_at(500)},
]
HEALTHY_SONARR_COMMANDS = [
    {"id": 3, "name": REFRESH_COMMAND, "status": "queued", "queued": _queued_at(30)},
]


def test_refresh_starvation_measures_oldest_queued_refresh(httpx_mock):
    httpx_mock.add_response(
        url=RADARR_COMMAND,
        json=[
            {"id": 1, "name": REFRESH_COMMAND, "status": "queued", "queued": _queued_at(600)},
            {"id": 2, "name": "MoviesSearch", "status": "queued", "queued": _queued_at(500)},
            {"id": 3, "name": REFRESH_COMMAND, "status": "started", "queued": _queued_at(100)},
            {"id": 4, "name": "MoviesSearch", "status": "completed", "queued": _queued_at(700)},
        ],
    )
    result = refresh_starvation("radarr", now=NOW)
    assert result["starved_seconds"] == 600
    assert result["refresh_queued"] == 1
    assert result["queued_searches"] == 1
    assert result["active_commands"] == 3


def test_refresh_starvation_no_waiting_refresh_is_zero(httpx_mock):
    httpx_mock.add_response(
        url=RADARR_COMMAND,
        json=[{"id": 5, "name": REFRESH_COMMAND, "status": "completed", "queued": _queued_at(600)}],
    )
    result = refresh_starvation("radarr", now=NOW)
    assert result["starved_seconds"] == 0
    assert result["refresh_queued"] == 0


def test_refresh_starvation_ignores_unparseable_queued_timestamps(httpx_mock):
    httpx_mock.add_response(
        url=RADARR_COMMAND,
        json=[
            {"id": 6, "name": REFRESH_COMMAND, "status": "queued", "queued": None},
            {"id": 7, "name": REFRESH_COMMAND, "status": "queued", "queued": "not-a-date"},
        ],
    )
    result = refresh_starvation("radarr", now=NOW)
    assert result["starved_seconds"] == 0
    assert result["refresh_queued"] == 2


def test_grab_import_lag_computes_lag_and_import_age(httpx_mock):
    httpx_mock.add_response(url=RADARR_HISTORY_GRABBED, json={"records": [{"date": _iso(3600), "eventType": 1}]})
    httpx_mock.add_response(url=RADARR_HISTORY_IMPORTED, json={"records": [{"date": _iso(7200), "eventType": 3}]})
    result = grab_import_lag("radarr", now=NOW)
    assert result["lag_seconds"] == 3600
    assert result["import_age_seconds"] == 7200
    assert result["last_grab"] is not None
    assert result["last_import"] is not None


def test_grab_import_lag_empty_history_is_null(httpx_mock):
    httpx_mock.add_response(url=RADARR_HISTORY_GRABBED, json={"records": []})
    httpx_mock.add_response(url=RADARR_HISTORY_IMPORTED, json={"records": []})
    result = grab_import_lag("radarr", now=NOW)
    assert result["lag_seconds"] is None
    assert result["import_age_seconds"] is None
    assert result["last_grab"] is None
    assert result["last_import"] is None


def test_detect_starved_when_refresh_queued_past_threshold(httpx_mock):
    httpx_mock.add_response(url=RADARR_COMMAND, json=STARVED_RADARR_COMMANDS)
    httpx_mock.add_response(url=RADARR_HISTORY_GRABBED, json={"records": [{"date": _iso(60), "eventType": 1}]})
    httpx_mock.add_response(url=RADARR_HISTORY_IMPORTED, json={"records": [{"date": _iso(30), "eventType": 3}]})
    result = detect("radarr", now=NOW)
    assert result["starved"] is True
    assert "queued 600s" in result["reason"]
    assert result["lagging"] is False


def test_detect_lagging_when_grabs_outpace_imports(httpx_mock):
    httpx_mock.add_response(
        url=RADARR_COMMAND,
        json=[{"id": 1, "name": REFRESH_COMMAND, "status": "queued", "queued": _queued_at(30)}],
    )
    httpx_mock.add_response(url=RADARR_HISTORY_GRABBED, json={"records": [{"date": _iso(3600), "eventType": 1}]})
    httpx_mock.add_response(url=RADARR_HISTORY_IMPORTED, json={"records": [{"date": _iso(7200), "eventType": 3}]})
    result = detect("radarr", now=NOW)
    assert result["starved"] is False
    assert result["lagging"] is True
    assert "Last grab is 3600s newer" in result["reason"]


def test_detect_healthy_when_imports_keep_up(httpx_mock):
    httpx_mock.add_response(
        url=RADARR_COMMAND,
        json=[{"id": 1, "name": REFRESH_COMMAND, "status": "queued", "queued": _queued_at(30)}],
    )
    httpx_mock.add_response(url=RADARR_HISTORY_GRABBED, json={"records": [{"date": _iso(100), "eventType": 1}]})
    httpx_mock.add_response(url=RADARR_HISTORY_IMPORTED, json={"records": [{"date": _iso(60), "eventType": 3}]})
    result = detect("radarr", now=NOW)
    assert result["starved"] is False
    assert result["lagging"] is False
    assert result["reason"] == "Imports are keeping up with grabs."


def test_clear_search_backlog_cancels_only_queued_searches(httpx_mock):
    httpx_mock.add_response(
        url=RADARR_COMMAND,
        json=[
            {"id": 10, "name": "MoviesSearch", "status": "queued"},
            {"id": 11, "name": "MoviesSearch", "status": "started"},
            {"id": 12, "name": REFRESH_COMMAND, "status": "queued"},
        ],
    )
    httpx_mock.add_response(url=f"{RADARR}/command/10", method="DELETE", json={})
    result = clear_search_backlog("radarr")
    assert result == {"targeted": 1, "cancelled": 1, "failed": 0}


def test_clear_search_backlog_counts_failed_cancellations(httpx_mock):
    httpx_mock.add_response(
        url=RADARR_COMMAND,
        json=[{"id": 10, "name": "MoviesSearch", "status": "queued"}],
    )
    httpx_mock.add_exception(httpx.ConnectError("boom"), url=f"{RADARR}/command/10", method="DELETE")
    result = clear_search_backlog("radarr")
    assert result == {"targeted": 1, "cancelled": 0, "failed": 1}


def test_require_queue_app_rejects_non_queue_app():
    with pytest.raises(ServiceError):
        refresh_starvation("prowlarr", now=NOW)


def test_check_all_remediates_starved_and_lists_lagging(httpx_mock):
    # radarr: /command is fetched twice (detect, then clear_search_backlog's
    # own re-fetch) - register a FIFO queue of two identical responses.
    httpx_mock.add_response(url=RADARR_COMMAND, json=STARVED_RADARR_COMMANDS)
    httpx_mock.add_response(url=RADARR_COMMAND, json=STARVED_RADARR_COMMANDS)
    httpx_mock.add_response(url=RADARR_HISTORY_GRABBED, json={"records": [{"date": _iso(60), "eventType": 1}]})
    httpx_mock.add_response(url=RADARR_HISTORY_IMPORTED, json={"records": [{"date": _iso(30), "eventType": 3}]})
    httpx_mock.add_response(url=f"{RADARR}/command/2", method="DELETE", json={})
    # sonarr: healthy
    httpx_mock.add_response(url=SONARR_COMMAND, json=HEALTHY_SONARR_COMMANDS)
    httpx_mock.add_response(url=SONARR_HISTORY_GRABBED, json={"records": [{"date": _iso(100), "eventType": 1}]})
    httpx_mock.add_response(url=SONARR_HISTORY_IMPORTED, json={"records": [{"date": _iso(60), "eventType": 3}]})

    result = check_all(now=NOW)
    assert result["starved"] == ["radarr"]
    assert result["lagging"] == []
    assert result["remediated"]["radarr"] == {"targeted": 1, "cancelled": 1, "failed": 0}
    assert result["apps"]["sonarr"]["starved"] is False


def test_check_all_without_remediation_skips_cancels(httpx_mock):
    httpx_mock.add_response(url=RADARR_COMMAND, json=STARVED_RADARR_COMMANDS)
    httpx_mock.add_response(url=RADARR_HISTORY_GRABBED, json={"records": [{"date": _iso(60), "eventType": 1}]})
    httpx_mock.add_response(url=RADARR_HISTORY_IMPORTED, json={"records": [{"date": _iso(30), "eventType": 3}]})
    httpx_mock.add_response(url=SONARR_COMMAND, json=HEALTHY_SONARR_COMMANDS)
    httpx_mock.add_response(url=SONARR_HISTORY_GRABBED, json={"records": [{"date": _iso(100), "eventType": 1}]})
    httpx_mock.add_response(url=SONARR_HISTORY_IMPORTED, json={"records": [{"date": _iso(60), "eventType": 3}]})

    result = check_all(remediate=False, now=NOW)
    assert result["starved"] == ["radarr"]
    assert result["remediated"] == {}

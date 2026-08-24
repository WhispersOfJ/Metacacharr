"""Gate tests for core/import_starvation.py - the detector for the
2026-08-08 incident where a mass backfill starved RefreshMonitoredDownloads
and silently stopped every import for hours while the queue read empty.

The critical case is test_starved_app_reports_empty_queue: the whole reason
this module exists is that a starved app looks perfectly healthy to every
queue-shaped check, because the starved command is the one that populates
the queue in the first place.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest

NOW = datetime(2026, 8, 8, 17, 15, 0, tzinfo=timezone.utc)


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _command(name, status, queued_ago_seconds=0):
    return {
        "id": abs(hash((name, status, queued_ago_seconds))) % 100000,
        "name": name,
        "status": status,
        "queued": _iso(NOW - timedelta(seconds=queued_ago_seconds)),
    }


def _history(date):
    return {"records": [{"date": _iso(date)}] if date else []}


@pytest.fixture
def starvation(cp_main_app, monkeypatch):
    """core.import_starvation with every outbound httpx call stubbed. Import
    happens inside the cp_main_app fixture so ARR_APPS' os.environ[...] reads
    see the fixture's stand-in keys."""
    import core.import_starvation as module

    state = {"commands": [], "grab": None, "import": None, "deleted": [], "delete_fails": set()}

    def fake_get(url, params=None, headers=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if url.endswith("/command"):
            resp.json.return_value = state["commands"]
        elif url.endswith("/history"):
            key = "grab" if (params or {}).get("eventType") == module.EVENT_GRABBED else "import"
            resp.json.return_value = _history(state[key])
        else:
            raise AssertionError(f"unexpected GET {url}")
        return resp

    def fake_delete(url, headers=None, timeout=None):
        command_id = int(url.rsplit("/", 1)[-1])
        resp = MagicMock()
        if command_id in state["delete_fails"]:
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "409", request=MagicMock(), response=resp)
        else:
            resp.raise_for_status = MagicMock()
            state["deleted"].append(command_id)
        return resp

    monkeypatch.setattr(module.httpx, "get", fake_get)
    monkeypatch.setattr(module.httpx, "delete", fake_delete)
    module.state = state
    return module


def test_healthy_app_is_not_starved(starvation):
    starvation.state["commands"] = [
        _command("RefreshMonitoredDownloads", "started", 5),
        _command("RssSync", "started", 2),
    ]
    starvation.state["grab"] = NOW - timedelta(seconds=30)
    starvation.state["import"] = NOW - timedelta(seconds=20)

    verdict = starvation.detect("radarr", now=NOW)

    assert verdict["starved"] is False
    assert verdict["lagging"] is False
    assert verdict["reason"] == "Imports are keeping up with grabs."


def test_queued_refresh_past_threshold_is_starved(starvation):
    """Signal 1, the conclusive one: radarr's real incident numbers - a
    RefreshMonitoredDownloads queued 85 minutes behind 1104 searches."""
    starvation.state["commands"] = [
        _command("RefreshMonitoredDownloads", "queued", 5100),
        *[_command("MoviesSearch", "queued", 5000 - i) for i in range(20)],
        _command("MoviesSearch", "started", 10),
    ]
    starvation.state["grab"] = NOW
    starvation.state["import"] = NOW - timedelta(seconds=5000)

    verdict = starvation.detect("radarr", now=NOW)

    assert verdict["starved"] is True
    assert verdict["starved_seconds"] == 5100
    assert verdict["queued_searches"] == 20
    assert "1104" not in verdict["reason"]  # reports observed count, not a constant
    assert "20 queued search command(s)" in verdict["reason"]


def test_starved_app_reports_empty_queue(starvation):
    """The trap this module exists for. RefreshMonitoredDownloads is what
    populates the queue, so a starved app shows zero queue items and every
    queue-shaped health check reads clean. Starvation must be detected from
    the command pool and history, never from queue contents."""
    starvation.state["commands"] = [_command("RefreshMonitoredDownloads", "queued", 8760),
                                    _command("MissingEpisodeSearch", "queued", 8000)]
    starvation.state["grab"] = NOW
    starvation.state["import"] = NOW - timedelta(seconds=8760)

    verdict = starvation.detect("sonarr", now=NOW)

    # No queue lookup happens at all - an empty queue must never be able to
    # mask this, so the detector does not consult it.
    assert verdict["starved"] is True
    assert verdict["lag_seconds"] == 8760


def test_lagging_without_starvation_is_flagged_separately(starvation):
    """Imports behind grabs while RefreshMonitoredDownloads runs normally is
    a different fault (blocked imports, bad mount) - reported, not remediated
    by cancelling searches."""
    starvation.state["commands"] = [_command("RefreshMonitoredDownloads", "started", 1)]
    starvation.state["grab"] = NOW
    starvation.state["import"] = NOW - timedelta(seconds=3600)

    verdict = starvation.detect("sonarr", now=NOW)

    assert verdict["starved"] is False
    assert verdict["lagging"] is True
    assert "may be blocked for another reason" in verdict["reason"]


def test_threshold_boundary_is_exclusive(starvation):
    """Exactly at the threshold is not starved - RefreshMonitoredDownloads
    runs every 60s, so brief contention must not trip remediation."""
    starvation.state["commands"] = [
        _command("RefreshMonitoredDownloads", "queued", starvation.STARVATION_THRESHOLD_SECONDS)]
    starvation.state["grab"] = NOW
    starvation.state["import"] = NOW

    assert starvation.detect("radarr", now=NOW)["starved"] is False


def test_missing_import_history_does_not_crash(starvation):
    """A fresh instance with grabs but zero imports yet - lag is unknowable,
    not infinite, and must not be reported as lagging."""
    starvation.state["commands"] = [_command("RefreshMonitoredDownloads", "started", 1)]
    starvation.state["grab"] = NOW
    starvation.state["import"] = None

    verdict = starvation.detect("radarr", now=NOW)

    assert verdict["lag_seconds"] is None
    assert verdict["lagging"] is False
    assert verdict["starved"] is False


def test_clear_search_backlog_cancels_only_queued_searches(starvation):
    """Started commands cannot be cancelled (409) and targeted work must
    survive - only QUEUED bulk searches are valid targets."""
    queued_search = _command("MissingEpisodeSearch", "queued", 100)
    started_search = _command("SeriesSearch", "started", 200)
    refresh = _command("RefreshMonitoredDownloads", "queued", 900)
    rss = _command("RssSync", "queued", 50)
    starvation.state["commands"] = [queued_search, started_search, refresh, rss]

    result = starvation.clear_search_backlog("sonarr")

    assert result == {"targeted": 1, "cancelled": 1, "failed": 0}
    assert starvation.state["deleted"] == [queued_search["id"]]


def test_clear_search_backlog_counts_rejected_cancels(starvation):
    """A command that starts between listing and deleting returns 409 - it
    is counted, not raised, so one racy item cannot abort the whole sweep."""
    first = _command("MoviesSearch", "queued", 100)
    second = _command("MoviesSearch", "queued", 101)
    starvation.state["commands"] = [first, second]
    starvation.state["delete_fails"] = {first["id"]}

    result = starvation.clear_search_backlog("radarr")

    assert result == {"targeted": 2, "cancelled": 1, "failed": 1}


def test_check_all_remediates_only_starved_apps(starvation):
    starvation.state["commands"] = [
        _command("RefreshMonitoredDownloads", "queued", 9000),
        _command("MoviesSearch", "queued", 8000),
    ]
    starvation.state["grab"] = NOW
    starvation.state["import"] = NOW - timedelta(seconds=9000)

    result = starvation.check_all(remediate=True, now=NOW)

    # Every app shares the same stubbed backend here, so both starve.
    assert set(result["starved"]) == {"radarr", "sonarr"}
    assert all(r["cancelled"] == 1 for r in result["remediated"].values())


def test_check_all_respects_remediate_false(starvation):
    starvation.state["commands"] = [
        _command("RefreshMonitoredDownloads", "queued", 9000),
        _command("MoviesSearch", "queued", 8000),
    ]
    starvation.state["grab"] = NOW
    starvation.state["import"] = NOW - timedelta(seconds=9000)

    result = starvation.check_all(remediate=False, now=NOW)

    assert result["starved"]
    assert result["remediated"] == {}
    assert starvation.state["deleted"] == []

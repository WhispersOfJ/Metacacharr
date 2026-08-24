"""Gate tests for core/arr_client.py's pure-logic helpers and error paths.
No test file has covered this module since test_arr_client_apps.py (anime-
instance-only) and app.py's test_helpers.py were both deleted in the Plan 3
consolidation (c7fc6b8) - the underlying human_size/format_eta/dedup logic
moved here but the tests weren't ported.
"""
from unittest.mock import MagicMock

import httpx
import pytest


@pytest.fixture
def arr_client(cp_main_app):
    import core.arr_client as module
    return module


def test_human_size_falsy_is_unknown(arr_client):
    assert arr_client.human_size(None) == "?"
    assert arr_client.human_size(0) == "?"


@pytest.mark.parametrize(
    "n,expected",
    [
        (500, "500.0 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024 ** 3, "1.0 GB"),
        (1024 ** 4, "1.0 TB"),
        (1024 ** 5, "1.0 PB"),
    ],
)
def test_human_size_units(arr_client, n, expected):
    assert arr_client.human_size(n) == expected


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (float("inf"), "unknown"),
        (-1, "unknown"),
        (30, "30s"),
        (90, "1m30s"),
        (3661, "1h01m"),
        (90000, "1d01h"),
    ],
)
def test_format_eta(arr_client, seconds, expected):
    assert arr_client.format_eta(seconds) == expected


def test_dedup_suffix_hit_true_cases(arr_client):
    assert arr_client.dedup_suffix_hit("Movie Name (2).mkv") is True
    assert arr_client.dedup_suffix_hit("path/to/Movie (1)") is True


def test_dedup_suffix_hit_false_cases(arr_client):
    # NOTE: DEDUP_SUFFIX_RE (arr_client.py:282) matches "(2020)" as a false
    # positive too - it can't distinguish a dedup suffix from a year in
    # parens. Flagged in AUDIT_FINDINGS.md rather than changed here (behavior
    # change, not a small/obvious fix).
    assert arr_client.dedup_suffix_hit(None) is False
    assert arr_client.dedup_suffix_hit("") is False
    assert arr_client.dedup_suffix_hit("Movie Name.mkv") is False


def test_arr_command_unknown_app_fails_404(arr_client):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        arr_client.arr_command("bogus", "SomeCommand")
    assert exc.value.status_code == 404


def test_require_queue_app_rejects_non_queue_app(arr_client, monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setitem(arr_client.ARR_APPS, "prowlarr", {"url": "http://prowlarr:9696"})
    with pytest.raises(HTTPException) as exc:
        arr_client.require_queue_app("prowlarr")
    assert exc.value.status_code == 404


def test_require_queue_app_returns_cfg_for_queue_app(arr_client):
    cfg = arr_client.require_queue_app("radarr")
    assert cfg["label"] == "Radarr"


def test_arr_queue_http_error_fails_502(arr_client, monkeypatch):
    from fastapi import HTTPException

    def raise_error(*a, **k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(arr_client.httpx, "get", raise_error)
    with pytest.raises(HTTPException) as exc:
        arr_client.arr_queue("radarr")
    assert exc.value.status_code == 502


def test_stuck_queue_items_filters_warning_and_error(arr_client, monkeypatch):
    records = [
        {"id": 1, "trackedDownloadStatus": "warning"},
        {"id": 2, "trackedDownloadStatus": "ok"},
        {"id": 3, "trackedDownloadStatus": "error"},
    ]
    monkeypatch.setattr(arr_client, "arr_queue", lambda app: records)
    result = arr_client.stuck_queue_items("radarr")
    assert {r["id"] for r in result} == {1, 3}


def test_import_candidate_queue_items_includes_import_pending(arr_client, monkeypatch):
    records = [
        {"id": 1, "trackedDownloadStatus": "ok", "trackedDownloadState": "importPending"},
        {"id": 2, "trackedDownloadStatus": "ok", "trackedDownloadState": "downloading"},
        {"id": 3, "trackedDownloadStatus": "warning", "trackedDownloadState": "downloading"},
    ]
    monkeypatch.setattr(arr_client, "arr_queue", lambda app: records)
    result = arr_client.import_candidate_queue_items("radarr")
    assert {r["id"] for r in result} == {1, 3}


def test_get_movie_or_episode_returns_none_on_http_error(arr_client, monkeypatch):
    def raise_error(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(arr_client.httpx, "get", raise_error)
    cfg = arr_client.ARR_APPS["radarr"]
    assert arr_client.get_movie_or_episode("radarr", cfg, 42) is None


def test_item_is_monitored_uses_embedded_object_first(arr_client):
    cfg = arr_client.ARR_APPS["radarr"]
    q = {"movie": {"monitored": False}, "movieId": 1}
    assert arr_client.item_is_monitored("radarr", q, cfg, "movieId") is False


def test_item_is_monitored_defaults_true_when_id_missing(arr_client):
    cfg = arr_client.ARR_APPS["radarr"]
    q = {"movie": None}
    assert arr_client.item_is_monitored("radarr", q, cfg, "movieId") is True


def test_item_is_monitored_falls_back_to_lookup_on_http_error(arr_client, monkeypatch):
    cfg = arr_client.ARR_APPS["radarr"]
    q = {"movie": None, "movieId": 5}

    def raise_error(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(arr_client.httpx, "get", raise_error)
    # Defaults to True (assume monitored) rather than silently dropping a
    # search that should have happened - see the function's own docstring.
    assert arr_client.item_is_monitored("radarr", q, cfg, "movieId") is True


def test_disable_autoredownload_below_threshold_is_noop(arr_client):
    assert arr_client.disable_autoredownload_if_storm("radarr", failed_pending_count=2, threshold=15) is False


def test_disable_autoredownload_already_off_is_noop(arr_client, monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"autoRedownloadFailed": False, "id": 1}
        return resp

    monkeypatch.setattr(arr_client.httpx, "get", fake_get)
    result = arr_client.disable_autoredownload_if_storm("radarr", failed_pending_count=20, threshold=15)
    assert result is False


def test_disable_autoredownload_turns_off_when_storming(arr_client, monkeypatch):
    put_calls = []

    def fake_get(url, headers=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"autoRedownloadFailed": True, "id": 7}
        return resp

    def fake_put(url, json=None, headers=None, timeout=None):
        put_calls.append(json)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        return resp

    monkeypatch.setattr(arr_client.httpx, "get", fake_get)
    monkeypatch.setattr(arr_client.httpx, "put", fake_put)
    result = arr_client.disable_autoredownload_if_storm("radarr", failed_pending_count=20, threshold=15)
    assert result is True
    assert put_calls[0]["autoRedownloadFailed"] is False


def test_disable_autoredownload_http_error_returns_false(arr_client, monkeypatch):
    def raise_error(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(arr_client.httpx, "get", raise_error)
    assert arr_client.disable_autoredownload_if_storm("radarr", failed_pending_count=99, threshold=15) is False


def test_dd_test_file_reports_readable_on_zero_exit(arr_client):
    container = MagicMock()
    container.exec_run.return_value = MagicMock(exit_code=0, output=(b"", b""))
    ok, msg = arr_client.dd_test_file(container, "/data/movies/x.mkv")
    assert ok is True
    assert msg == "readable"


def test_dd_test_file_reports_stderr_on_failure(arr_client):
    container = MagicMock()
    container.exec_run.return_value = MagicMock(exit_code=1, output=(b"", b"Input/output error\n"))
    ok, msg = arr_client.dd_test_file(container, "/data/movies/x.mkv")
    assert ok is False
    assert "Input/output error" in msg


def test_dd_test_file_handles_exec_exception(arr_client):
    container = MagicMock()
    container.exec_run.side_effect = RuntimeError("docker exec failed")
    ok, msg = arr_client.dd_test_file(container, "/data/movies/x.mkv")
    assert ok is False
    assert "exec failed" in msg


def test_find_candidate_files_missing_path(arr_client):
    container = MagicMock()
    container.exec_run.return_value = MagicMock(exit_code=1)
    status, files = arr_client.find_candidate_files(container, "/data/movies/gone")
    assert status == "missing"
    assert files == []


def test_find_candidate_files_prefers_symlinks(arr_client):
    container = MagicMock()

    def exec_run(cmd, **kwargs):
        if cmd[:2] == ["test", "-e"]:
            return MagicMock(exit_code=0)
        if "-type" in cmd and cmd[cmd.index("-type") + 1] == "l":
            return MagicMock(output=b"/data/movies/x.mkv\n")
        return MagicMock(output=b"")

    container.exec_run.side_effect = exec_run
    status, files = arr_client.find_candidate_files(container, "/data/movies/x")
    assert status == "ok"
    assert files == ["/data/movies/x.mkv"]


def test_find_candidate_files_empty_when_no_files_found(arr_client):
    container = MagicMock()
    container.exec_run.side_effect = [
        MagicMock(exit_code=0),
        MagicMock(output=b""),
        MagicMock(output=b""),
    ]
    status, files = arr_client.find_candidate_files(container, "/data/movies/x")
    assert status == "empty"
    assert files == []


def test_importing_queue_targets_dedupes_by_download_id(arr_client, monkeypatch):
    records = [
        {"id": 1, "trackedDownloadState": "importing", "downloadId": "abc", "title": "Show S01E01"},
        {"id": 2, "trackedDownloadState": "importing", "downloadId": "abc", "title": "Show S01E02"},
        {"id": 3, "trackedDownloadState": "downloading", "downloadId": "xyz"},
    ]
    monkeypatch.setattr(arr_client, "arr_queue", lambda app: records)
    targets = arr_client.importing_queue_targets("radarr")
    assert len(targets) == 1
    assert targets[0]["queueIds"] == [1, 2]


def test_current_queue_output_path_finds_match(arr_client, monkeypatch):
    records = [{"movieId": 1, "outputPath": "/data/movies/a"}, {"movieId": 2, "outputPath": "/data/movies/b"}]
    monkeypatch.setattr(arr_client, "arr_queue", lambda app: records)
    assert arr_client.current_queue_output_path("radarr", 2, "movieId") == "/data/movies/b"


def test_current_queue_output_path_returns_none_when_absent(arr_client, monkeypatch):
    monkeypatch.setattr(arr_client, "arr_queue", lambda app: [])
    assert arr_client.current_queue_output_path("radarr", 99, "movieId") is None


def test_arr_sizeleft_snapshot_returns_empty_on_http_exception(arr_client, monkeypatch):
    from fastapi import HTTPException

    def raise_fail(app):
        raise HTTPException(status_code=502, detail="boom")

    monkeypatch.setattr(arr_client, "arr_queue", raise_fail)
    assert arr_client.arr_sizeleft_snapshot("radarr") == {}


def test_arr_sizeleft_snapshot_filters_zero_sizeleft(arr_client, monkeypatch):
    records = [{"id": 1, "sizeleft": 500}, {"id": 2, "sizeleft": 0}, {"id": 3, "sizeleft": None}]
    monkeypatch.setattr(arr_client, "arr_queue", lambda app: records)
    assert arr_client.arr_sizeleft_snapshot("radarr") == {1: 500}


def test_wanted_missing_total_reads_total_records(arr_client, monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"totalRecords": 42}
        return resp

    monkeypatch.setattr(arr_client.httpx, "get", fake_get)
    assert arr_client.wanted_missing_total("radarr") == 42


def test_recent_import_rate_below_two_events_is_zero(arr_client, monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"records": [{"eventType": "downloadFolderImported", "date": "2026-08-19T10:00:00Z"}]}
        return resp

    monkeypatch.setattr(arr_client.httpx, "get", fake_get)
    rate, count = arr_client.recent_import_rate_per_hour("radarr")
    assert rate == 0.0
    assert count == 1


def test_recent_import_rate_stale_newest_is_zero(arr_client, monkeypatch):
    from datetime import datetime, timedelta, timezone
    old = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat().replace("+00:00", "Z")
    older = (datetime.now(timezone.utc) - timedelta(hours=11)).isoformat().replace("+00:00", "Z")

    def fake_get(url, params=None, headers=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"records": [
            {"eventType": "downloadFolderImported", "date": old},
            {"eventType": "downloadFolderImported", "date": older},
        ]}
        return resp

    monkeypatch.setattr(arr_client.httpx, "get", fake_get)
    rate, count = arr_client.recent_import_rate_per_hour("radarr")
    assert rate == 0.0
    assert count == 2


def test_radarr_root_folder_and_profile_defaults(arr_client, monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        resp = MagicMock()
        if url.endswith("rootfolder"):
            resp.json.return_value = [{"path": "/data/movies"}]
        else:
            resp.json.return_value = [{"id": 1, "name": "Unlimited"}]
        return resp

    monkeypatch.setattr(arr_client.httpx, "get", fake_get)
    cfg = arr_client.ARR_APPS["radarr"]
    path, profile_id = arr_client.radarr_root_folder_and_profile(cfg, None, None)
    assert path == "/data/movies"
    assert profile_id == 1


def test_radarr_root_folder_and_profile_fails_when_no_folders(arr_client, monkeypatch):
    from fastapi import HTTPException

    def fake_get(url, headers=None, timeout=None):
        resp = MagicMock()
        resp.json.return_value = []
        return resp

    monkeypatch.setattr(arr_client.httpx, "get", fake_get)
    cfg = arr_client.ARR_APPS["radarr"]
    with pytest.raises(HTTPException) as exc:
        arr_client.radarr_root_folder_and_profile(cfg, None, None)
    assert exc.value.status_code == 500


def test_radarr_ensure_tags_creates_missing_tags(arr_client, monkeypatch):
    created = []

    def fake_get(url, headers=None, timeout=None):
        resp = MagicMock()
        resp.json.return_value = [{"id": 1, "label": "existing"}]
        return resp

    def fake_post(url, json=None, headers=None, timeout=None):
        created.append(json["label"])
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"id": 2}
        return resp

    monkeypatch.setattr(arr_client.httpx, "get", fake_get)
    monkeypatch.setattr(arr_client.httpx, "post", fake_post)
    cfg = arr_client.ARR_APPS["radarr"]
    ids = arr_client.radarr_ensure_tags(cfg, ["existing", "new-tag"])
    assert ids == [1, 2]
    assert created == ["new-tag"]


def test_radarr_ensure_tags_empty_input_short_circuits(arr_client):
    cfg = arr_client.ARR_APPS["radarr"]
    assert arr_client.radarr_ensure_tags(cfg, []) == []


def test_radarr_add_movie_already_present_short_circuits(arr_client):
    cfg = arr_client.ARR_APPS["radarr"]
    result = arr_client.radarr_add_movie(
        cfg, tmdb_id=42, monitored=True, search=False, root_folder_path="/data/movies",
        quality_profile_id=1, existing_tmdb_ids={42},
    )
    assert result == {"status": "already", "title": None, "tmdbId": 42}


def test_radarr_add_movie_no_match_fails(arr_client, monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {}
        return resp

    monkeypatch.setattr(arr_client.httpx, "get", fake_get)
    cfg = arr_client.ARR_APPS["radarr"]
    result = arr_client.radarr_add_movie(
        cfg, tmdb_id=99, monitored=True, search=False, root_folder_path="/data/movies",
        quality_profile_id=1, existing_tmdb_ids=set(),
    )
    assert result["status"] == "failed"
    assert "no Radarr match" in result["reason"]


def test_radarr_add_movie_dry_run_does_not_post(arr_client, monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"title": "Test Movie"}
        return resp

    posted = []
    monkeypatch.setattr(arr_client.httpx, "get", fake_get)
    monkeypatch.setattr(arr_client.httpx, "post", lambda *a, **k: posted.append(1))
    cfg = arr_client.ARR_APPS["radarr"]
    result = arr_client.radarr_add_movie(
        cfg, tmdb_id=1, monitored=True, search=False, root_folder_path="/data/movies",
        quality_profile_id=1, existing_tmdb_ids=set(), dry_run=True,
    )
    assert result == {"status": "added", "title": "Test Movie"}
    assert posted == []


def test_sonarr_add_series_no_match_fails(arr_client, monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = []
        return resp

    monkeypatch.setattr(arr_client.httpx, "get", fake_get)
    cfg = arr_client.ARR_APPS["sonarr"]
    result = arr_client.sonarr_add_series(
        cfg, tvdb_id=99, monitored=True, search=False, root_folder_path="/data/shows",
        quality_profile_id=1, existing_tvdb_ids=set(),
    )
    assert result["status"] == "failed"
    assert "no Sonarr match" in result["reason"]


def test_sonarr_add_series_already_present_short_circuits(arr_client):
    cfg = arr_client.ARR_APPS["sonarr"]
    result = arr_client.sonarr_add_series(
        cfg, tvdb_id=7, monitored=True, search=False, root_folder_path="/data/shows",
        quality_profile_id=1, existing_tvdb_ids={7},
    )
    assert result == {"status": "already", "title": None, "tvdbId": 7}

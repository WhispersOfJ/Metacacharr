"""arr/services.py unit tests.

Grouped by dependency, per plan Task 17 Step 2: the majority mock the
Radarr/Sonarr/Prowlarr httpx calls via core.arr_client; unstick_importing
mocks core.docker_client.docker_client.containers.get().exec_run;
import_starvation/queue_autofix mock core.import_starvation.check_all;
manual_import* mock the manualimport endpoints; unmonitor asserts a bulk
PUT with the right id list; loop_candidates asserts the time-window-based
repeat-grab detection against a fixture history payload; and
backlog_status/command_queue_summary/queue_errors assert the multi-app
aggregation loop tolerates one app being unreachable (same partial-failure
pattern as Task 8's queue aggregation).
"""
import json
from datetime import datetime, timedelta, timezone

import docker
import httpx
import pytest

from core import nzbdav_client
from core.api_base import ServiceError
from arr import services


@pytest.fixture(autouse=True)
def _nzbdav_api_key(monkeypatch):
    """queue_autofix calls nzbdav_api(), which reads NZBDAV_API_KEY from the
    nzbdav_client module at call time - same fixture pattern as the
    nzbdav app's own tests."""
    monkeypatch.setattr(nzbdav_client, "NZBDAV_API_KEY", "test-nzbdav-key")


# ---------------------------------------------------------------------------
# rss_sync / search_missing / search_status / search_toggle
# ---------------------------------------------------------------------------


def test_rss_sync_starts_command(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/command", method="POST",
        json={"id": 1, "name": "RssSync", "status": "started"},
    )
    assert services.rss_sync("radarr") == "Radarr RSS sync started."


def test_rss_sync_unknown_app_raises_404():
    with pytest.raises(ServiceError) as exc_info:
        services.rss_sync("not-an-app")
    assert exc_info.value.status_code == 404


def test_search_missing_starts_command(httpx_mock):
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/command", method="POST",
        json={"id": 1, "name": "MissingEpisodeSearch", "status": "started"},
    )
    assert services.search_missing("sonarr") == "Sonarr search for missing items started."


def test_search_status_all_enabled(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/indexer",
        json=[{"enableRss": True, "enableAutomaticSearch": True}, {"enableRss": True, "enableAutomaticSearch": True}],
    )
    assert services.search_status("radarr") == {"enabled": True}


def test_search_status_any_disabled(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/indexer",
        json=[{"enableRss": True, "enableAutomaticSearch": False}],
    )
    assert services.search_status("radarr") == {"enabled": False}


def test_search_status_unreachable_raises(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("refused"), url="http://radarr:7878/api/v3/indexer")
    with pytest.raises(ServiceError):
        services.search_status("radarr")


def test_search_toggle_enables_all_indexers(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/indexer",
        json=[{"id": 1, "enableRss": False, "enableAutomaticSearch": False}],
    )
    httpx_mock.add_response(url="http://radarr:7878/api/v3/indexer/1", method="PUT", json={})
    message = services.search_toggle("radarr", True)
    assert "enabled on 1 indexer(s)" in message


# ---------------------------------------------------------------------------
# command_backlog / unstick / unstick_importing
# ---------------------------------------------------------------------------


def test_command_backlog_counts_and_lists(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/command",
        json=[
            {"id": 1, "name": "RefreshMovie", "status": "completed"},
            {"id": 2, "name": "MissingMoviesSearch", "status": "queued", "queued": "2026-08-01T01:00:00Z"},
            {"id": 3, "name": "RssSync", "status": "started", "started": "2026-08-01T02:00:00Z"},
        ],
    )
    result = services.command_backlog("radarr")
    assert result["total"] == 3
    assert result["counts"] == {"completed": 1, "queued": 1, "started": 1}
    assert result["queued_total"] == 1
    assert result["oldest_queued"] == [{"id": 2, "name": "MissingMoviesSearch", "queued": "2026-08-01T01:00:00Z"}]
    assert result["running"][0]["name"] == "RssSync"


def test_unstick_no_stuck_items(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeMovie=true",
        json={"records": []},
    )
    result = services.unstick("radarr")
    assert result["message"] == "No stuck downloads in Radarr."
    assert result["removed"] == []


def test_unstick_removes_warning_items(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeMovie=true",
        json={"records": [{"id": 7, "title": "Movie.One", "trackedDownloadStatus": "warning"}]},
    )
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/queue/7?removeFromClient=true&blocklist=true&skipRedownload=false",
        method="DELETE", json={},
    )
    result = services.unstick("radarr")
    assert result["removed"] == ["Movie.One"]
    assert "Removed, blocklisted, and re-searching 1 stuck download(s)" in result["message"]


def test_unstick_all_failed_raises(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeMovie=true",
        json={"records": [{"id": 7, "title": "Movie.One", "trackedDownloadStatus": "error"}]},
    )
    httpx_mock.add_exception(httpx.ConnectError("refused"),
                             url="http://radarr:7878/api/v3/queue/7?removeFromClient=true&blocklist=true&skipRedownload=false")
    with pytest.raises(ServiceError):
        services.unstick("radarr")


def test_unstick_importing_no_targets(httpx_mock):
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeEpisode=true",
        json={"records": []},
    )
    result = services.unstick_importing("sonarr")
    assert result["message"] == "No downloads currently importing in Sonarr."
    assert result["results"] == []


def test_unstick_importing_wedged_cleared(httpx_mock, monkeypatch):
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeEpisode=true",
        json={"records": [{"id": 11, "downloadId": "nzo-1", "title": "Show.S01E01", "outputPath": "/data/Show",
                           "trackedDownloadState": "importing", "seriesId": 5}]},
    )

    class _FakeContainer:
        def exec_run(self, cmd, demux=True):
            if cmd[0] == "test":
                return _FakeResult(0)
            if cmd[0] == "find":
                return _FakeResult(0, b"/data/Show/Show.S01E01.mkv\n")
            if cmd[0] == "timeout":
                # dd read succeeds -> readable -> not blocklisted
                return _FakeResult(0)
            raise AssertionError(f"unexpected exec cmd: {cmd}")

    class _FakeResult:
        def __init__(self, exit_code, output=b""):
            self.exit_code = exit_code
            self.output = output

    class _FakeDocker:
        class containers:
            @staticmethod
            def get(name):
                return _FakeContainer()

    monkeypatch.setattr(services, "docker_client", _FakeDocker())

    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/queue/11?removeFromClient=true&blocklist=false&skipRedownload=false",
        method="DELETE", json={},
    )
    httpx_mock.add_response(url="http://sonarr:8989/api/v3/command", method="POST", json={})

    result = services.unstick_importing("sonarr")
    assert result["results"][0]["verdict"] == "wedged-cleared"
    assert "1 wedged/cleared" in result["message"]


def test_unstick_importing_broken_blocklisted(httpx_mock, monkeypatch):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeMovie=true",
        json={"records": [{"id": 11, "downloadId": "nzo-1", "title": "Movie.Two", "outputPath": "/data/Movie",
                           "trackedDownloadState": "importing", "movieId": 9}]},
    )

    class _FakeContainer:
        def exec_run(self, cmd, demux=True):
            if cmd[0] == "test":
                return _FakeResult(0)
            if cmd[0] == "find":
                return _FakeResult(0, b"/data/Movie/Movie.Two.mkv\n")
            # dd read test fails -> unreadable -> blocklist
            if cmd[0] == "timeout":
                return _FakeResult(1, (None, b"Input/output error"))
            raise AssertionError(f"unexpected exec cmd: {cmd}")

    class _FakeResult:
        def __init__(self, exit_code, output=b""):
            self.exit_code = exit_code
            self.output = output

    class _FakeDocker:
        class containers:
            @staticmethod
            def get(name):
                return _FakeContainer()

    monkeypatch.setattr(services, "docker_client", _FakeDocker())

    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/queue/11?removeFromClient=true&blocklist=true&skipRedownload=false",
        method="DELETE", json={},
    )
    httpx_mock.add_response(url="http://radarr:7878/api/v3/command", method="POST", json={})

    result = services.unstick_importing("radarr")
    assert result["results"][0]["verdict"] == "broken-blocklisted"
    assert "1 broken/blocklisted" in result["message"]


def test_unstick_importing_container_not_found_raises(httpx_mock, monkeypatch):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeMovie=true",
        json={"records": [{"id": 11, "downloadId": "nzo-1", "title": "Movie", "outputPath": "/data/Movie",
                           "trackedDownloadState": "importing"}]},
    )

    class _FakeDocker:
        class containers:
            @staticmethod
            def get(name):
                raise docker.errors.NotFound("nope")

    monkeypatch.setattr(services, "docker_client", _FakeDocker())
    with pytest.raises(ServiceError):
        services.unstick_importing("radarr")


# ---------------------------------------------------------------------------
# import_starvation / queue_autofix
# ---------------------------------------------------------------------------


def test_import_starvation_status_builds_message(monkeypatch):
    monkeypatch.setattr(
        "arr.services.import_starvation.check_all",
        lambda remediate=False: {
            "apps": {}, "starved": ["radarr"], "lagging": [],
            "remediated": {},
        },
    )
    result = services.import_starvation_status()
    assert "1 app(s) starved" in result["message"]
    assert result["starved"] == ["radarr"]


def test_import_starvation_status_healthy(monkeypatch):
    monkeypatch.setattr(
        "arr.services.import_starvation.check_all",
        lambda remediate=False: {"apps": {}, "starved": [], "lagging": [], "remediated": {}},
    )
    result = services.import_starvation_status()
    assert result["message"] == "Every app is importing in step with its grabs."


def test_queue_autofix_fixes_and_reports(httpx_mock, monkeypatch):
    monkeypatch.setattr(
        "arr.services.import_starvation.check_all",
        lambda remediate=True: {
            "apps": {}, "starved": [], "lagging": [], "remediated": {},
        },
    )
    monkeypatch.setattr(
        "arr.services.settings_core.get_settings",
        lambda: {"failed_pending_storm_threshold": 15, "loop_review_profile_threshold": 8, "recent_values": {}},
    )
    # radarr queue: one failedPending item that gets fixed
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeMovie=true",
        json={"records": [{"id": 1, "title": "Movie.One", "trackedDownloadState": "failedPending", "movieId": 3}]},
    )
    # item_is_monitored does a direct movie lookup
    httpx_mock.add_response(url="http://radarr:7878/api/v3/movie/3", json={"monitored": True})
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/queue/1?removeFromClient=true&blocklist=true&skipRedownload=false",
        method="DELETE", json={},
    )
    httpx_mock.add_response(url="http://radarr:7878/api/v3/command", method="POST", json={})
    # sonarr queue: empty
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeEpisode=true",
        json={"records": []},
    )
    # nzbdav queue (unpaused)
    httpx_mock.add_response(
        url="http://nzbdav:3000/api?mode=queue&output=json&apikey=test-nzbdav-key",
        json={"queue": {"paused": False, "slots": []}},
    )

    result = services.queue_autofix()
    assert result["radarr"]["failed_pending"] == 1
    assert result["radarr"]["fixed"] == ["Movie.One"]
    assert "Fixed 1 stuck queue item(s)" in result["message"]
    assert result["nzbdav"] == {"slots": 0, "paused": False}


def test_queue_autofix_tolerates_unreachable_arr(httpx_mock, monkeypatch):
    monkeypatch.setattr(
        "arr.services.import_starvation.check_all",
        lambda remediate=True: {"apps": {}, "starved": [], "lagging": [], "remediated": {}},
    )
    monkeypatch.setattr(
        "arr.services.settings_core.get_settings",
        lambda: {"failed_pending_storm_threshold": 15, "recent_values": {}},
    )
    # radarr fails first and queue_autofix propagates (arr_queue raises
    # ServiceError on an unreachable app, unlike the read-only aggregation
    # routes) - so only the radarr mock is needed; sonarr never gets read.
    httpx_mock.add_exception(httpx.ConnectError("refused"),
                             url="http://radarr:7878/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeMovie=true")
    with pytest.raises(ServiceError):
        services.queue_autofix()


# ---------------------------------------------------------------------------
# loop_candidates / unmonitor
# ---------------------------------------------------------------------------


def _history_record(target_id, title, date, releases=("Rel.One",)):
    return {
        "id": target_id, "movieId": target_id, "episodeId": target_id,
        "date": date, "sourceTitle": title, "eventType": 4,
        "releases": [{"title": r} for r in releases],
    }


def test_loop_candidates_flags_repeats(httpx_mock, monkeypatch):
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old = (now - timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/history?eventType=4&pageSize=500&sortKey=date&sortDirection=descending",
        json={"records": [
            _history_record(1, "Movie.A", recent),
            _history_record(1, "Movie.A", recent),
            _history_record(2, "Movie.B", old),  # outside window -> ignored
        ]},
    )
    # get_movie_or_episode detail lookups
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/movie/1",
        json={"id": 1, "title": "Movie.A", "monitored": True, "hasFile": False},
    )
    # current_queue_output_path uses the queue
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeMovie=true",
        json={"records": [{"id": 1, "movieId": 1, "outputPath": "/data/Movie.A"}]},
    )
    monkeypatch.setattr(
        "arr.services.settings_core.get_settings",
        lambda: {"loop_review_profile_threshold": 8, "recent_values": {}},
    )

    result = services.loop_candidates("radarr", hours=6.0)
    assert result["app"] == "radarr"
    assert len(result["candidates"]) == 1
    cand = result["candidates"][0]
    assert cand["id"] == 1
    assert cand["occurrences"] == 2
    assert cand["suggested_action"] == "unmonitor"
    assert "1 looping candidate(s) in the last 6h" in result["message"]


def test_loop_candidates_sonarr_scene_mismatch(httpx_mock, monkeypatch):
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/history?eventType=4&pageSize=500&sortKey=date&sortDirection=descending",
        json={"records": [
            {"id": 1, "episodeId": 1, "date": recent, "sourceTitle": "Show.S01E01",
             "eventType": 4, "releases": [{"title": "Rel"}]},
            {"id": 1, "episodeId": 1, "date": recent, "sourceTitle": "Show.S01E01",
             "eventType": 4, "releases": [{"title": "Rel"}]},
        ]},
    )
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/episode/1",
        json={"id": 1, "title": "Pilot", "monitored": True, "hasFile": False,
              "episodeNumber": 1, "seasonNumber": 1,
              "sceneEpisodeNumber": 3, "sceneSeasonNumber": 1,
              "series": {"title": "Show"}, "seriesId": 9},
    )
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeEpisode=true",
        json={"records": [{"id": 1, "episodeId": 1, "outputPath": "/data/Show"}]},
    )
    monkeypatch.setattr(
        "arr.services.settings_core.get_settings",
        lambda: {"loop_review_profile_threshold": 8, "recent_values": {}},
    )

    result = services.loop_candidates("sonarr", hours=6.0)
    cand = result["candidates"][0]
    assert cand["suggested_action"] == "unmonitor"
    assert "scene numbering mismatch" in cand["reason"]
    assert cand["title"].startswith("Show S01E01")


def test_loop_candidates_already_unmonitored(httpx_mock, monkeypatch):
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/history?eventType=4&pageSize=500&sortKey=date&sortDirection=descending",
        json={"records": [
            {"id": 1, "episodeId": 1, "date": recent, "sourceTitle": "Show.S01E01",
             "eventType": 4, "releases": [{"title": "Rel"}]},
            {"id": 1, "episodeId": 1, "date": recent, "sourceTitle": "Show.S01E01",
             "eventType": 4, "releases": [{"title": "Rel"}]},
        ]},
    )
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/episode/1",
        json={"id": 1, "title": "Pilot", "monitored": False, "hasFile": False,
              "episodeNumber": 1, "seasonNumber": 1,
              "series": {"title": "Show"}, "seriesId": 9},
    )
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeEpisode=true",
        json={"records": [{"id": 1, "episodeId": 1, "outputPath": "/data/Show"}]},
    )
    monkeypatch.setattr(
        "arr.services.settings_core.get_settings",
        lambda: {"loop_review_profile_threshold": 8, "recent_values": {}},
    )

    result = services.loop_candidates("sonarr", hours=6.0)
    assert result["candidates"][0]["suggested_action"] == "none"
    assert result["candidates"][0]["reason"] == "Already unmonitored."


def test_unmonitor_movies_bulk_put(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/movie/editor", method="PUT", json={},
    )
    result = services.unmonitor("radarr", [1, 2, 3])
    assert result["message"] == "Unmonitored 3 item(s) in Radarr."
    assert result["ids"] == [1, 2, 3]


def test_unmonitor_sonarr_episode_put(httpx_mock):
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/episode/monitor", method="PUT", json={},
    )
    result = services.unmonitor("sonarr", [7])
    assert "Unmonitored 1 item(s) in Sonarr." in result["message"]


def test_unmonitor_empty_ids_raises():
    with pytest.raises(ServiceError) as exc_info:
        services.unmonitor("radarr", [])
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# manual_import / manual_import_all / missing_aired
# ---------------------------------------------------------------------------


def test_manual_import_candidates_lists_files(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeMovie=true",
        json={"records": [{"id": 1, "title": "Movie.One", "downloadId": "nzo-1",
                           "outputPath": "/data/Movie.One", "trackedDownloadState": "importPending"}]},
    )
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/manualimport?folder=/data/Movie.One&downloadId=nzo-1&filterExistingFiles=true",
        json=[{
            "path": "/data/Movie.One/Movie.One.mkv", "name": "Movie.One.mkv",
            "relativePath": "Movie.One.mkv", "size": 1024 * 1024,
            "quality": {"quality": {"name": "1080p"}}, "languages": [{"name": "English"}],
            "releaseGroup": "GRP", "downloadId": "nzo-1", "rejections": [{"reason": "Sample"}],
            "movie": {"id": 3, "title": "Movie One"},
        }],
    )
    candidates = services.manual_import_candidates("radarr")
    assert len(candidates) == 1
    c = candidates[0]
    assert c["name"] == "Movie.One.mkv"
    assert c["size"] == "1.0 MB"
    assert c["quality"] == "1080p"
    assert c["rejections"] == ["Sample"]
    assert c["match_title"] == "Movie One"
    assert c["file"]["movieId"] == 3


def test_manual_import_execute_posts_command(httpx_mock):
    payload = {"path": "/data/Movie.One/Movie.One.mkv", "quality": {"quality": {"name": "1080p"}},
               "languages": [], "movieId": 3}
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/command", method="POST", json={},
    )
    message = services.manual_import_execute("radarr", payload)
    assert message == 'Import started for "Movie.One.mkv" in Radarr.'


def test_manual_import_all_skips_unmatched(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeMovie=true",
        json={"records": [{"id": 1, "title": "Movie.One", "downloadId": "nzo-1",
                           "outputPath": "/data/Movie.One", "trackedDownloadState": "importPending"}]},
    )
    # manualimport returns a file with no movie match -> skipped
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/manualimport?folder=/data/Movie.One&downloadId=nzo-1&filterExistingFiles=true",
        json=[{"path": "/data/Movie.One/Movie.One.mkv", "name": "Movie.One.mkv",
               "quality": {"quality": {"name": "1080p"}}, "languages": [], "rejections": []}],
    )
    message = services.manual_import_all("radarr")
    assert "No importable files in Radarr." in message
    assert "1 file(s) have no resolved match" in message


def test_missing_aired_movies(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/movie",
        json=[
            {"title": "Aired Movie", "year": 2024, "monitored": True, "hasFile": False,
             "isAvailable": True, "digitalRelease": "2024-01-01T00:00:00Z"},
            {"title": "Not Available", "monitored": True, "hasFile": False, "isAvailable": False},
            {"title": "Has File", "monitored": True, "hasFile": True, "isAvailable": True},
        ],
    )
    results = services.missing_aired("radarr")
    assert len(results) == 1
    assert results[0]["title"] == "Aired Movie"


def test_missing_aired_sonarr_paginates(httpx_mock):
    now = datetime.now(timezone.utc)
    past = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    future = (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/wanted/missing?page=1&pageSize=250&sortKey=airDateUtc&sortDirection=ascending&includeSeries=true",
        json={"totalRecords": 2, "records": [
            {"seasonNumber": 1, "episodeNumber": 1, "title": "Pilot", "airDateUtc": past,
             "series": {"title": "Show"}},
            {"seasonNumber": 1, "episodeNumber": 2, "title": "Future", "airDateUtc": future,
             "series": {"title": "Show"}},
        ]},
    )
    results = services.missing_aired("sonarr")
    assert len(results) == 1
    assert results[0]["episode"] == "S01E01"
    assert results[0]["series"] == "Show"


# ---------------------------------------------------------------------------
# blocklist / blocklist_clear
# ---------------------------------------------------------------------------


def test_blocklist_lists_records(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/blocklist?page=1&pageSize=50&sortKey=date&sortDirection=descending",
        json={"totalRecords": 2, "records": [
            {"id": 1, "sourceTitle": "Bad.Release", "date": "2026-08-01T00:00:00Z", "movieId": 3},
        ]},
    )
    result = services.blocklist("radarr")
    assert result["total"] == 2
    assert result["records"] == [{"id": 1, "title": "Bad.Release", "date": "2026-08-01T00:00:00Z",
                                  "seriesId": None, "movieId": 3}]
    assert "2 total blocklist entry(ies)" in result["message"]


def test_blocklist_clear_loops_pages(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/blocklist?page=1&pageSize=250",
        json={"records": [{"id": 1}, {"id": 2}]},
    )
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/blocklist/bulk", method="DELETE", json={},
    )
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/blocklist?page=1&pageSize=250",
        json={"records": []},
    )
    result = services.blocklist_clear("radarr")
    assert result["cleared"] == 2
    assert "Cleared 2 blocklist entry(ies)" in result["message"]


# ---------------------------------------------------------------------------
# backlog_status / command_queue_summary / queue_errors - partial failure
# ---------------------------------------------------------------------------


def test_backlog_status_partial_failure(httpx_mock):
    # radarr reachable with 2 missing + recent import rate
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/wanted/missing?pageSize=1",
        json={"totalRecords": 2},
    )
    now = datetime.now(timezone.utc)
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/history?pageSize=200&sortKey=date&sortDirection=descending",
        json={"records": [
            {"eventType": "downloadFolderImported", "date": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")},
            {"eventType": "downloadFolderImported", "date": (now - timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        ]},
    )
    # sonarr unreachable -> error entry, not a 500
    httpx_mock.add_exception(httpx.ConnectError("refused"),
                             url="http://sonarr:8989/api/v3/wanted/missing?pageSize=1")
    result = services.backlog_status()
    assert result["apps"]["radarr"]["missing"] == 2
    assert result["apps"]["radarr"]["rate_per_hour"] > 0
    assert result["apps"]["radarr"]["eta"] != "unknown"
    assert result["apps"]["sonarr"] == {"label": "Sonarr", "error": "unreachable"}
    # len(result) counts every entry including the errored one - matches
    # the FastAPI-era source exactly ("across {len(result)} apps.")
    assert "2 item(s) missing across 2 apps." in result["message"]


def test_command_queue_summary_partial_failure(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/command",
        json=[{"id": 1, "status": "queued"}, {"id": 2, "status": "started"}],
    )
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/command",
        json=[{"id": 3, "status": "queued"}],
    )
    httpx_mock.add_exception(httpx.ConnectError("refused"), url="http://prowlarr:9696/api/v1/command")
    result = services.command_queue_summary()
    assert result["apps"]["radarr"] == {"total": 2, "queued": 1, "running": 1}
    assert result["apps"]["sonarr"] == {"total": 1, "queued": 1, "running": 0}
    assert "error" in result["apps"]["prowlarr"]
    assert "2 commands queued across 3 apps." in result["message"]


def test_queue_errors_partial_failure(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeMovie=true",
        json={"records": [
            {"title": "Movie.One", "trackedDownloadStatus": "error", "statusMessages": [{"title": "Import failed"}]},
            {"title": "Movie.Two", "trackedDownloadStatus": "ok"},
        ]},
    )
    httpx_mock.add_exception(httpx.ConnectError("refused"),
                             url="http://sonarr:8989/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeEpisode=true")
    result = services.queue_errors()
    assert result["apps"]["radarr"] == [
        {"title": "Movie.One", "status": "error", "messages": ["Import failed"]},
    ]
    assert result["apps"]["sonarr"] == {"error": "lookup failed"}
    assert "1 queue item(s) flagged" in result["message"]


# ---------------------------------------------------------------------------
# logs / recently_added / cutoff_unmet / import_lists / implementations /
# import_list_add / customformat_snapshot
# ---------------------------------------------------------------------------


def test_logs_reads_container(monkeypatch):
    class _FakeLogsContainer:
        def logs(self, tail=100, timestamps=True):
            return b"line one\nline two\n"

    class _FakeDocker:
        class containers:
            @staticmethod
            def get(name):
                return _FakeLogsContainer()

    monkeypatch.setattr(services, "docker_client", _FakeDocker())
    assert services.logs("radarr", lines=100) == "line one\nline two\n"


def test_logs_rejects_non_log_apps():
    with pytest.raises(ServiceError) as exc_info:
        services.logs("radarr-anime", lines=100)
    assert exc_info.value.status_code == 400


def test_logs_container_not_found_raises(monkeypatch):
    class _FakeDocker:
        class containers:
            @staticmethod
            def get(name):
                raise docker.errors.NotFound("nope")

    monkeypatch.setattr(services, "docker_client", _FakeDocker())
    with pytest.raises(ServiceError):
        services.logs("radarr", lines=100)


def test_recently_added_movies(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/movie",
        json=[
            {"title": "Old", "added": "2026-01-01T00:00:00Z", "monitored": True, "statistics": {"movieFileCount": 1}},
            {"title": "New", "added": "2026-08-01T00:00:00Z", "monitored": True, "statistics": {"movieFileCount": 0}},
        ],
    )
    result = services.recently_added("radarr", limit=10)
    assert [i["title"] for i in result["items"]] == ["New", "Old"]
    assert result["items"][0]["file_count"] == 0


def test_recently_added_sonarr(httpx_mock):
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/series",
        json=[{"title": "Show", "added": "2026-08-01T00:00:00Z", "monitored": True,
               "statistics": {"episodeFileCount": 3, "episodeCount": 10}}],
    )
    result = services.recently_added("sonarr", limit=10)
    assert result["items"][0]["file_count"] == 3
    assert result["items"][0]["total_count"] == 10


def test_cutoff_unmet(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/wanted/cutoff?pageSize=20&sortKey=title",
        json={"totalRecords": 1, "records": [{"title": "Movie.One"}]},
    )
    result = services.cutoff_unmet("radarr", limit=20)
    assert result["items"] == [{"title": "Movie.One"}]
    assert result["total"] == 1


def test_import_lists(httpx_mock):
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/importlist",
        json=[{"name": "Trakt Watchlist", "enabled": True, "enableAutomaticAdd": True}],
    )
    result = services.import_lists("sonarr")
    assert result["items"] == [{"name": "Trakt Watchlist", "enabled": True, "enableAutomaticAdd": True}]


def test_import_list_implementations(httpx_mock):
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/importlist/schema",
        json=[
            {"implementation": "TraktListImport", "implementationName": "Trakt List"},
            {"implementation": "PlexImport", "implementationName": "Plex Watchlist"},
        ],
    )
    result = services.import_list_implementations("sonarr")
    assert result["items"] == [
        {"implementation": "PlexImport", "name": "Plex Watchlist"},
        {"implementation": "TraktListImport", "name": "Trakt List"},
    ]


def test_import_list_add_basic(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/importlist/schema",
        json=[{"implementation": "TMDbKeywordImport", "name": "TMDB Keyword", "fields": [{"name": "keywordId"}]}],
    )
    httpx_mock.add_response(url="http://radarr:7878/api/v3/rootfolder", json=[{"path": "/data/movies"}])
    httpx_mock.add_response(url="http://radarr:7878/api/v3/qualityprofile", json=[{"id": 1, "name": "Unlimited"}])
    httpx_mock.add_response(url="http://radarr:7878/api/v3/importlist", method="POST", json={"id": 5})

    result = services.import_list_add("radarr", {
        "implementation": "TMDbKeywordImport", "name": "My List", "fields": {"keywordId": "123"},
        "search_on_add": True, "monitor": None, "minimum_availability": "released",
    })
    assert result["id"] == 5
    assert "added to Radarr" in result["message"]


def test_import_list_add_unknown_implementation(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/importlist/schema",
        json=[{"implementation": "PlexImport", "name": "Plex Watchlist", "fields": []}],
    )
    httpx_mock.add_response(url="http://radarr:7878/api/v3/rootfolder", json=[{"path": "/data/movies"}])
    httpx_mock.add_response(url="http://radarr:7878/api/v3/qualityprofile", json=[{"id": 1}])
    with pytest.raises(ServiceError) as exc_info:
        services.import_list_add("radarr", {"implementation": "Nope", "name": "X", "fields": {}})
    assert exc_info.value.status_code == 400


def test_import_list_add_oauth_donor_reuse(httpx_mock):
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/importlist/schema",
        json=[{"implementation": "TraktListImport", "name": "Trakt List", "fields": [
            {"name": "accessToken"}, {"name": "authUser"},
        ]}],
    )
    httpx_mock.add_response(url="http://radarr:7878/api/v3/rootfolder", json=[{"path": "/data/movies"}])
    httpx_mock.add_response(url="http://radarr:7878/api/v3/qualityprofile", json=[{"id": 1}])
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/importlist",
        json=[{"implementation": "TraktListImport", "fields": [
            {"name": "accessToken", "value": "donor-token"}, {"name": "authUser", "value": "bear"},
        ]}],
    )
    httpx_mock.add_response(url="http://radarr:7878/api/v3/importlist", method="POST", json={"id": 9})

    result = services.import_list_add("radarr", {
        "implementation": "TraktListImport", "name": "Second Trakt List", "fields": {},
        "search_on_add": True, "monitor": None, "minimum_availability": "released",
    })
    assert result["id"] == 9


def test_customformat_snapshot(httpx_mock):
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/customformat",
        json=[{"id": 1, "name": "Dual Audio"}],
    )
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/qualityprofile",
        json=[{"name": "Any", "formatItems": [{"format": 1, "score": 100}]}],
    )
    result = services.customformat_snapshot("sonarr")
    assert result["profiles"] == {"Any": {"Dual Audio": 100}}
    assert "1 custom format(s) across 1 profile(s)" in result["message"]

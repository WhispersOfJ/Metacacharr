"""Tests for queue_app.services.aggregate_queue_status, ported from the
FastAPI-era control-panel/services/queue/router.py behavior (2-sample
delta-bucketing, QUEUE_SAMPLE_SECONDS apart).

time.sleep is monkeypatched to a no-op so tests don't actually block for
QUEUE_SAMPLE_SECONDS. Each mocked HTTP endpoint is registered with two
responses (pytest-httpx serves them FIFO) representing the "before" and
"after" snapshot round.
"""
import pytest

from core import nzbdav_client, plex_client
from queue_app import services


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(services.time, "sleep", lambda *_a, **_k: None)


@pytest.fixture(autouse=True)
def _plex_config(monkeypatch):
    monkeypatch.setattr(plex_client, "PLEX_URL", "http://plex:32400")
    monkeypatch.setattr(plex_client, "PLEX_TOKEN", "test-plex-token")


@pytest.fixture(autouse=True)
def _nzbdav_config(monkeypatch):
    monkeypatch.setattr(nzbdav_client, "NZBDAV_API_KEY", "test-nzbdav-key")


RADARR_QUEUE_URL = (
    "http://radarr:7878/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeMovie=true"
)
SONARR_QUEUE_URL = (
    "http://sonarr:8989/api/v3/queue?pageSize=250&includeUnknownMovieItems=true&includeEpisode=true"
)
NZBDAV_QUEUE_URL = "http://nzbdav:3000/api?mode=queue&output=json&apikey=test-nzbdav-key"
PLEX_ACTIVITIES_URL = "http://plex:32400/activities"


def _radarr_round1():
    return [
        {"id": 1, "title": "Movie A", "size": 2000, "sizeleft": 1000, "trackedDownloadState": "downloading"},
        {"id": 2, "title": "Movie B", "size": 800, "sizeleft": 800, "trackedDownloadState": "downloading"},
    ]


def _radarr_round2():
    return [
        {"id": 1, "title": "Movie A", "size": 2000, "sizeleft": 200, "trackedDownloadState": "downloading"},
        {"id": 2, "title": "Movie B", "size": 800, "sizeleft": 800, "trackedDownloadState": "downloading"},
    ]


def _sonarr_round(sizeleft=500):
    return [
        {"id": 3, "title": "Show C", "size": 500, "sizeleft": sizeleft, "trackedDownloadState": "importPending"},
        {"id": 4, "title": "Show D", "size": 300, "sizeleft": 0, "trackedDownloadState": "downloading"},
    ]


def _nzbdav_round1():
    return {"queue": {"slots": [
        {"nzo_id": "n1", "filename": "File1", "mb": 1000, "mbleft": 500, "status": "Downloading"},
        {"nzo_id": "n2", "filename": "File2", "mb": 200, "mbleft": 200, "status": "Downloading"},
        {"nzo_id": "n3", "filename": "File3", "mb": 100, "mbleft": 100, "status": "Queued"},
        {"nzo_id": "n4", "filename": "File4", "mb": 50, "mbleft": 0, "status": "Completed"},
    ]}}


def _nzbdav_round2():
    return {"queue": {"slots": [
        {"nzo_id": "n1", "filename": "File1", "mb": 1000, "mbleft": 100, "status": "Downloading"},
        {"nzo_id": "n2", "filename": "File2", "mb": 200, "mbleft": 200, "status": "Downloading"},
        {"nzo_id": "n3", "filename": "File3", "mb": 100, "mbleft": 100, "status": "Queued"},
        {"nzo_id": "n4", "filename": "File4", "mb": 50, "mbleft": 0, "status": "Completed"},
    ]}}


def _plex_round1():
    return {"MediaContainer": {"Activity": [
        {"uuid": "p1", "title": "Analyzing", "progress": 20},
        {"uuid": "p2", "title": "Deep scan", "subtitle": "Section X", "progress": 50},
    ]}}


def _plex_round2():
    return {"MediaContainer": {"Activity": [
        {"uuid": "p1", "title": "Analyzing", "progress": 60},
        {"uuid": "p2", "title": "Deep scan", "subtitle": "Section X", "progress": 50},
    ]}}


def _mock_happy_path(httpx_mock):
    httpx_mock.add_response(url=RADARR_QUEUE_URL, json={"records": _radarr_round1()})
    httpx_mock.add_response(url=RADARR_QUEUE_URL, json={"records": _radarr_round2()})
    httpx_mock.add_response(url=SONARR_QUEUE_URL, json={"records": _sonarr_round()})
    httpx_mock.add_response(url=SONARR_QUEUE_URL, json={"records": _sonarr_round()})
    httpx_mock.add_response(url=NZBDAV_QUEUE_URL, json=_nzbdav_round1())
    httpx_mock.add_response(url=NZBDAV_QUEUE_URL, json=_nzbdav_round2())
    httpx_mock.add_response(url=PLEX_ACTIVITIES_URL, json=_plex_round1())
    httpx_mock.add_response(url=PLEX_ACTIVITIES_URL, json=_plex_round2())


class TestAggregateQueueStatusHappyPath:
    def test_radarr_buckets_downloading_and_stalled(self, httpx_mock):
        _mock_happy_path(httpx_mock)
        result = services.aggregate_queue_status()
        radarr = result["radarr"]
        assert radarr["label"] == "Radarr"
        assert radarr["total"] == 2
        titles_downloading = [i["title"] for i in radarr["downloading"]]
        titles_stalled = [i["title"] for i in radarr["stalled"]]
        assert titles_downloading == ["Movie A"]
        assert titles_stalled == ["Movie B"]
        assert "speed" in radarr["downloading"][0]
        assert "eta" in radarr["downloading"][0]
        assert radarr["stalled"][0]["note"] == "no progress observed (still caching, or stalled)"

    def test_sonarr_buckets_importing_and_queued(self, httpx_mock):
        _mock_happy_path(httpx_mock)
        result = services.aggregate_queue_status()
        sonarr = result["sonarr"]
        assert sonarr["label"] == "Sonarr"
        assert sonarr["total"] == 2
        titles_importing = [i["title"] for i in sonarr["importing"]]
        titles_queued = [i["title"] for i in sonarr["queued"]]
        assert titles_importing == ["Show C"]
        assert titles_queued == ["Show D"]

    def test_nzbdav_buckets_all_four_states(self, httpx_mock):
        _mock_happy_path(httpx_mock)
        result = services.aggregate_queue_status()
        nzbdav = result["nzbdav"]
        assert nzbdav["label"] == "NzbDAV"
        assert nzbdav["total"] == 4
        assert [i["title"] for i in nzbdav["downloading"]] == ["File1"]
        assert [i["title"] for i in nzbdav["stalled"]] == ["File2"]
        assert [i["title"] for i in nzbdav["queued"]] == ["File3"]
        assert [i["title"] for i in nzbdav["importing"]] == ["File4"]

    def test_plex_buckets_downloading_and_stalled(self, httpx_mock):
        _mock_happy_path(httpx_mock)
        result = services.aggregate_queue_status()
        plex = result["plex"]
        assert plex["label"] == "Plex"
        assert plex["total"] == 2
        assert [i["title"] for i in plex["downloading"]] == ["Analyzing"]
        assert [i["title"] for i in plex["stalled"]] == ["Deep scan: Section X"]
        assert "eta" in plex["downloading"][0]


class TestAggregateQueueStatusUnreachable:
    def test_radarr_unreachable_produces_error_without_failing_call(self, httpx_mock):
        # Radarr's queue lookup 500s on both rounds - arr_queue() raises
        # ServiceError, which _arr_sizeleft_snapshot swallows to {} and the
        # main loop catches to mark the app unreachable, without aborting
        # the rest of the aggregation.
        httpx_mock.add_response(url=RADARR_QUEUE_URL, status_code=500)
        httpx_mock.add_response(url=RADARR_QUEUE_URL, status_code=500)
        httpx_mock.add_response(url=SONARR_QUEUE_URL, json={"records": _sonarr_round()})
        httpx_mock.add_response(url=SONARR_QUEUE_URL, json={"records": _sonarr_round()})
        httpx_mock.add_response(url=NZBDAV_QUEUE_URL, json=_nzbdav_round1())
        httpx_mock.add_response(url=NZBDAV_QUEUE_URL, json=_nzbdav_round2())
        httpx_mock.add_response(url=PLEX_ACTIVITIES_URL, json=_plex_round1())
        httpx_mock.add_response(url=PLEX_ACTIVITIES_URL, json=_plex_round2())

        result = services.aggregate_queue_status()

        assert result["radarr"] == {"label": "Radarr", "error": "unreachable"}
        # the rest of the aggregation still succeeded
        assert result["sonarr"]["total"] == 2
        assert result["nzbdav"]["total"] == 4
        assert result["plex"]["total"] == 2

    def test_nzbdav_unreachable_produces_error_without_failing_call(self, httpx_mock):
        httpx_mock.add_response(url=RADARR_QUEUE_URL, json={"records": _radarr_round1()})
        httpx_mock.add_response(url=RADARR_QUEUE_URL, json={"records": _radarr_round2()})
        httpx_mock.add_response(url=SONARR_QUEUE_URL, json={"records": _sonarr_round()})
        httpx_mock.add_response(url=SONARR_QUEUE_URL, json={"records": _sonarr_round()})
        httpx_mock.add_response(url=NZBDAV_QUEUE_URL, status_code=500)
        httpx_mock.add_response(url=NZBDAV_QUEUE_URL, status_code=500)
        httpx_mock.add_response(url=PLEX_ACTIVITIES_URL, json=_plex_round1())
        httpx_mock.add_response(url=PLEX_ACTIVITIES_URL, json=_plex_round2())

        result = services.aggregate_queue_status()

        assert result["nzbdav"] == {"label": "NzbDAV", "error": "unreachable"}
        assert result["radarr"]["total"] == 2

    def test_plex_unreachable_produces_error_without_failing_call(self, httpx_mock):
        httpx_mock.add_response(url=RADARR_QUEUE_URL, json={"records": _radarr_round1()})
        httpx_mock.add_response(url=RADARR_QUEUE_URL, json={"records": _radarr_round2()})
        httpx_mock.add_response(url=SONARR_QUEUE_URL, json={"records": _sonarr_round()})
        httpx_mock.add_response(url=SONARR_QUEUE_URL, json={"records": _sonarr_round()})
        httpx_mock.add_response(url=NZBDAV_QUEUE_URL, json=_nzbdav_round1())
        httpx_mock.add_response(url=NZBDAV_QUEUE_URL, json=_nzbdav_round2())
        httpx_mock.add_response(url=PLEX_ACTIVITIES_URL, status_code=500)
        httpx_mock.add_response(url=PLEX_ACTIVITIES_URL, status_code=500)

        result = services.aggregate_queue_status()

        assert result["plex"] == {"label": "Plex", "error": "unreachable"}
        assert result["radarr"]["total"] == 2

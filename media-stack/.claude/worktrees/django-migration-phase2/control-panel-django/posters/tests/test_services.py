import json
import queue
import threading
import time

import pytest

from core import plex_client
from core.api_base import ServiceError
from posters import candidates, services, state


@pytest.fixture(autouse=True)
def _plex_config(monkeypatch):
    """PLEX_URL/PLEX_TOKEN are empty by default in the test environment
    (see core/plex_client.py's module-level os.environ.get()) - patch the
    core.plex_client module attributes directly (not env vars, since
    they're already bound), same pattern as plex/tests/test_services.py."""
    monkeypatch.setattr(plex_client, "PLEX_URL", "http://plex:32400")
    monkeypatch.setattr(plex_client, "PLEX_TOKEN", "test-plex-token")
    monkeypatch.setattr(services, "PLEX_URL", "http://plex:32400")


@pytest.fixture(autouse=True)
def _source_keys(monkeypatch):
    """TMDB_KEY/FANART_KEY/TVDB_KEY are imported into posters.services as
    separate bare names (`from posters.candidates import FANART_KEY, ...`),
    so patching posters.candidates's copies alone doesn't reach
    services._require_source_configured's own bound names - both module's
    copies need patching, same as the FastAPI-era router.py's identical
    `from services.posters.candidates import ...` shape."""
    for mod in (candidates, services):
        monkeypatch.setattr(mod, "TMDB_KEY", "test-tmdb-key")
        monkeypatch.setattr(mod, "FANART_KEY", "test-fanart-key")
        monkeypatch.setattr(mod, "TVDB_KEY", "test-tvdb-key")


@pytest.fixture(autouse=True)
def _poster_state_path(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "POSTER_STATE_PATH", str(tmp_path / "poster-sync-state.json"))


@pytest.fixture(autouse=True)
def _reset_job_state():
    for job_state in (services.POSTER_SYNC_STATE, services.POSTER_REVIEW_STATE, services.POSTER_SCAN_STATE):
        job_state["running"] = False
        job_state["queue"] = None
    yield
    for job_state in (services.POSTER_SYNC_STATE, services.POSTER_REVIEW_STATE, services.POSTER_SCAN_STATE):
        job_state["running"] = False
        job_state["queue"] = None


class FakeQueue:
    """Test double for queue.Queue - pre-populated with fixture messages,
    then a "stop sentinel" (an empty backlog that raises queue.Empty
    immediately, no real timeout wait) so the SSE generator tests run
    instantly instead of blocking on the real 1s get(timeout=1) poll."""

    def __init__(self, items):
        self._items = list(items)

    def get(self, timeout=None):
        if self._items:
            return self._items.pop(0)
        raise queue.Empty


def _tracking_thread(monkeypatch, created: list):
    real_thread = threading.Thread

    class TrackingThread(real_thread):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            created.append(self)

    monkeypatch.setattr(services.threading, "Thread", TrackingThread)


# ---------------------------------------------------------------------
# list_libraries
# ---------------------------------------------------------------------

class TestListLibraries:
    def test_filters_to_movie_and_show(self, monkeypatch):
        monkeypatch.setattr(services, "plex_sections", lambda: [
            {"key": "1", "title": "Movies", "type": "movie"},
            {"key": "2", "title": "TV Shows", "type": "show"},
            {"key": "3", "title": "Music", "type": "artist"},
        ])
        result = services.list_libraries()
        assert result["items"] == [
            {"key": "1", "title": "Movies", "type": "movie"},
            {"key": "2", "title": "TV Shows", "type": "show"},
        ]
        assert "2" in result["message"]

    def test_plex_unreachable_raises_service_error(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/sections", status_code=500)
        with pytest.raises(ServiceError) as exc:
            services.list_libraries()
        assert "Could not read Plex libraries" in str(exc.value)


# ---------------------------------------------------------------------
# start_sync / sync_stream
# ---------------------------------------------------------------------

class TestStartSync:
    def test_rejects_unconfigured_source(self, monkeypatch):
        monkeypatch.setattr(services, "FANART_KEY", None)
        with pytest.raises(ServiceError) as exc:
            services.start_sync("Movies", False, "fanart")
        assert exc.value.status_code == 503

    def test_rejects_when_plex_not_configured(self, monkeypatch):
        def _raise():
            raise ServiceError("Plex isn't configured", status=503)

        monkeypatch.setattr(services, "plex_headers", _raise)
        with pytest.raises(ServiceError) as exc:
            services.start_sync("Movies", False, "tmdb")
        assert exc.value.status_code == 503

    def test_spawns_thread_sets_running_and_rejects_concurrent_start(self, monkeypatch):
        started = threading.Event()
        release = threading.Event()
        seen_args = {}

        def fake_run(library, dry_run, q, source):
            seen_args["args"] = (library, dry_run, source)
            started.set()
            assert release.wait(timeout=2)

        monkeypatch.setattr(services, "plex_headers", lambda: None)
        monkeypatch.setattr(services, "run_poster_sync", fake_run)
        created: list = []
        _tracking_thread(monkeypatch, created)

        message = services.start_sync("Movies", True, "tmdb")
        assert "Movies" in message and "dry run" in message

        assert started.wait(timeout=2)
        assert seen_args["args"] == ("Movies", True, "tmdb")
        assert services.POSTER_SYNC_STATE["running"] is True

        with pytest.raises(ServiceError) as exc:
            services.start_sync("Movies", True, "tmdb")
        assert exc.value.status_code == 409

        release.set()
        created[0].join(timeout=2)
        assert services.POSTER_SYNC_STATE["running"] is False


class TestSyncStream:
    def test_raises_404_when_not_started(self):
        with pytest.raises(ServiceError) as exc:
            services.sync_stream()
        assert exc.value.status_code == 404

    def test_yields_queued_messages_as_sse_lines(self):
        services.POSTER_SYNC_STATE["queue"] = FakeQueue(["line1", "line2"])
        services.POSTER_SYNC_STATE["running"] = False
        result = list(services.sync_stream())
        assert result == ["data: line1\n\n", "data: line2\n\n"]


class TestRunPosterSync:
    def test_no_matching_library_puts_error(self, monkeypatch):
        monkeypatch.setattr(services, "plex_sections", lambda: [{"key": "1", "title": "Movies", "type": "movie"}])
        q = queue.Queue()
        services.run_poster_sync("Nonexistent", False, q, "tmdb")
        assert "ERROR" in q.get_nowait()

    def test_plex_sections_error_puts_error_line(self, monkeypatch, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/sections", status_code=500)
        q = queue.Queue()
        services.run_poster_sync("Movies", False, q, "tmdb")
        assert q.get_nowait().startswith("ERROR Could not read Plex libraries")

    def test_dry_run_reports_would_set_without_uploading(self, httpx_mock, monkeypatch):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?X-Plex-Container-Size=100000",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100", "title": "Foo", "year": 2020}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/metadata/100",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100", "Guid": [{"id": "tmdb://5"}]}]}},
        )
        monkeypatch.setattr(services, "resolve_poster_candidates", lambda meta, mt, src, limit=1: ("tmdb", [{"url": "https://poster", "label": "l"}]))
        q = queue.Queue()
        services.run_poster_sync("Movies", True, q, "tmdb")
        lines = []
        while True:
            try:
                lines.append(q.get_nowait())
            except queue.Empty:
                break
        assert any("would set poster" in line for line in lines)
        assert lines[-1].startswith("DONE 1 updated, 0 skipped, 0 failed")

    def test_live_run_uploads_and_records_cooldown(self, httpx_mock, monkeypatch):
        monkeypatch.setattr(time, "sleep", lambda *_: None)
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?X-Plex-Container-Size=100000",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100", "title": "Foo", "year": 2020}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/metadata/100",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100", "Guid": [{"id": "tmdb://5"}]}]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/metadata/100/posters?url=https%3A%2F%2Fposter", method="POST")
        monkeypatch.setattr(services, "resolve_poster_candidates", lambda meta, mt, src, limit=1: ("tmdb", [{"url": "https://poster", "label": "l"}]))
        q = queue.Queue()
        services.run_poster_sync("Movies", False, q, "tmdb")
        lines = []
        while True:
            try:
                lines.append(q.get_nowait())
            except queue.Empty:
                break
        assert any("poster updated" in line for line in lines)
        saved = state.load_poster_state()
        assert "100" in saved

    def test_cooldown_item_is_skipped(self, httpx_mock):
        state.save_poster_state({"100": time.time()})
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?X-Plex-Container-Size=100000",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100", "title": "Foo", "year": 2020}]}},
        )
        q = queue.Queue()
        services.run_poster_sync("Movies", False, q, "tmdb")
        lines = []
        while True:
            try:
                lines.append(q.get_nowait())
            except queue.Empty:
                break
        assert any("cooldown" in line for line in lines)
        assert lines[-1].startswith("DONE 0 updated, 1 skipped, 0 failed")

    def test_metadata_fetch_failure_marks_failed(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?X-Plex-Container-Size=100000",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100", "title": "Foo", "year": 2020}]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/metadata/100", status_code=500)
        q = queue.Queue()
        services.run_poster_sync("Movies", False, q, "tmdb")
        lines = []
        while True:
            try:
                lines.append(q.get_nowait())
            except queue.Empty:
                break
        assert lines[-1].startswith("DONE 0 updated, 0 skipped, 1 failed")

    def test_no_candidates_is_skipped(self, httpx_mock, monkeypatch):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?X-Plex-Container-Size=100000",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100", "title": "Foo", "year": 2020}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/metadata/100",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100"}]}},
        )
        monkeypatch.setattr(services, "resolve_poster_candidates", lambda meta, mt, src, limit=1: (None, []))
        q = queue.Queue()
        services.run_poster_sync("Movies", False, q, "tmdb")
        lines = []
        while True:
            try:
                lines.append(q.get_nowait())
            except queue.Empty:
                break
        assert lines[-1].startswith("DONE 0 updated, 1 skipped, 0 failed")

    def test_poster_upload_failure_marks_failed(self, httpx_mock, monkeypatch):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?X-Plex-Container-Size=100000",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100", "title": "Foo", "year": 2020}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/metadata/100",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100"}]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/metadata/100/posters?url=https%3A%2F%2Fposter", method="POST", status_code=500)
        monkeypatch.setattr(services, "resolve_poster_candidates", lambda meta, mt, src, limit=1: ("tmdb", [{"url": "https://poster", "label": "l"}]))
        q = queue.Queue()
        services.run_poster_sync("Movies", False, q, "tmdb")
        lines = []
        while True:
            try:
                lines.append(q.get_nowait())
            except queue.Empty:
                break
        assert lines[-1].startswith("DONE 0 updated, 0 skipped, 1 failed")

    def test_list_error_puts_error_line(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/sections/1/all?X-Plex-Container-Size=100000", status_code=500)
        q = queue.Queue()
        services.run_poster_sync("Movies", False, q, "tmdb")
        assert q.get_nowait().startswith("ERROR Could not list")


# ---------------------------------------------------------------------
# start_review / review_stream
# ---------------------------------------------------------------------

class TestStartReview:
    def test_rejects_unconfigured_source(self, monkeypatch):
        monkeypatch.setattr(services, "TVDB_KEY", None)
        with pytest.raises(ServiceError) as exc:
            services.start_review("Movies", "tvdb")
        assert exc.value.status_code == 503

    def test_spawns_thread_sets_running_and_rejects_concurrent_start(self, monkeypatch):
        started = threading.Event()
        release = threading.Event()

        def fake_run(library, source, q):
            started.set()
            assert release.wait(timeout=2)

        monkeypatch.setattr(services, "plex_headers", lambda: None)
        monkeypatch.setattr(services, "run_poster_review", fake_run)
        created: list = []
        _tracking_thread(monkeypatch, created)

        message = services.start_review("Movies", "fanart")
        assert "Movies" in message

        assert started.wait(timeout=2)
        assert services.POSTER_REVIEW_STATE["running"] is True

        with pytest.raises(ServiceError) as exc:
            services.start_review("Movies", "fanart")
        assert exc.value.status_code == 409

        release.set()
        created[0].join(timeout=2)
        assert services.POSTER_REVIEW_STATE["running"] is False


class TestReviewStream:
    def test_raises_404_when_not_started(self):
        with pytest.raises(ServiceError) as exc:
            services.review_stream()
        assert exc.value.status_code == 404

    def test_yields_queued_messages_as_sse_lines(self):
        services.POSTER_REVIEW_STATE["queue"] = FakeQueue(["a", "b"])
        services.POSTER_REVIEW_STATE["running"] = False
        result = list(services.review_stream())
        assert result == ["data: a\n\n", "data: b\n\n"]


class TestRunPosterReview:
    def test_happy_path_emits_start_item_done(self, httpx_mock, monkeypatch):
        monkeypatch.setattr(time, "sleep", lambda *_: None)
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?X-Plex-Container-Size=100000",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100", "title": "Foo", "year": 2020}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/metadata/100",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100"}]}},
        )
        monkeypatch.setattr(services, "resolve_poster_candidates", lambda meta, mt, src, limit=3: ("fanart", [{"url": "https://x", "label": "l"}]))
        q = queue.Queue()
        services.run_poster_review("Movies", "fanart", q)
        lines = [json.loads(q.get_nowait()) for _ in range(3)]
        assert lines[0]["type"] == "start"
        assert lines[1]["type"] == "item" and lines[1]["candidates"]
        assert lines[2]["type"] == "done"

    def test_no_matching_library_puts_error(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        q = queue.Queue()
        services.run_poster_review("Nonexistent", "fanart", q)
        payload = json.loads(q.get_nowait())
        assert payload["type"] == "error"

    def test_plex_sections_error_puts_error(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/sections", status_code=500)
        q = queue.Queue()
        services.run_poster_review("Movies", "fanart", q)
        assert json.loads(q.get_nowait())["type"] == "error"

    def test_list_error_puts_error(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/sections/1/all?X-Plex-Container-Size=100000", status_code=500)
        q = queue.Queue()
        services.run_poster_review("Movies", "fanart", q)
        assert json.loads(q.get_nowait())["type"] == "error"

    def test_metadata_fetch_failure_emits_empty_candidates(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?X-Plex-Container-Size=100000",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100", "title": "Foo", "year": 2020}]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/metadata/100", status_code=500)
        q = queue.Queue()
        services.run_poster_review("Movies", "fanart", q)
        q.get_nowait()  # start
        item = json.loads(q.get_nowait())
        assert item["type"] == "item" and item["candidates"] == []


# ---------------------------------------------------------------------
# apply_poster
# ---------------------------------------------------------------------

class TestApplyPoster:
    def test_success_records_cooldown(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/metadata/100/posters?url=https%3A%2F%2Fposter", method="POST")
        message = services.apply_poster("100", "https://poster")
        assert message == "Poster updated."
        assert "100" in state.load_poster_state()

    def test_upload_failure_raises(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/metadata/100/posters?url=https%3A%2F%2Fposter", method="POST", status_code=500)
        with pytest.raises(ServiceError):
            services.apply_poster("100", "https://poster")


# ---------------------------------------------------------------------
# gallery / thumb
# ---------------------------------------------------------------------

class TestGallery:
    def test_no_matching_library_raises_404(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        with pytest.raises(ServiceError) as exc:
            services.gallery("Nonexistent")
        assert exc.value.status_code == 404

    def test_success_builds_thumb_urls(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?X-Plex-Container-Start=0&X-Plex-Container-Size=60&sort=titleSort",
            json={"MediaContainer": {"totalSize": 1, "Metadata": [
                {"ratingKey": "100", "title": "Foo", "year": 2020, "thumb": "/thumb/100"},
            ]}},
        )
        result = services.gallery("Movies")
        assert result["items"] == [{"ratingKey": "100", "title": "Foo", "year": 2020, "thumbUrl": "/api/v2/posters/thumb/100"}]
        assert result["total"] == 1

    def test_item_without_thumb_has_no_thumb_url(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?X-Plex-Container-Start=0&X-Plex-Container-Size=60&sort=titleSort",
            json={"MediaContainer": {"totalSize": 1, "Metadata": [{"ratingKey": "100", "title": "Foo"}]}},
        )
        result = services.gallery("Movies")
        assert result["items"][0]["thumbUrl"] is None

    def test_plex_sections_unreachable_raises_service_error(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/sections", status_code=500)
        with pytest.raises(ServiceError) as exc:
            services.gallery("Movies")
        assert "Could not read Plex libraries" in str(exc.value)

    def test_item_listing_unreachable_raises_service_error(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?X-Plex-Container-Start=0&X-Plex-Container-Size=60&sort=titleSort",
            status_code=500,
        )
        with pytest.raises(ServiceError) as exc:
            services.gallery("Movies")
        assert "Could not list 'Movies'" in str(exc.value)


class TestThumb:
    def test_success_returns_bytes_and_content_type(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/metadata/100/thumb",
            content=b"\xff\xd8", headers={"content-type": "image/jpeg"},
        )
        content, content_type = services.thumb("100")
        assert content == b"\xff\xd8"
        assert content_type == "image/jpeg"

    def test_not_found_raises_404(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/metadata/100/thumb", status_code=404)
        with pytest.raises(ServiceError) as exc:
            services.thumb("100")
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------
# start_scan / scan_stream
# ---------------------------------------------------------------------

class TestStartScan:
    def test_rejects_when_plex_not_configured(self, monkeypatch):
        def _raise():
            raise ServiceError("Plex isn't configured", status=503)

        monkeypatch.setattr(services, "plex_headers", _raise)
        with pytest.raises(ServiceError):
            services.start_scan("Movies")

    def test_spawns_thread_sets_running_and_rejects_concurrent_start(self, monkeypatch):
        started = threading.Event()
        release = threading.Event()

        def fake_run(library, q):
            started.set()
            assert release.wait(timeout=2)

        monkeypatch.setattr(services, "plex_headers", lambda: None)
        monkeypatch.setattr(services, "run_poster_scan", fake_run)
        created: list = []
        _tracking_thread(monkeypatch, created)

        message = services.start_scan("Movies")
        assert "Movies" in message

        assert started.wait(timeout=2)
        assert services.POSTER_SCAN_STATE["running"] is True

        with pytest.raises(ServiceError) as exc:
            services.start_scan("Movies")
        assert exc.value.status_code == 409

        release.set()
        created[0].join(timeout=2)
        assert services.POSTER_SCAN_STATE["running"] is False


class TestScanStream:
    def test_raises_404_when_not_started(self):
        with pytest.raises(ServiceError) as exc:
            services.scan_stream()
        assert exc.value.status_code == 404

    def test_yields_queued_messages_as_sse_lines(self):
        services.POSTER_SCAN_STATE["queue"] = FakeQueue(["a", "b"])
        services.POSTER_SCAN_STATE["running"] = False
        result = list(services.scan_stream())
        assert result == ["data: a\n\n", "data: b\n\n"]


class TestRunPosterScan:
    def test_happy_path_flags_no_poster_item(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?X-Plex-Container-Size=100000",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100", "title": "Foo", "year": 2020}]}},
        )
        q = queue.Queue()
        services.run_poster_scan("Movies", q)
        q.get_nowait()  # start
        item = json.loads(q.get_nowait())
        assert item["flags"] == ["no_poster"]
        done = json.loads(q.get_nowait())
        assert done == {"type": "done", "flagged": 1, "total": 1}

    def test_scans_existing_poster_with_scan_item_quality(self, httpx_mock, monkeypatch):
        monkeypatch.setattr(time, "sleep", lambda *_: None)
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?X-Plex-Container-Size=100000",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100", "title": "Foo", "year": 2020, "thumb": "/t"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/metadata/100",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100"}]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/metadata/100/thumb", content=b"abc")
        monkeypatch.setattr(services, "scan_item_quality", lambda meta, mt, poster_bytes: ["low_res"])
        q = queue.Queue()
        services.run_poster_scan("Movies", q)
        q.get_nowait()  # start
        item = json.loads(q.get_nowait())
        assert item["flags"] == ["low_res"]

    def test_metadata_fetch_failure_emits_error_flag(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?X-Plex-Container-Size=100000",
            json={"MediaContainer": {"Metadata": [{"ratingKey": "100", "title": "Foo", "year": 2020, "thumb": "/t"}]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/metadata/100", status_code=500)
        q = queue.Queue()
        services.run_poster_scan("Movies", q)
        q.get_nowait()  # start
        item = json.loads(q.get_nowait())
        assert item.get("error") == "could not fetch"

    def test_no_matching_library_puts_error(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        q = queue.Queue()
        services.run_poster_scan("Nonexistent", q)
        assert json.loads(q.get_nowait())["type"] == "error"

    def test_plex_sections_error_puts_error(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/sections", status_code=500)
        q = queue.Queue()
        services.run_poster_scan("Movies", q)
        assert json.loads(q.get_nowait())["type"] == "error"

    def test_list_error_puts_error(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/sections/1/all?X-Plex-Container-Size=100000", status_code=500)
        q = queue.Queue()
        services.run_poster_scan("Movies", q)
        assert json.loads(q.get_nowait())["type"] == "error"

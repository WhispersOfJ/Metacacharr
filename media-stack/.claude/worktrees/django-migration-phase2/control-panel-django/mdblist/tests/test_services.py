import pytest

from core.api_base import ServiceError
from core.models import MDBListSyncLog, MDBListTrackedList
from mdblist import services

LIST_URL = "https://mdblist.com/lists/bear/my-list/"


@pytest.fixture(autouse=True)
def _force_test_mdblist_key(monkeypatch):
    """conftest.py seeds MDBLIST_KEY via os.environ.setdefault, which is
    honored only when the shell hasn't already exported the real key. When
    it has (this host does), the service sends apikey=<real key> and these
    tests' httpx mocks (apikey=test-mdblist-key) match nothing. Force the
    test key so the suite is hermetic regardless of the host environment."""
    monkeypatch.setenv("MDBLIST_KEY", "test-mdblist-key")

MOVIES_PAGE = {
    "movies": [{"title": "The Matrix", "ids": {"tmdb": 603}}],
    "shows": [],
    "pagination": {"has_more": False, "next_cursor": None},
}

MIXED_PAGE = {
    "movies": [{"title": "The Matrix", "ids": {"tmdb": 603}}],
    "shows": [{"title": "Severance", "ids": {"tvdb": 371980}}],
    "pagination": {"has_more": False, "next_cursor": None},
}


def _mock_arr(monkeypatch, radarr_result=None, sonarr_result=None):
    monkeypatch.setattr(
        "mdblist.services.radarr_root_folder_and_profile",
        lambda cfg, root, profile: ("/data/movies", 1),
    )
    monkeypatch.setattr(
        "mdblist.services.sonarr_root_folder_and_profile",
        lambda cfg, root, profile: ("/data/shows", 1),
    )
    monkeypatch.setattr(
        "mdblist.services.radarr_add_movie",
        lambda *a, **k: radarr_result or {"status": "added", "title": "The Matrix"},
    )
    monkeypatch.setattr(
        "mdblist.services.sonarr_add_series",
        lambda *a, **k: sonarr_result or {"status": "added", "title": "Severance"},
    )


@pytest.mark.django_db
def test_import_list_adds_movies_via_radarr(httpx_mock, monkeypatch):
    _mock_arr(monkeypatch)
    httpx_mock.add_response(
        url="https://api.mdblist.com/lists/bear/my-list/items?apikey=test-mdblist-key&limit=100",
        json=MOVIES_PAGE,
    )
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/movie",
        json=[],
    )

    result = services.import_list(LIST_URL)

    assert result["radarr"]["added"] == ["The Matrix"]
    assert result["sonarr"] is None
    assert result["dryRun"] is False
    assert "Radarr: 1 added" in result["message"]


@pytest.mark.django_db
def test_import_list_writes_sync_log_row(httpx_mock, monkeypatch):
    _mock_arr(monkeypatch)
    httpx_mock.add_response(
        url="https://api.mdblist.com/lists/bear/my-list/items?apikey=test-mdblist-key&limit=100",
        json=MOVIES_PAGE,
    )
    httpx_mock.add_response(url="http://radarr:7878/api/v3/movie", json=[])

    services.import_list(LIST_URL)

    assert MDBListSyncLog.objects.count() == 1
    row = MDBListSyncLog.objects.first()
    assert row.list_url == LIST_URL
    assert row.radarr_added == 1
    assert row.radarr_already == 0
    assert row.radarr_failed == 0
    assert row.sonarr_added == 0


@pytest.mark.django_db
def test_import_list_handles_movies_and_shows(httpx_mock, monkeypatch):
    _mock_arr(monkeypatch)
    httpx_mock.add_response(
        url="https://api.mdblist.com/lists/bear/my-list/items?apikey=test-mdblist-key&limit=100",
        json=MIXED_PAGE,
    )
    httpx_mock.add_response(url="http://radarr:7878/api/v3/movie", json=[])
    httpx_mock.add_response(url="http://sonarr:8989/api/v3/series", json=[])

    result = services.import_list(LIST_URL)

    assert result["radarr"]["added"] == ["The Matrix"]
    assert result["sonarr"]["added"] == ["Severance"]


@pytest.mark.django_db
def test_import_list_paginates_via_cursor(httpx_mock, monkeypatch):
    _mock_arr(monkeypatch)
    httpx_mock.add_response(
        url="https://api.mdblist.com/lists/bear/my-list/items?apikey=test-mdblist-key&limit=100",
        json={
            "movies": [{"title": "Page One", "ids": {"tmdb": 1}}],
            "shows": [],
            "pagination": {"has_more": True, "next_cursor": "abc"},
        },
    )
    httpx_mock.add_response(
        url="https://api.mdblist.com/lists/bear/my-list/items?apikey=test-mdblist-key&limit=100&cursor=abc",
        json={
            "movies": [{"title": "Page Two", "ids": {"tmdb": 2}}],
            "shows": [],
            "pagination": {"has_more": False, "next_cursor": None},
        },
    )
    httpx_mock.add_response(url="http://radarr:7878/api/v3/movie", json=[])
    calls = []
    monkeypatch.setattr(
        "mdblist.services.radarr_add_movie",
        lambda *a, **k: (calls.append(a[1]), {"status": "added", "title": f"movie-{a[1]}"})[1],
    )

    services.import_list(LIST_URL)

    assert calls == [1, 2]


@pytest.mark.django_db
def test_import_list_rejects_unrecognized_url():
    with pytest.raises(ServiceError) as exc_info:
        services.import_list("https://example.com/not-mdblist")
    assert exc_info.value.status_code == 400


@pytest.mark.django_db
def test_import_list_requires_mdblist_key(monkeypatch):
    monkeypatch.delenv("MDBLIST_KEY", raising=False)
    with pytest.raises(ServiceError) as exc_info:
        services.import_list(LIST_URL)
    assert exc_info.value.status_code == 500


@pytest.mark.django_db
def test_import_list_no_items_found_is_404(httpx_mock):
    httpx_mock.add_response(
        url="https://api.mdblist.com/lists/bear/my-list/items?apikey=test-mdblist-key&limit=100",
        json={"movies": [], "shows": [], "pagination": {"has_more": False, "next_cursor": None}},
    )
    with pytest.raises(ServiceError) as exc_info:
        services.import_list(LIST_URL)
    assert exc_info.value.status_code == 404


@pytest.mark.django_db
def test_get_history_returns_recent_runs_newest_first():
    MDBListSyncLog.objects.create(list_url="https://mdblist.com/lists/a/1/", radarr_added=1)
    MDBListSyncLog.objects.create(list_url="https://mdblist.com/lists/a/2/", sonarr_added=2)

    result = services.get_history()

    assert len(result["runs"]) == 2
    assert result["runs"][0]["listUrl"] == "https://mdblist.com/lists/a/2/"
    assert result["runs"][0]["sonarrAdded"] == 2
    assert result["runs"][1]["radarrAdded"] == 1
    assert "2 recent sync run" in result["message"]


@pytest.mark.django_db
def test_track_creates_row():
    result = services.track("https://mdblist.com/lists/bear/watch/", label="Watch")

    assert result["id"] is not None
    row = MDBListTrackedList.objects.get(url="https://mdblist.com/lists/bear/watch/")
    assert row.label == "Watch"
    assert row.app == "radarr"
    assert row.sonarr_app == "sonarr"


@pytest.mark.django_db
def test_track_duplicate_raises_409():
    MDBListTrackedList.objects.create(url="https://mdblist.com/lists/bear/watch/")
    with pytest.raises(ServiceError) as exc_info:
        services.track("https://mdblist.com/lists/bear/watch/")
    assert exc_info.value.status_code == 409


@pytest.mark.django_db
def test_track_rejects_unknown_app():
    with pytest.raises(ServiceError) as exc_info:
        services.track("https://mdblist.com/lists/bear/watch/", app="not-radarr")
    assert exc_info.value.status_code == 400


@pytest.mark.django_db
def test_untrack_deletes_row():
    MDBListTrackedList.objects.create(url="https://mdblist.com/lists/bear/watch/")
    services.untrack("https://mdblist.com/lists/bear/watch/")
    assert MDBListTrackedList.objects.count() == 0


@pytest.mark.django_db
def test_untrack_unknown_raises_404():
    with pytest.raises(ServiceError) as exc_info:
        services.untrack("https://mdblist.com/lists/nope/nope/")
    assert exc_info.value.status_code == 404


@pytest.mark.django_db
def test_list_tracked_returns_rows():
    MDBListTrackedList.objects.create(url="https://mdblist.com/lists/bear/a/", label="A")
    MDBListTrackedList.objects.create(url="https://mdblist.com/lists/bear/b/")

    result = services.list_tracked()

    assert result["message"] == "2 tracked list(s)."
    urls = {row["url"] for row in result["lists"]}
    assert urls == {"https://mdblist.com/lists/bear/a/", "https://mdblist.com/lists/bear/b/"}


@pytest.mark.django_db
def test_sync_tick_imports_every_tracked_row(monkeypatch):
    MDBListTrackedList.objects.create(url="https://mdblist.com/lists/bear/a/")
    MDBListTrackedList.objects.create(url="https://mdblist.com/lists/bear/b/")

    calls = []

    def fake_run_import(url, **kwargs):
        calls.append(url)
        return {"radarr": {"added": ["Movie"], "alreadyCount": 0, "failed": []}, "sonarr": None}

    monkeypatch.setattr("mdblist.services._run_import", fake_run_import)

    result = services.sync_tick()

    assert sorted(calls) == ["https://mdblist.com/lists/bear/a/", "https://mdblist.com/lists/bear/b/"]
    assert result["message"] == "Synced 2 tracked list(s)."
    assert MDBListSyncLog.objects.count() == 2
    for row in MDBListTrackedList.objects.all():
        assert row.last_synced_at is not None


@pytest.mark.django_db
def test_sync_tick_continues_after_a_row_errors(monkeypatch):
    MDBListTrackedList.objects.create(url="https://mdblist.com/lists/bear/broken/")
    MDBListTrackedList.objects.create(url="https://mdblist.com/lists/bear/ok/")

    def fake_run_import(url, **kwargs):
        if "broken" in url:
            raise ServiceError("MDBList lookup failed: boom")
        return {"radarr": {"added": ["Movie"], "alreadyCount": 0, "failed": []}, "sonarr": None}

    monkeypatch.setattr("mdblist.services._run_import", fake_run_import)

    result = services.sync_tick()

    by_url = {r["url"]: r for r in result["results"]}
    assert "error" in by_url["https://mdblist.com/lists/bear/broken/"]
    assert "error" not in by_url["https://mdblist.com/lists/bear/ok/"]
    assert by_url["https://mdblist.com/lists/bear/ok/"]["radarrAdded"] == ["Movie"]
    # The broken row's log gets error_detail; the ok row gets counts.
    logs = {log.list_url: log for log in MDBListSyncLog.objects.all()}
    assert logs["https://mdblist.com/lists/bear/broken/"].error_detail == "MDBList lookup failed: boom"
    assert logs["https://mdblist.com/lists/bear/ok/"].radarr_added == 1
    # last_synced_at only advances for the row that actually synced.
    broken_row = MDBListTrackedList.objects.get(url="https://mdblist.com/lists/bear/broken/")
    ok_row = MDBListTrackedList.objects.get(url="https://mdblist.com/lists/bear/ok/")
    assert broken_row.last_synced_at is None
    assert ok_row.last_synced_at is not None

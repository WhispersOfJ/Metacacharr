"""Tests for letterboxd/services.py - ported from
control-panel/services/letterboxd/router.py (+ sync.py folded in), covering
add_from_url, add_from_list (rating->quality-profile map, tags->Radarr-tags,
TV-crossover-to-Sonarr branches each independently), get_history, track,
untrack, list_tracked, sync_tick."""
import pytest

from core.api_base import ServiceError
from core.models import LetterboxdSyncLog, LetterboxdTmdbCache, LetterboxdTrackedList
from letterboxd import services

FILM_URL = "https://letterboxd.com/film/oppenheimer/"
LIST_URL = "https://letterboxd.com/bear/watchlist/"

FILM_PAGE_WITH_TMDB = '<a href="https://www.themoviedb.org/movie/872585">TMDb</a>'
LIST_PAGE_NO_MORE = '<li data-item-slug="oppenheimer"></li>'


# ---------------------------------------------------------------------------
# add_from_url
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_add_from_url_rejects_non_film_url():
    with pytest.raises(ServiceError) as exc_info:
        services.add_from_url("https://letterboxd.com/bear/watchlist/")
    assert exc_info.value.status_code == 400


@pytest.mark.django_db
def test_add_from_url_no_tmdb_link_is_404(httpx_mock):
    httpx_mock.add_response(url=FILM_URL, text="<html>no tmdb link</html>")
    with pytest.raises(ServiceError) as exc_info:
        services.add_from_url(FILM_URL)
    assert exc_info.value.status_code == 404


@pytest.mark.django_db
def test_add_from_url_already_in_radarr(httpx_mock):
    httpx_mock.add_response(url=FILM_URL, text=FILM_PAGE_WITH_TMDB)
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/movie?tmdbId=872585",
        json=[{"title": "Oppenheimer", "year": 2023, "id": 42}],
    )

    result = services.add_from_url(FILM_URL)

    assert result["alreadyAdded"] is True
    assert result["radarrId"] == 42
    assert result["tmdbId"] == 872585


@pytest.mark.django_db
def test_add_from_url_dry_run_does_not_post(httpx_mock):
    httpx_mock.add_response(url=FILM_URL, text=FILM_PAGE_WITH_TMDB)
    httpx_mock.add_response(url="http://radarr:7878/api/v3/movie?tmdbId=872585", json=[])
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/movie/lookup/tmdb?tmdbId=872585",
        json={"title": "Oppenheimer", "year": 2023},
    )
    httpx_mock.add_response(url="http://radarr:7878/api/v3/rootfolder", json=[{"path": "/data/movies"}])
    httpx_mock.add_response(url="http://radarr:7878/api/v3/qualityprofile", json=[{"id": 1, "name": "Unlimited"}])

    result = services.add_from_url(FILM_URL, dry_run=True)

    assert result["dryRun"] is True
    assert result["tmdbId"] == 872585


@pytest.mark.django_db
def test_add_from_url_adds_new_movie(httpx_mock):
    httpx_mock.add_response(url=FILM_URL, text=FILM_PAGE_WITH_TMDB)
    httpx_mock.add_response(url="http://radarr:7878/api/v3/movie?tmdbId=872585", json=[])
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/movie/lookup/tmdb?tmdbId=872585",
        json={"title": "Oppenheimer", "year": 2023},
    )
    httpx_mock.add_response(url="http://radarr:7878/api/v3/rootfolder", json=[{"path": "/data/movies"}])
    httpx_mock.add_response(url="http://radarr:7878/api/v3/qualityprofile", json=[{"id": 1, "name": "Unlimited"}])
    httpx_mock.add_response(
        method="POST", url="http://radarr:7878/api/v3/movie",
        json={"title": "Oppenheimer", "year": 2023, "id": 99},
    )

    result = services.add_from_url(FILM_URL)

    assert result["radarrId"] == 99
    assert result["tmdbId"] == 872585


@pytest.mark.django_db
def test_add_from_url_no_radarr_match_is_404(httpx_mock):
    httpx_mock.add_response(url=FILM_URL, text=FILM_PAGE_WITH_TMDB)
    httpx_mock.add_response(url="http://radarr:7878/api/v3/movie?tmdbId=872585", json=[])
    httpx_mock.add_response(url="http://radarr:7878/api/v3/movie/lookup/tmdb?tmdbId=872585", json={})

    with pytest.raises(ServiceError) as exc_info:
        services.add_from_url(FILM_URL)
    assert exc_info.value.status_code == 404


@pytest.mark.django_db
def test_add_from_url_rejects_unknown_app():
    with pytest.raises(ServiceError) as exc_info:
        services.add_from_url(FILM_URL, app="not-radarr")
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# add_from_list (+ underlying _run_list_sync)
# ---------------------------------------------------------------------------

def _mock_list_flow(httpx_mock, monkeypatch, *, tmdb_ids=(872585,), unmatched=None,
                     existing_tmdb_ids=None, radarr_add_result=None):
    unmatched = unmatched if unmatched is not None else []
    existing_tmdb_ids = existing_tmdb_ids if existing_tmdb_ids is not None else set()
    httpx_mock.add_response(url=LIST_URL, text=LIST_PAGE_NO_MORE)
    monkeypatch.setattr("letterboxd.services.resolve_tmdb_ids", lambda slugs: (list(tmdb_ids), list(unmatched)))
    httpx_mock.add_response(url="http://radarr:7878/api/v3/movie", json=[{"tmdbId": t} for t in existing_tmdb_ids])
    httpx_mock.add_response(url="http://radarr:7878/api/v3/rootfolder", json=[{"path": "/data/movies"}])
    httpx_mock.add_response(url="http://radarr:7878/api/v3/qualityprofile", json=[{"id": 1, "name": "Unlimited"}])
    monkeypatch.setattr(
        "letterboxd.services.radarr_add_movie",
        lambda *a, **k: radarr_add_result or {"status": "added", "title": "Oppenheimer"},
    )


@pytest.mark.django_db
def test_add_from_list_rejects_disallowed_url():
    with pytest.raises(ServiceError) as exc_info:
        services.add_from_list("https://letterboxd.com/bear/list/my-list/by/rating/")
    assert exc_info.value.status_code == 400


@pytest.mark.django_db
def test_add_from_list_rejects_unrecognized_url():
    with pytest.raises(ServiceError) as exc_info:
        services.add_from_list("https://letterboxd.com/")
    assert exc_info.value.status_code == 400


@pytest.mark.django_db
def test_add_from_list_no_films_found_is_404(httpx_mock):
    httpx_mock.add_response(url=LIST_URL, text="<html>no film grid here (client-rendered)</html>")
    with pytest.raises(ServiceError) as exc_info:
        services.add_from_list(LIST_URL)
    assert exc_info.value.status_code == 404


@pytest.mark.django_db
def test_add_from_list_adds_movies_and_records_sync_log(httpx_mock, monkeypatch):
    _mock_list_flow(httpx_mock, monkeypatch)

    result = services.add_from_list(LIST_URL)

    assert result["added"] == ["Oppenheimer"]
    assert result["dryRun"] is False
    assert LetterboxdSyncLog.objects.count() == 1
    row = LetterboxdSyncLog.objects.first()
    assert row.list_url == LIST_URL
    assert row.added == 1
    assert row.matched == 1


@pytest.mark.django_db
def test_add_from_list_rating_quality_map_selects_profile_by_rating(httpx_mock, monkeypatch):
    httpx_mock.add_response(
        url=LIST_URL,
        text=(
            '<li data-item-slug="oppenheimer">'
            '<span class="rating -micro -darker rated-10"></span>'
            '</li>'
        ),
    )
    monkeypatch.setattr("letterboxd.services.resolve_tmdb_ids", lambda slugs: ([872585], []))
    LetterboxdTmdbCache.objects.create(slug="oppenheimer", tmdb_id=872585, media_type="movie")
    httpx_mock.add_response(url="http://radarr:7878/api/v3/movie", json=[])
    httpx_mock.add_response(url="http://radarr:7878/api/v3/rootfolder", json=[{"path": "/data/movies"}])
    # Queried twice: once by radarr_root_folder_and_profile, once by
    # radarr_quality_profile_id_by_name (rating_quality_map lookup) - each
    # pytest_httpx response is consumed on first match, so register it twice.
    profiles = [{"id": 1, "name": "Unlimited"}, {"id": 2, "name": "4K"}]
    httpx_mock.add_response(url="http://radarr:7878/api/v3/qualityprofile", json=profiles)
    httpx_mock.add_response(url="http://radarr:7878/api/v3/qualityprofile", json=profiles)

    captured = {}

    def fake_add_movie(cfg, tmdb_id, monitored, search, root_folder_path, quality_profile_id,
                        existing_tmdb_ids, dry_run=False, tag_ids=None):
        captured["quality_profile_id"] = quality_profile_id
        return {"status": "added", "title": "Oppenheimer"}

    monkeypatch.setattr("letterboxd.services.radarr_add_movie", fake_add_movie)

    services.add_from_list(LIST_URL, rating_quality_map={"10": "4K"})

    assert captured["quality_profile_id"] == 2


@pytest.mark.django_db
def test_add_from_list_tags_as_radarr_tags_ensures_tags(httpx_mock, monkeypatch):
    _mock_list_flow(httpx_mock, monkeypatch)
    LetterboxdTmdbCache.objects.create(slug="oppenheimer", tmdb_id=872585, media_type="movie")
    monkeypatch.setattr(
        "letterboxd.services.fetch_page_or_none",
        lambda url: '<ul class="tags"><li><a href="/bear/tag/press-screening/films/"></a></li></ul>',
    )

    captured = {}

    def fake_ensure_tags(cfg, tag_names):
        captured["tag_names"] = tag_names
        return [7]

    monkeypatch.setattr("letterboxd.services.radarr_ensure_tags", fake_ensure_tags)

    def fake_add_movie(cfg, tmdb_id, monitored, search, root_folder_path, quality_profile_id,
                        existing_tmdb_ids, dry_run=False, tag_ids=None):
        captured["tag_ids"] = tag_ids
        return {"status": "added", "title": "Oppenheimer"}

    monkeypatch.setattr("letterboxd.services.radarr_add_movie", fake_add_movie)

    services.add_from_list(LIST_URL, tags_as_radarr_tags=True)

    assert captured["tag_names"] == ["press-screening"]
    assert captured["tag_ids"] == [7]


@pytest.mark.django_db
def test_add_from_list_sonarr_crossover_adds_tv_match(httpx_mock, monkeypatch):
    httpx_mock.add_response(url=LIST_URL, text=LIST_PAGE_NO_MORE)
    monkeypatch.setattr(
        "letterboxd.services.resolve_tmdb_ids", lambda slugs: ([], ["oppenheimer"]),
    )
    monkeypatch.setattr(
        "letterboxd.services.resolve_tv_crossovers",
        lambda unmatched: ([{"slug": "oppenheimer", "title": "Chernobyl", "year": 2019, "tvdb_id": 361744}], []),
    )
    httpx_mock.add_response(url="http://sonarr:8989/api/v3/series", json=[])
    httpx_mock.add_response(url="http://sonarr:8989/api/v3/rootfolder", json=[{"path": "/data/shows"}])
    httpx_mock.add_response(url="http://sonarr:8989/api/v3/qualityprofile", json=[{"id": 1, "name": "Any"}])
    httpx_mock.add_response(url="http://radarr:7878/api/v3/movie", json=[])
    httpx_mock.add_response(url="http://radarr:7878/api/v3/rootfolder", json=[{"path": "/data/movies"}])
    httpx_mock.add_response(url="http://radarr:7878/api/v3/qualityprofile", json=[{"id": 1, "name": "Unlimited"}])
    monkeypatch.setattr(
        "letterboxd.services.sonarr_add_series",
        lambda *a, **k: {"status": "added", "title": "Chernobyl"},
    )

    result = services.add_from_list(LIST_URL, sonarr_crossover=True)

    assert result["tvCrossoverAdded"] == ["Chernobyl"]
    assert result["tvCrossoverCount"] == 1
    assert "TV crossover" in result["message"]


@pytest.mark.django_db
def test_add_from_list_dry_run_summary(httpx_mock, monkeypatch):
    _mock_list_flow(httpx_mock, monkeypatch)

    result = services.add_from_list(LIST_URL, dry_run=True)

    assert result["dryRun"] is True
    assert "would be added" in result["message"]


# ---------------------------------------------------------------------------
# get_history
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_get_history_returns_recent_runs_newest_first():
    LetterboxdSyncLog.objects.create(list_url="https://letterboxd.com/a/watchlist/", added=1, matched=1)
    LetterboxdSyncLog.objects.create(list_url="https://letterboxd.com/b/watchlist/", added=2, matched=2)

    result = services.get_history()

    assert len(result["runs"]) == 2
    assert result["runs"][0]["listUrl"] == "https://letterboxd.com/b/watchlist/"
    assert result["runs"][0]["added"] == 2
    assert "2 recent sync run" in result["message"]


# ---------------------------------------------------------------------------
# track / untrack / list_tracked
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_track_creates_row():
    result = services.track(LIST_URL, label="Watchlist")

    assert result["id"] is not None
    row = LetterboxdTrackedList.objects.get(url=LIST_URL)
    assert row.label == "Watchlist"
    assert row.app == "radarr"
    assert row.sonarr_app == "sonarr"


@pytest.mark.django_db
def test_track_serializes_rating_quality_map_as_json():
    services.track(LIST_URL, rating_quality_map={"10": "4K"})

    row = LetterboxdTrackedList.objects.get(url=LIST_URL)
    assert row.rating_quality_map_json == '{"10": "4K"}'


@pytest.mark.django_db
def test_track_duplicate_raises_409():
    LetterboxdTrackedList.objects.create(url=LIST_URL)
    with pytest.raises(ServiceError) as exc_info:
        services.track(LIST_URL)
    assert exc_info.value.status_code == 409


@pytest.mark.django_db
def test_track_rejects_unknown_radarr_app():
    with pytest.raises(ServiceError) as exc_info:
        services.track(LIST_URL, app="not-radarr")
    assert exc_info.value.status_code == 400


@pytest.mark.django_db
def test_track_rejects_unknown_sonarr_app():
    with pytest.raises(ServiceError) as exc_info:
        services.track(LIST_URL, sonarr_app="not-sonarr")
    assert exc_info.value.status_code == 400


@pytest.mark.django_db
def test_untrack_deletes_row():
    LetterboxdTrackedList.objects.create(url=LIST_URL)
    services.untrack(LIST_URL)
    assert LetterboxdTrackedList.objects.count() == 0


@pytest.mark.django_db
def test_untrack_unknown_raises_404():
    with pytest.raises(ServiceError) as exc_info:
        services.untrack("https://letterboxd.com/nope/watchlist/")
    assert exc_info.value.status_code == 404


@pytest.mark.django_db
def test_list_tracked_returns_rows():
    LetterboxdTrackedList.objects.create(url="https://letterboxd.com/a/watchlist/", label="A")
    LetterboxdTrackedList.objects.create(url="https://letterboxd.com/b/watchlist/")

    result = services.list_tracked()

    assert result["message"] == "2 tracked list(s)."
    urls = {row["url"] for row in result["lists"]}
    assert urls == {"https://letterboxd.com/a/watchlist/", "https://letterboxd.com/b/watchlist/"}


# ---------------------------------------------------------------------------
# sync_tick
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sync_tick_runs_every_tracked_row(monkeypatch):
    LetterboxdTrackedList.objects.create(url="https://letterboxd.com/a/watchlist/")
    LetterboxdTrackedList.objects.create(url="https://letterboxd.com/b/watchlist/")

    calls = []

    def fake_run_list_sync(url, **kwargs):
        calls.append(url)
        return {"added": ["Movie"], "already": [], "failed": [], "unmatched": [],
                "tvAdded": [], "tvAlready": [], "tvFailed": [], "matched": 1}

    monkeypatch.setattr("letterboxd.services._run_list_sync", fake_run_list_sync)

    result = services.sync_tick()

    assert sorted(calls) == ["https://letterboxd.com/a/watchlist/", "https://letterboxd.com/b/watchlist/"]
    assert result["message"] == "Synced 2 tracked list(s)."
    assert LetterboxdSyncLog.objects.count() == 2
    for row in LetterboxdTrackedList.objects.all():
        assert row.last_synced_at is not None


@pytest.mark.django_db
def test_sync_tick_continues_after_a_row_errors(monkeypatch):
    LetterboxdTrackedList.objects.create(url="https://letterboxd.com/broken/watchlist/")
    LetterboxdTrackedList.objects.create(url="https://letterboxd.com/ok/watchlist/")

    def fake_run_list_sync(url, **kwargs):
        if "broken" in url:
            raise ServiceError("scrape failed: boom")
        return {"added": ["Movie"], "already": [], "failed": [], "unmatched": [],
                "tvAdded": [], "tvAlready": [], "tvFailed": [], "matched": 1}

    monkeypatch.setattr("letterboxd.services._run_list_sync", fake_run_list_sync)

    result = services.sync_tick()

    by_url = {r["url"]: r for r in result["results"]}
    assert by_url["https://letterboxd.com/broken/watchlist/"]["failed"] == ["scrape failed: boom"]
    assert by_url["https://letterboxd.com/ok/watchlist/"]["added"] == ["Movie"]
    logs = {log.list_url: log for log in LetterboxdSyncLog.objects.all()}
    assert logs["https://letterboxd.com/broken/watchlist/"].error_detail == "scrape failed: boom"
    assert logs["https://letterboxd.com/ok/watchlist/"].added == 1
    broken_row = LetterboxdTrackedList.objects.get(url="https://letterboxd.com/broken/watchlist/")
    ok_row = LetterboxdTrackedList.objects.get(url="https://letterboxd.com/ok/watchlist/")
    assert broken_row.last_synced_at is None
    assert ok_row.last_synced_at is not None


@pytest.mark.django_db
def test_sync_tick_deserializes_rating_quality_map(monkeypatch):
    LetterboxdTrackedList.objects.create(
        url=LIST_URL, rating_quality_map_json='{"10": "4K"}',
    )

    captured = {}

    def fake_run_list_sync(url, **kwargs):
        captured["rating_quality_map"] = kwargs.get("rating_quality_map")
        return {"added": [], "already": [], "failed": [], "unmatched": [],
                "tvAdded": [], "tvAlready": [], "tvFailed": [], "matched": 0}

    monkeypatch.setattr("letterboxd.services._run_list_sync", fake_run_list_sync)

    services.sync_tick()

    assert captured["rating_quality_map"] == {"10": "4K"}


@pytest.mark.django_db
def test_sync_tick_sonarr_crossover_always_disabled(monkeypatch):
    """sync_tick always calls _run_list_sync with sonarr_crossover=False -
    the scheduled sync never does the crossover pass, matching the real
    FastAPI-era letterboxd_sync_tick route."""
    LetterboxdTrackedList.objects.create(url=LIST_URL)

    captured = {}

    def fake_run_list_sync(url, **kwargs):
        captured["sonarr_crossover"] = kwargs.get("sonarr_crossover")
        return {"added": [], "already": [], "failed": [], "unmatched": [],
                "tvAdded": [], "tvAlready": [], "tvFailed": [], "matched": 0}

    monkeypatch.setattr("letterboxd.services._run_list_sync", fake_run_list_sync)

    services.sync_tick()

    assert captured["sonarr_crossover"] is False

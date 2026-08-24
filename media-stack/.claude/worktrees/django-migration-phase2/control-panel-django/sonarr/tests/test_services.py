import httpx
import pytest

from core.api_base import ServiceError
from sonarr.services import fix_monitored_episodes

SERIES_URL = "http://sonarr:8989/api/v3/series"


def _episode_url(series_id: int) -> str:
    return f"http://sonarr:8989/api/v3/episode?seriesId={series_id}"


def test_fix_monitored_episodes_excludes_season_zero_and_unmonitored_series(httpx_mock):
    """Only unmonitored episodes under monitored series, non-special seasons, get fixed."""
    httpx_mock.add_response(
        url=SERIES_URL,
        json=[
            {"id": 1, "monitored": True},
            {"id": 2, "monitored": False},  # unmonitored series - never touched
        ],
    )
    httpx_mock.add_response(
        url=_episode_url(1),
        json=[
            {"id": 101, "seasonNumber": 1, "monitored": False},  # to fix
            {"id": 102, "seasonNumber": 1, "monitored": True},  # already monitored
            {"id": 103, "seasonNumber": 0, "monitored": False},  # special - excluded
        ],
    )
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/episode/monitor",
        method="PUT",
        json={},
        match_json={"episodeIds": [101], "monitored": True},
    )

    result = fix_monitored_episodes()

    assert result == {"fixed": 1, "monitored_series": 1}


def test_fix_monitored_episodes_chunks_put_calls_at_200(httpx_mock):
    """250 episode ids to fix span 2 PUT calls: one of 200, one of 50."""
    episode_ids = list(range(1000, 1250))
    httpx_mock.add_response(url=SERIES_URL, json=[{"id": 1, "monitored": True}])
    httpx_mock.add_response(
        url=_episode_url(1),
        json=[{"id": eid, "seasonNumber": 1, "monitored": False} for eid in episode_ids],
    )
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/episode/monitor",
        method="PUT",
        json={},
        match_json={"episodeIds": episode_ids[:200], "monitored": True},
    )
    httpx_mock.add_response(
        url="http://sonarr:8989/api/v3/episode/monitor",
        method="PUT",
        json={},
        match_json={"episodeIds": episode_ids[200:], "monitored": True},
    )

    result = fix_monitored_episodes()

    assert result == {"fixed": 250, "monitored_series": 1}
    put_requests = [r for r in httpx_mock.get_requests() if r.method == "PUT"]
    assert len(put_requests) == 2


def test_fix_monitored_episodes_no_series_monitored(httpx_mock):
    """No monitored series - zero episodes fixed, no episode/PUT calls made."""
    httpx_mock.add_response(url=SERIES_URL, json=[{"id": 1, "monitored": False}])

    result = fix_monitored_episodes()

    assert result == {"fixed": 0, "monitored_series": 0}


def test_fix_monitored_episodes_series_lookup_http_error(httpx_mock):
    """HTTP error on series lookup raises ServiceError."""
    httpx_mock.add_exception(httpx.ConnectError("connection refused"), url=SERIES_URL)

    with pytest.raises(ServiceError):
        fix_monitored_episodes()


def test_fix_monitored_episodes_episode_lookup_http_error(httpx_mock):
    """HTTP error on episode lookup for a series raises ServiceError."""
    httpx_mock.add_response(url=SERIES_URL, json=[{"id": 1, "monitored": True}])
    httpx_mock.add_exception(httpx.ConnectError("connection refused"), url=_episode_url(1))

    with pytest.raises(ServiceError):
        fix_monitored_episodes()


def test_fix_monitored_episodes_put_http_error(httpx_mock):
    """HTTP error on the monitor PUT call raises ServiceError."""
    httpx_mock.add_response(url=SERIES_URL, json=[{"id": 1, "monitored": True}])
    httpx_mock.add_response(
        url=_episode_url(1),
        json=[{"id": 101, "seasonNumber": 1, "monitored": False}],
    )
    httpx_mock.add_exception(
        httpx.ConnectError("connection refused"),
        url="http://sonarr:8989/api/v3/episode/monitor",
        method="PUT",
    )

    with pytest.raises(ServiceError):
        fix_monitored_episodes()

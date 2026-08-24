import httpx
import pytest

from core.api_base import ServiceError
from radarr.services import exclude_movie


def test_exclude_movie_success(httpx_mock):
    """Exclude a movie from Radarr import lists."""
    # Mock get_movie_or_episode
    movie_data = {
        "id": 123,
        "title": "The Matrix",
        "year": 1999,
        "tmdbId": 603,
    }

    # Mock the Radarr API endpoint
    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/exclusions",
        json={"id": 1},
        status_code=201,
    )

    # We'll need to patch get_movie_or_episode in the test
    with pytest.importorskip("unittest.mock").patch(
        "radarr.services.get_movie_or_episode", return_value=movie_data
    ):
        result = exclude_movie(123)

    assert result == {"movieId": 123}


def test_exclude_movie_not_found(httpx_mock):
    """Exclude returns 404 when movie not found in Radarr."""
    with pytest.importorskip("unittest.mock").patch(
        "radarr.services.get_movie_or_episode", return_value=None
    ):
        with pytest.raises(ServiceError) as exc_info:
            exclude_movie(999)
        assert exc_info.value.status_code == 404


def test_exclude_movie_http_error(httpx_mock):
    """HTTP errors from Radarr raise ServiceError."""
    movie_data = {"id": 123, "title": "Test", "year": 2020, "tmdbId": 123}

    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    with pytest.importorskip("unittest.mock").patch(
        "radarr.services.get_movie_or_episode", return_value=movie_data
    ):
        with pytest.raises(ServiceError):
            exclude_movie(123)


def test_exclude_movie_idempotent_400(httpx_mock):
    """400 response (already excluded) treated as success (idempotent)."""
    movie_data = {"id": 123, "title": "The Matrix", "year": 1999, "tmdbId": 603}

    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/exclusions",
        json={"message": "Already excluded"},
        status_code=400,
    )

    with pytest.importorskip("unittest.mock").patch(
        "radarr.services.get_movie_or_episode", return_value=movie_data
    ):
        result = exclude_movie(123)

    assert result == {"movieId": 123}


def test_exclude_movie_idempotent_409(httpx_mock):
    """409 response (conflict/already excluded) treated as success (idempotent)."""
    movie_data = {"id": 123, "title": "The Matrix", "year": 1999, "tmdbId": 603}

    httpx_mock.add_response(
        url="http://radarr:7878/api/v3/exclusions",
        json={"message": "Conflict"},
        status_code=409,
    )

    with pytest.importorskip("unittest.mock").patch(
        "radarr.services.get_movie_or_episode", return_value=movie_data
    ):
        result = exclude_movie(123)

    assert result == {"movieId": 123}

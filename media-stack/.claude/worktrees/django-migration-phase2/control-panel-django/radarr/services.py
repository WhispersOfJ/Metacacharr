"""Radarr-only service for excluding movies from import lists.
Ported from control-panel/services/radarr/router.py.
"""
import httpx

from core.api_base import ServiceError
from core.arr_client import ARR_APPS, get_movie_or_episode


def exclude_movie(movie_id: int) -> dict:
    """Exclude a movie from Radarr import lists - prevents re-monitoring
    on periodic syncs. A durable fix for movies that keep being re-added
    by import lists (plain unmonitor only holds until the next sync).
    Idempotent: 400/409 (already excluded) treated as success."""
    cfg = ARR_APPS["radarr"]
    movie = get_movie_or_episode("radarr", cfg, movie_id)
    if movie is None:
        raise ServiceError(f"Movie {movie_id} not found in Radarr", status=404)
    try:
        response = httpx.post(
            f"{cfg['url']}/api/{cfg['api']}/exclusions",
            headers={"X-Api-Key": cfg["key"]},
            json={
                "tmdbId": movie.get("tmdbId"),
                "movieTitle": movie.get("title"),
                "movieYear": movie.get("year"),
            },
            timeout=20,
        )
        # 400/409 from Radarr means already excluded - treat as success (idempotent)
        if response.status_code not in (200, 201, 400, 409):
            response.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"Exclusion failed: {e}") from e
    return {"movieId": movie_id}

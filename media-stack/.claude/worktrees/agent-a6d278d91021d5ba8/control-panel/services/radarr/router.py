"""Radarr-only routes with no Sonarr equivalent and no Letterboxd
involvement - the Letterboxd-driven routes that used to live here moved to
services/letterboxd/router.py (2026-08-06) once Letterboxd became a
first-class integration spanning both Radarr and Sonarr.
"""
import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.arr_client import ARR_APPS, get_movie_or_episode
from core.responses import fail, ok
from core.security import current_user

router = APIRouter(tags=["radarr"])

SERVICE_META = {"label": "Radarr", "health_check": None}


class ExcludeRequest(BaseModel):
    movieId: int


@router.post("/api/arr/radarr/exclude")
def arr_radarr_exclude(body: ExcludeRequest, _=Depends(current_user)):
    """The durable fix for movies that keep getting silently re-monitored by
    an import list's periodic sync - plain unmonitor only holds until the
    next sync. No Sonarr equivalent exists."""
    cfg = ARR_APPS["radarr"]
    movie = get_movie_or_episode("radarr", cfg, body.movieId)
    if movie is None:
        fail(f"Movie {body.movieId} not found in Radarr.", status_code=404)
    try:
        r = httpx.post(f"{cfg['url']}/api/{cfg['api']}/exclusions",
                        json={"tmdbId": movie.get("tmdbId"), "movieTitle": movie.get("title"), "movieYear": movie.get("year")},
                        headers={"X-Api-Key": cfg["key"]}, timeout=20)
        if r.status_code not in (200, 201, 400, 409):
            r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Exclusion failed: {e}")
    return ok(f"Excluded \"{movie.get('title')}\" from Radarr import lists.", movieId=body.movieId)

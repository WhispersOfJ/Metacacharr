"""Seerr media-requests service, ported byte-identical (behavior-wise) from
the FastAPI-era control-panel/services/seerr/router.py.
"""
import json
import os

import httpx

from core.api_base import ServiceError
from core.host_paths import HOST_CONFIG_DIR

SEERR_URL = "http://seerr:5055"


def _seerr_key() -> str | None:
    """Seerr generates its own key on first setup and only stores it in
    settings.json, never in .env."""
    path = os.path.join(HOST_CONFIG_DIR, "seerr", "settings.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f).get("main", {}).get("apiKey")
    except (ValueError, OSError):
        return None


def list_requests(status: str = "pending") -> list[dict]:
    """Pending (or any-status) media requests sitting in Seerr - the queue
    a user expects Radarr/Sonarr to eventually pick up automatically, so
    this is mostly useful for confirming a request actually landed there
    before chasing why it's not showing up downstream."""
    key = _seerr_key()
    if not key:
        raise ServiceError(
            "Could not read Seerr's API key from config/seerr/settings.json.", status=503
        )
    try:
        response = httpx.get(
            f"{SEERR_URL}/api/v1/request",
            params={"filter": status, "take": 25},
            headers={"X-Api-Key": key},
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ServiceError(f"Seerr lookup failed: {exc}") from exc
    data = response.json()
    return [
        {
            # Seerr's own /api/v1/request response has no title field on its
            # embedded media object at all (confirmed live) - externalServiceSlug
            # (Radarr/Sonarr's own URL-safe slug, e.g. "the-ambiguously-gay-duo")
            # is the only human-readable thing available without a second
            # per-item API call to /api/v1/media/{id} or TMDB directly.
            "title": (req.get("media") or {}).get("externalServiceSlug")
            or f"tmdb:{(req.get('media') or {}).get('tmdbId')}",
            "type": (req.get("media") or {}).get("mediaType"),
            "requestedBy": (req.get("requestedBy") or {}).get("displayName"),
            "status": req.get("status"),
            "createdAt": req.get("createdAt"),
        }
        for req in data.get("results", [])
    ]

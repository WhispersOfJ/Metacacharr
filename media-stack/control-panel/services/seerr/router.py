"""Seerr routes, ported from app.py (lines ~4669-4698) - migration gap
closed after the auth cutover left this route 404ing (never given a
services/<name>/router.py, so main.py's auto-discovery never mounted it -
see the stack-seerr-requests fix that surfaced this).

Read-only - current_user_or_service, same reasoning as most other services.
"""
import json
import os

import httpx
from core.host_paths import HOST_CONFIG_DIR
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends

router = APIRouter(tags=["seerr"])

SERVICE_META = {"label": "Seerr", "health_check": None}

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


@router.get("/api/seerr/requests")
def seerr_requests(status: str = "pending", _=Depends(current_user_or_service)):
    """Pending (or any-status) media requests sitting in Seerr - the queue
    a user expects Radarr/Sonarr to eventually pick up automatically, so
    this is mostly useful for confirming a request actually landed there
    before chasing why it's not showing up downstream."""
    key = _seerr_key()
    if not key:
        fail("Could not read Seerr's API key from config/seerr/settings.json.", status_code=503)
    try:
        r = httpx.get(f"{SEERR_URL}/api/v1/request", params={"filter": status, "take": 25},
                       headers={"X-Api-Key": key}, timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Seerr lookup failed: {e}")
    data = r.json()
    items = [{
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
    } for req in data.get("results", [])]
    return ok(f"{len(items)} {status} request(s) in Seerr.", items=items)

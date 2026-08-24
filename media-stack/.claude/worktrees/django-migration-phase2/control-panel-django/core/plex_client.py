"""Shared Plex config/helpers, ported near-verbatim from the FastAPI-era
control-panel/core/plex_client.py for the Django/DRF rewrite. Used by any
plex/posters app whose services.py reads Plex library/metadata directly.

Only transform applied vs. the FastAPI-era source: core.responses.fail()
(which raised a fastapi.HTTPException) is replaced with
core.api_base.ServiceError. Every constant/function name and signature is
otherwise byte-identical.
"""
import os

import httpx

from core.api_base import ServiceError

PLEX_URL = (os.environ.get("PLEX_URL") or "").rstrip("/")
PLEX_TOKEN = os.environ.get("PLEX_TOKEN")


def plex_headers() -> dict:
    if not PLEX_URL or not PLEX_TOKEN:
        raise ServiceError("Plex isn't configured (PLEX_URL/PLEX_TOKEN not set)", status=503)
    return {"Accept": "application/json", "X-Plex-Token": PLEX_TOKEN}


def plex_sections() -> list[dict]:
    r = httpx.get(f"{PLEX_URL}/library/sections", headers=plex_headers(), timeout=15)
    r.raise_for_status()
    return r.json()["MediaContainer"].get("Directory", [])

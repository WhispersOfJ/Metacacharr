"""Shared Plex config/helpers, ported from app.py (lines 37, 516-535) -
Phase 4 of .claude/plans/evolved-control-panel-backend.plan.md. Used by
services/plex/router.py and services/posters/router.py (poster-sync reads
Plex library/metadata directly).
"""
import os

import httpx

from core.responses import fail

PLEX_URL = (os.environ.get("PLEX_URL") or "").rstrip("/")
PLEX_TOKEN = os.environ.get("PLEX_TOKEN")


def plex_headers() -> dict:
    if not PLEX_URL or not PLEX_TOKEN:
        fail("Plex isn't configured (PLEX_URL/PLEX_TOKEN not set)", status_code=503)
    return {"Accept": "application/json", "X-Plex-Token": PLEX_TOKEN}


def plex_sections() -> list[dict]:
    r = httpx.get(f"{PLEX_URL}/library/sections", headers=plex_headers(), timeout=15)
    r.raise_for_status()
    return r.json()["MediaContainer"].get("Directory", [])

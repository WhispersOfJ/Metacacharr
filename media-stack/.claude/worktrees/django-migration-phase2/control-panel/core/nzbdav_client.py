"""Shared NzbDAV config/helpers, ported from app.py (lines 44-49, 1380-1409)
- Phase 4 of .claude/plans/evolved-control-panel-backend.plan.md.

NzbDAV is the usenet streaming layer (WebDAV, no local disk; the actual
FUSE mount is a separate rclone sidecar, nzbdav_rclone - see
docker-compose.yml). Queue/history go through its SABnzbd-compatible API
(mode=queue/history, keyed by NZBDAV_API_KEY == FRONTEND_BACKEND_API_KEY,
the same value used for both the SAB surface and its admin API - no
separate JWT-login flow like BearMount had.

Moved here out of core/arr_client.py (where Phase 3 left it as a
pulled-forward dependency for queue-autofix) to give NzbDAV its own
module boundary per this repo's services-first architecture rule.
"""
import os

import httpx

from core.responses import fail

NZBDAV_URL = "http://nzbdav:3000/api"
NZBDAV_REST_URL = "http://nzbdav:3000"
NZBDAV_API_KEY = os.environ.get("FRONTEND_BACKEND_API_KEY")


def nzbdav_api(mode: str, timeout: int = 15, **params) -> dict:
    if not NZBDAV_API_KEY:
        fail("NzbDAV isn't configured (FRONTEND_BACKEND_API_KEY not set)", status_code=503)
    try:
        r = httpx.get(
            NZBDAV_URL,
            params={"mode": mode, "output": "json", "apikey": NZBDAV_API_KEY, **params},
            timeout=timeout,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"NzbDAV {mode} lookup failed: {e}")
    return r.json()

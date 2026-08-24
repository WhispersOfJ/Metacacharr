"""Shared NzbDAV config/helpers, ported near-verbatim from the FastAPI-era
control-panel/core/nzbdav_client.py for the Django/DRF rewrite.

NzbDAV is the usenet streaming layer (WebDAV, no local disk; the actual
FUSE mount is a separate rclone sidecar, nzbdav_rclone - see
docker-compose.yml). Queue/history go through its SABnzbd-compatible API
(mode=queue/history), keyed by NZBDAV_API_KEY == FRONTEND_BACKEND_API_KEY,
the same value used for both the SAB surface and its admin API - no
separate JWT-login flow like BearMount had.

Only transform applied vs. the FastAPI-era source: core.responses.fail()
(which raised a fastapi.HTTPException) is replaced with
core.api_base.ServiceError. Every constant/function name and signature is
otherwise byte-identical.
"""
import os

import httpx

from core.api_base import ServiceError

NZBDAV_URL = "http://nzbdav:3000/api"
NZBDAV_REST_URL = "http://nzbdav:3000"
NZBDAV_API_KEY = os.environ.get("FRONTEND_BACKEND_API_KEY")


def nzbdav_api(mode: str, timeout: int = 15, **params) -> dict:
    if not NZBDAV_API_KEY:
        raise ServiceError("NzbDAV isn't configured (FRONTEND_BACKEND_API_KEY not set)", status=503)
    try:
        r = httpx.get(
            NZBDAV_URL,
            params={"mode": mode, "output": "json", "apikey": NZBDAV_API_KEY, **params},
            timeout=timeout,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"NzbDAV {mode} lookup failed: {e}")
    return r.json()

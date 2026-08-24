"""Sonarr-only service (no Radarr equivalent), ported from
control-panel/services/sonarr/router.py.

Auth policy: default IsAuthenticatedOrServiceKey (not session-only) -
stack-sonarr-monitor-episodes-fix.fish calls this unattended via the
service key.
"""
import httpx

from core.api_base import ServiceError
from core.arr_client import ARR_APPS

_CHUNK_SIZE = 200


def fix_monitored_episodes() -> dict:
    """Every monitored series can drift out of sync with its own episodes -
    an import list add, a partial re-add after a bulk delete, etc. can leave
    individual episodes unmonitored under a monitored series/season. Fixes
    every such episode in non-special seasons (seasonNumber 0 is left alone
    - that's Sonarr's convention for specials/extras, not regular content)."""
    cfg = ARR_APPS["sonarr"]
    headers = {"X-Api-Key": cfg["key"]}
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/series", headers=headers, timeout=30)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} series lookup failed: {e}") from e
    monitored_series = [s for s in r.json() if s.get("monitored")]

    to_fix = []
    for s in monitored_series:
        try:
            r = httpx.get(
                f"{cfg['url']}/api/{cfg['api']}/episode",
                params={"seriesId": s["id"]},
                headers=headers,
                timeout=30,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ServiceError(f"{cfg['label']} episode lookup failed for series {s['id']}: {e}") from e
        for ep in r.json():
            if ep.get("seasonNumber") == 0:
                continue
            if not ep.get("monitored"):
                to_fix.append(ep["id"])

    for i in range(0, len(to_fix), _CHUNK_SIZE):
        chunk = to_fix[i : i + _CHUNK_SIZE]
        try:
            r = httpx.put(
                f"{cfg['url']}/api/{cfg['api']}/episode/monitor",
                json={"episodeIds": chunk, "monitored": True},
                headers=headers,
                timeout=30,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ServiceError(f"{cfg['label']} episode-monitor fix failed after {i}: {e}") from e

    return {"fixed": len(to_fix), "monitored_series": len(monitored_series)}

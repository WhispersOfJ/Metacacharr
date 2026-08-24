"""Sonarr-only route (no Radarr equivalent), ported from app.py
(lines ~3543-3583) - Phase 3 of
.claude/plans/evolved-control-panel-backend.plan.md.

Auth policy: current_user_or_service, not current_user - stack-sonarr-monitor-
episodes-fix.fish calls this unattended via __stack_api's service key
(2026-08-06 fix; this docstring previously said "no automation caller",
which was already stale by the time the fish command was added).
"""
import httpx
from fastapi import APIRouter, Depends

from core.arr_client import ARR_APPS
from core.responses import fail, ok
from core.security import current_user_or_service

router = APIRouter(tags=["sonarr"])

SERVICE_META = {"label": "Sonarr", "health_check": None}


@router.post("/api/arr/sonarr/monitor-episodes-fix")
def sonarr_monitor_episodes_fix(_=Depends(current_user_or_service)):
    """Every monitored series can drift out of sync with its own episodes -
    an import list add, a partial re-add after a bulk delete, etc. can leave
    individual episodes unmonitored under a monitored series/season. Fixes
    every such episode in non-special seasons (seasonNumber 0 is left alone
    - that's Sonarr's convention for specials/extras, not regular content)."""
    cfg = ARR_APPS["sonarr"]
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/series", headers={"X-Api-Key": cfg["key"]}, timeout=30)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} series lookup failed: {e}")
    monitored_series = [s for s in r.json() if s.get("monitored")]

    to_fix = []
    for s in monitored_series:
        try:
            r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/episode", params={"seriesId": s["id"]},
                          headers={"X-Api-Key": cfg["key"]}, timeout=30)
            r.raise_for_status()
        except httpx.HTTPError as e:
            fail(f"{cfg['label']} episode lookup failed for series {s['id']}: {e}")
        for ep in r.json():
            if ep.get("seasonNumber") == 0:
                continue
            if not ep.get("monitored"):
                to_fix.append(ep["id"])

    for i in range(0, len(to_fix), 200):
        chunk = to_fix[i:i + 200]
        try:
            r = httpx.put(f"{cfg['url']}/api/{cfg['api']}/episode/monitor",
                          json={"episodeIds": chunk, "monitored": True},
                          headers={"X-Api-Key": cfg["key"]}, timeout=30)
            r.raise_for_status()
        except httpx.HTTPError as e:
            fail(f"{cfg['label']} episode-monitor fix failed after {i}: {e}")

    return ok(f"Fixed {len(to_fix)} unmonitored episode(s) across {len(monitored_series)} monitored series.",
               fixed=len(to_fix), monitored_series=len(monitored_series))

"""Prowlarr route, ported from app.py (lines ~4624-4639) - Phase 3 of
.claude/plans/evolved-control-panel-backend.plan.md.
"""
import httpx
from fastapi import APIRouter, Depends

from core.api_hit_counts import install as install_hit_counter, register_host_label
from core.arr_client import PROWLARR_CFG
from core.responses import fail, ok
from core.security import current_user_or_service

router = APIRouter(tags=["prowlarr"])

SERVICE_META = {"label": "Prowlarr", "health_check": None}

register_host_label(PROWLARR_CFG["url"], "Prowlarr")
install_hit_counter()


@router.get("/api/prowlarr/indexers")
def prowlarr_indexers(_=Depends(current_user_or_service)):
    """Every configured indexer's enabled/priority state in one place -
    Prowlarr's own UI is the only other place to see this without
    hitting the API directly."""
    if not PROWLARR_CFG["key"]:
        fail("PROWLARR_API_KEY not set.", status_code=503)
    try:
        r = httpx.get(f"{PROWLARR_CFG['url']}/api/{PROWLARR_CFG['api']}/indexer",
                       headers={"X-Api-Key": PROWLARR_CFG["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Prowlarr lookup failed: {e}")
    items = [{"name": i.get("name"), "enabled": i.get("enable"), "priority": i.get("priority")} for i in r.json()]
    items.sort(key=lambda i: i["name"] or "")
    enabled = sum(1 for i in items if i["enabled"])
    return ok(f"{enabled}/{len(items)} indexers enabled.", items=items)

"""Prowlarr indexer listing service, ported from
the FastAPI-era control-panel/services/prowlarr/router.py.
"""
import httpx

from core.api_base import ServiceError
from core.arr_client import PROWLARR_CFG


def list_indexers() -> list[dict]:
    """Every configured indexer's enabled/priority state in one place -
    Prowlarr's own UI is the only other place to see this without
    hitting the API directly."""
    if not PROWLARR_CFG.get("key"):
        raise ServiceError("PROWLARR_API_KEY is not configured", status=503)
    try:
        response = httpx.get(
            f"{PROWLARR_CFG['url']}/api/{PROWLARR_CFG['api']}/indexer",
            headers={"X-Api-Key": PROWLARR_CFG["key"]},
            timeout=20,
        )
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"Prowlarr lookup failed: {e}") from e
    items = [
        {"name": item.get("name"), "enabled": item.get("enable"), "priority": item.get("priority")}
        for item in response.json()
    ]
    return sorted(items, key=lambda item: item["name"] or "")

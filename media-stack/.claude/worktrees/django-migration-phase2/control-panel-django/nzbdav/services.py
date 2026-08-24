"""NzbDAV routes, ported from the FastAPI-era
control-panel/services/nzbdav/router.py.

queue/history/stats are read-only; dedup-config-check is a diagnostic
read; delete-failures is a bulk cleanup of already-failed history entries
(no live download it could disrupt) - IsAuthenticatedOrServiceKey
throughout, same reasoning as arr's automation-invoked mutating routes.

Module-qualified references to core.nzbdav_client (rather than `from ...
import NZBDAV_API_KEY` etc.) are deliberate: NZBDAV_API_KEY is a plain
str constant, and importing the name directly would bind a copy at
import time that tests could not monkeypatch. Going through the module
object keeps every constant lookup live, matching how nzbdav_api()
itself reads NZBDAV_API_KEY internally.
"""
import concurrent.futures

import httpx

from core import nzbdav_client
from core.api_base import ServiceError
from core.arr_client import human_size


def get_queue() -> list[dict]:
    slots = nzbdav_client.nzbdav_api("queue").get("queue", {}).get("slots", [])
    return [{
        "name": s.get("filename"),
        "category": s.get("cat"),
        "status": s.get("status"),
        "percentage": s.get("percentage"),
        "size_mb": s.get("mb"),
        "size_left_mb": s.get("mbleft"),
    } for s in slots]


def get_history(limit: int = 20) -> list[dict]:
    slots = nzbdav_client.nzbdav_api("history", limit=limit).get("history", {}).get("slots", [])
    return [{
        "name": s.get("name"),
        "category": s.get("category"),
        "status": s.get("status"),
        "size": human_size(s.get("bytes")),
        "fail_message": s.get("fail_message") or None,
        "path": s.get("storage"),
    } for s in slots]


def check_dedup_config() -> dict:
    """One-off diagnostic for the 2026-08-01 dedup-suffix fix - confirms
    api.duplicate-nzb-behavior is still mark-failed (not reverted to
    increment, which is what caused the original importBlocked-loop bug).
    Uses get-config directly (form-encoded POST, not nzbdav_api()'s
    mode= based SAB surface - a GET with query params 500s here)."""
    if not nzbdav_client.NZBDAV_API_KEY:
        raise ServiceError("NzbDAV isn't configured (FRONTEND_BACKEND_API_KEY not set)", status=503)
    try:
        r = httpx.post(
            f"{nzbdav_client.NZBDAV_REST_URL}/api/get-config",
            data={"config-keys": "api.duplicate-nzb-behavior"},
            headers={"X-Api-Key": nzbdav_client.NZBDAV_API_KEY},
            timeout=15,
        )
        r.raise_for_status()
        items = r.json().get("configItems", [])
        value = items[0].get("configValue") if items else None
    except httpx.HTTPError as e:
        raise ServiceError(f"NzbDAV config lookup failed: {e}") from e
    healthy = value == "mark-failed"
    message = ("NzbDAV dedup config OK (mark-failed)." if healthy
               else f"NzbDAV dedup config is '{value}' - should be 'mark-failed', "
                    "or the (2)/(3)-suffix importBlocked bug can return.")
    return {"message": message, "value": value, "healthy": healthy}


def get_stats() -> dict:
    """Aggregate counts instead of the raw queue/history dumps
    get_queue()/get_history() above already provide - queued count and
    total size left, plus history success/fail counts, in one glance."""
    queue = nzbdav_client.nzbdav_api("queue").get("queue", {}).get("slots", [])
    history = nzbdav_client.nzbdav_api("history", limit=100).get("history", {}).get("slots", [])
    fail_count = sum(1 for h in history if (h.get("status") or "").lower() == "failed")
    mb_left = sum(float(s.get("mbleft") or 0) for s in queue)
    return {
        "message": f"{len(queue)} queued ({mb_left:.0f}MB left), {len(history)} in recent history "
                   f"({fail_count} failed).",
        "queued": len(queue),
        "mb_left": round(mb_left),
        "history_count": len(history),
        "history_failed": fail_count,
    }


def delete_failures() -> dict:
    """Deletes every "Failed" history entry via NzbDAV's SABnzbd-compatible
    delete endpoint (mode=history&name=delete&value=<nzo_id>, one id per
    call, same shape BearMount's equivalent route used). Deletes fan out
    across threads rather than running serially - same-host calls, not
    rate-limited."""
    history = nzbdav_client.nzbdav_api("history", limit=0, timeout=180)
    slots = history.get("history", {}).get("slots", [])
    failed = [s for s in slots if (s.get("status") or "") == "Failed"]
    if not failed:
        return {"message": "No failed history entries to delete.", "deleted": 0, "errors": []}

    def delete_one(slot):
        try:
            r = httpx.get(nzbdav_client.NZBDAV_URL, params={
                "mode": "history", "name": "delete", "value": slot["nzo_id"],
                "apikey": nzbdav_client.NZBDAV_API_KEY, "output": "json",
            }, timeout=30)
            r.raise_for_status()
            result = r.json()
        except httpx.HTTPError as e:
            return False, f'{slot.get("name")}: {e}'
        if result.get("status"):
            return True, None
        return False, f'{slot.get("name")}: {result.get("error")}'

    deleted, errors = 0, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        for ok_, message in pool.map(delete_one, failed):
            if ok_:
                deleted += 1
            else:
                errors.append(message)
    msg = f"Deleted {deleted}/{len(failed)} failed history entries."
    if errors:
        msg += f" {len(errors)} error(s)."
    return {"message": msg, "deleted": deleted, "errors": errors[:20]}

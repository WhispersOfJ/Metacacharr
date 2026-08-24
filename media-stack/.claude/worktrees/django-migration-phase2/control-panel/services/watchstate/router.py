"""WatchState routes - Phase 6 of PLANS.md's 7-service integration batch.

WatchState keeps its own record of what has been watched, fed from Plex by a
scheduled import and a webhook. These routes proxy its REST API: what the last
import did, an out-of-schedule import, and the watch history for a title.

Things established by reading upstream source rather than PLANS.md's guesses:

1. **Auth is `X-apikey`**, checked by `AuthorizationMiddleware` against
   `WS_API_KEY`. It also accepts `?apikey=` and a bearer token; the header
   keeps the key out of WatchState's own access log.

2. **Triggering an import is a queue, not a call.** `POST /v1/api/tasks/import
   /queue` enqueues an event; a separate dispatcher task (`events:dispatch`,
   every minute, not disableable) is what actually runs it. So /import returns
   "queued", never "done", and status is where the result shows up.

3. **An empty history is a 404**, not an empty list - WatchState answers
   `{"error": {"code": 404, "message": "No Results."}}`. Before the first
   import finishes that is the normal state, so it must not surface as a
   failure.

The scheduled import stays enabled even though the webhook is registered.
Upstream's README says to keep it that way because webhooks drop events, and
this stack's compose block says the same. Neither is an oversight to clean up.
"""
import os
from datetime import datetime

import httpx
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(tags=["watchstate"])

SERVICE_META = {"label": "WatchState", "health_check": None}

WATCHSTATE_URL = "http://watchstate:8080"
API = f"{WATCHSTATE_URL}/v1/api"
# The one backend this stack registers, named by scripts/watchstate-provision.py.
BACKEND_NAME = "plex"
# The task PLANS.md 6.4 requires stay enabled alongside the webhook.
IMPORT_TASK = "import"


def _headers() -> dict:
    # Bare subscript, same as core.arr_client: a missing key is a deployment
    # misconfiguration that should fail loudly rather than send an
    # unauthenticated request and report a confusing 400.
    return {"X-apikey": os.environ["WS_API_KEY"]}


def _request(method: str, path: str, params: dict | None = None, timeout: int = 30) -> tuple[int, dict | list]:
    """Returns (status_code, parsed_body) without raising on 4xx.

    404 is a real answer from this API (see the module docstring), and the
    task/backend routes use 404 for "no such name", which callers report
    rather than retry.
    """
    try:
        r = httpx.request(method, f"{API}{path}", params=params, headers=_headers(), timeout=timeout)
    except httpx.HTTPError as e:
        fail(f"WatchState request failed: {e}")
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


def _error(body) -> str:
    """WatchState wraps failures as {"error": {"code": .., "message": ..}}."""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)
        if error:
            return str(error)
    return str(body)


def _backend() -> dict:
    status, body = _request("GET", "/backends")
    if status != 200 or not isinstance(body, list):
        fail(f"Couldn't list WatchState's backends: {_error(body)}")
    return next((b for b in body if b.get("name") == BACKEND_NAME), {})


def _import_task() -> dict:
    status, body = _request("GET", f"/tasks/{IMPORT_TASK}")
    if status != 200 or not isinstance(body, dict):
        fail(f"Couldn't read the '{IMPORT_TASK}' task: {_error(body)}")
    return body


def _history(params: dict) -> tuple[list, int]:
    """Returns (items, total). An empty database answers 404, not an empty list."""
    status, body = _request("GET", "/history", params, timeout=60)
    if status == 404:
        return [], 0
    if status != 200 or not isinstance(body, dict):
        fail(f"Couldn't read WatchState's history: {_error(body)}")
    items = body.get("history") or body.get("items") or []
    total = ((body.get("paging") or {}).get("total"))
    return items, int(total if total is not None else len(items))


def _timestamp(value) -> str | None:
    """WatchState stores `updated` as a unix int; render it as local ISO.

    A bare epoch in a terminal is unreadable, and "did this row come from the
    webhook or the 17:25 import" is exactly the question these rows get asked.
    """
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value)).astimezone().isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        # Already a string (or something unparseable) - pass it through rather
        # than dropping the only timing information the row has.
        return str(value)


def _shape(item: dict) -> dict:
    """One history row, flattened to what a terminal reader needs.

    `via` is which backend reported it and `updated_at` when - together they
    are what distinguishes a webhook-delivered event from one the scheduled
    import picked up, which is the pair Phase 6 has to be able to tell apart.
    """
    return {
        "id": item.get("id"),
        "title": item.get("full_title") or item.get("title"),
        "type": item.get("type"),
        "year": item.get("year"),
        "season": item.get("season"),
        "episode": item.get("episode"),
        "watched": bool(item.get("watched")),
        "via": item.get("via"),
        "updated_at": _timestamp(item.get("updated_at") or item.get("updated")),
    }


class ImportRequest(BaseModel):
    pass


@router.get("/api/watchstate/status")
def watchstate_status(_=Depends(current_user_or_service)):
    """Version, the Plex backend's sync state, and the import task's schedule."""
    status, version = _request("GET", "/system/version")
    if status != 200:
        fail(f"WatchState is not answering: {_error(version)}")

    backend = _backend()
    task = _import_task()
    _, total = _history({"perpage": 1})

    if not backend:
        message = (f"No '{BACKEND_NAME}' backend registered - run "
                   f"scripts/watchstate-provision.py.")
    elif task.get("queued"):
        message = f"Import queued, {total} item(s) tracked."
    else:
        last = task.get("prev_run") or "never"
        message = f"Idle. {total} item(s) tracked, last import {last}, next {task.get('next_run')}."

    return ok(
        message,
        version=(version or {}).get("version"),
        tracked=total,
        backend={
            "name": backend.get("name"),
            "url": backend.get("url"),
            "import_enabled": bool((backend.get("import") or {}).get("enabled")),
            # Export writes back INTO Plex and is deliberately off - see the
            # compose block. Surfaced so a silent flip is visible here.
            "export_enabled": bool((backend.get("export") or {}).get("enabled")),
            "last_sync": (backend.get("import") or {}).get("lastSync"),
        } if backend else None,
        task={
            "enabled": bool(task.get("enabled")),
            "timer": task.get("timer"),
            "next_run": task.get("next_run"),
            "prev_run": task.get("prev_run"),
            "queued": bool(task.get("queued")),
        },
    )


@router.post("/api/watchstate/import")
def watchstate_import(_payload: ImportRequest | None = None, _=Depends(current_user_or_service)):
    """Queue an out-of-schedule import.

    Queued, not run: WatchState's dispatcher picks the event up on its own
    once-a-minute cycle. Poll /api/watchstate/status for the result rather
    than expecting one here.
    """
    status, body = _request("POST", f"/tasks/{IMPORT_TASK}/queue")
    if status not in (200, 201, 202):
        fail(f"Couldn't queue the import: {_error(body)}")
    event_id = body.get("id") if isinstance(body, dict) else None
    return ok("Import queued - WatchState's dispatcher runs it within a minute. "
              "Check stack-watchstate-status for the result.",
              event_id=event_id, task=IMPORT_TASK)


@router.get("/api/watchstate/history")
def watchstate_history(item: str = "", limit: int = 20, _=Depends(current_user_or_service)):
    """Watch history, optionally filtered to titles matching `item`.

    The filter is WatchState's own `title` query param, which matches on the
    stored title rather than an exact id, so a partial name works.
    """
    if limit <= 0:
        fail("limit must be a positive integer.", status_code=400)
    params: dict = {"perpage": limit}
    if item.strip():
        params["title"] = item.strip()

    items, total = _history(params)
    rows = [_shape(i) for i in items]

    scope = f" matching '{item}'" if item.strip() else ""
    if not rows:
        # An empty result and a never-imported database read identically here,
        # and they mean different things, so the status route is named.
        message = (f"No watch history{scope}. If this is unexpected, check "
                   f"stack-watchstate-status - the first import may not have run yet.")
    else:
        message = f"{total} item(s){scope}, showing {len(rows)}."
    return ok(message, history=rows, total=total, shown=len(rows))

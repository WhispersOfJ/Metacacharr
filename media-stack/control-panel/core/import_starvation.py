"""Detects Radarr/Sonarr import starvation - the 2026-08-08 incident where
a mass backfill silently stopped all imports for hours.

Mechanism: RefreshMonitoredDownloads is the single command that both polls
the download client (populating the queue) and triggers imports of completed
items. It runs on a 1-minute schedule but shares a thread pool with searches
and has no priority over them. Queue 1104 MoviesSearch commands and it simply
never gets a slot - radarr's went 85 minutes without starting, sonarr_anime's
146 minutes, while both kept grabbing thousands of releases.

The trap for any health check: because RefreshMonitoredDownloads is what
*populates* the queue, a starved app reports an EMPTY queue. Every
queue-shaped check (trackedDownloadStatus flags, failedPending counts,
importBlocked counts) reads perfectly clean on a totally broken app. That is
exactly how the first sweep of the incident mis-reported all four apps as
healthy. Never infer health from an empty queue alone - ask this module.

Two independent signals, both cheap and deterministic:
  1. A queued RefreshMonitoredDownloads older than STARVATION_THRESHOLD.
     Conclusive on its own - the command is scheduled every 60s, so a
     queued-but-not-started one past the threshold means the pool is full.
  2. last-grab newer than last-import by more than the same threshold.
     Corroborating evidence, and the signal a human actually notices
     ("nothing is showing up in Sonarr").
"""
from datetime import datetime, timezone

import httpx

from core.arr_client import ARR_APPS, QUEUE_ARR_APPS, require_queue_app

# RefreshMonitoredDownloads is scheduled every 60s. Five minutes of it
# sitting queued is well past any normal contention and comfortably clear of
# a slow-but-progressing run.
STARVATION_THRESHOLD_SECONDS = 300

REFRESH_COMMAND = "RefreshMonitoredDownloads"

# Bulk search commands - the only thing observed to saturate the pool. A
# targeted single-item search is fine and must not be cancelled, but these
# arrive in the thousands from a backfill. ProcessMonitoredDownloads is
# deliberately absent: it is the import worker, never the blocker.
SEARCH_COMMANDS = frozenset({
    "MoviesSearch", "MovieSearch", "MissingMoviesSearch", "CutoffUnmetMoviesSearch",
    "MissingEpisodeSearch", "EpisodeSearch", "SeasonSearch", "SeriesSearch",
    "CutoffUnmetEpisodeSearch",
})

# Radarr/Sonarr history eventType ids.
EVENT_GRABBED = 1
EVENT_IMPORTED = 3


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _get(cfg: dict, path: str, params: dict | None = None, timeout: int = 30):
    r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/{path}",
                  params=params or {}, headers={"X-Api-Key": cfg["key"]}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _age_seconds(ts: datetime | None, now: datetime) -> float | None:
    return None if ts is None else (now - ts).total_seconds()


def refresh_starvation(app_name: str, now: datetime | None = None) -> dict:
    """Signal 1: how long the oldest queued RefreshMonitoredDownloads has
    been waiting, plus what is occupying the pool ahead of it."""
    cfg = require_queue_app(app_name)
    now = now or datetime.now(timezone.utc)
    commands = _get(cfg, "command")

    active = [c for c in commands if c.get("status") in ("queued", "started")]
    waiting = [c for c in active
               if c.get("name") == REFRESH_COMMAND and c.get("status") == "queued"]
    ages = [a for a in (_age_seconds(_parse_ts(c.get("queued")), now) for c in waiting)
            if a is not None]
    starved_seconds = max(ages) if ages else 0.0

    return {
        "starved_seconds": round(starved_seconds),
        "refresh_queued": len(waiting),
        "queued_searches": sum(1 for c in active
                               if c.get("status") == "queued" and c.get("name") in SEARCH_COMMANDS),
        "active_commands": len(active),
    }


def grab_import_lag(app_name: str, now: datetime | None = None) -> dict:
    """Signal 2: the user-visible symptom - releases still being grabbed
    while nothing has imported for a long time."""
    cfg = require_queue_app(app_name)
    now = now or datetime.now(timezone.utc)

    def newest(event_type: int) -> datetime | None:
        page = _get(cfg, "history", {"pageSize": 1, "eventType": event_type,
                                     "sortKey": "date", "sortDirection": "descending"})
        records = page.get("records") or []
        return _parse_ts(records[0].get("date")) if records else None

    last_grab, last_import = newest(EVENT_GRABBED), newest(EVENT_IMPORTED)
    lag = None
    if last_grab is not None and last_import is not None:
        lag = round((last_grab - last_import).total_seconds())

    return {
        "last_grab": last_grab.isoformat() if last_grab else None,
        "last_import": last_import.isoformat() if last_import else None,
        "lag_seconds": lag,
        "import_age_seconds": (lambda a: round(a) if a is not None else None)(
            _age_seconds(last_import, now)),
    }


def detect(app_name: str, now: datetime | None = None) -> dict:
    """Combine both signals into one verdict for a single app."""
    now = now or datetime.now(timezone.utc)
    starvation = refresh_starvation(app_name, now)
    lag = grab_import_lag(app_name, now)

    starved = starvation["starved_seconds"] > STARVATION_THRESHOLD_SECONDS
    lagging = (lag["lag_seconds"] or 0) > STARVATION_THRESHOLD_SECONDS

    if starved:
        reason = (f"{REFRESH_COMMAND} has been queued {starvation['starved_seconds']}s "
                  f"behind {starvation['queued_searches']} queued search command(s).")
    elif lagging:
        reason = (f"Last grab is {lag['lag_seconds']}s newer than the last import, but "
                  f"{REFRESH_COMMAND} is running - imports may be blocked for another reason.")
    else:
        reason = "Imports are keeping up with grabs."

    return {
        "app": app_name,
        "label": ARR_APPS[app_name]["label"],
        "starved": starved,
        "lagging": lagging,
        "reason": reason,
        **starvation,
        **lag,
    }


def clear_search_backlog(app_name: str) -> dict:
    """Remediation: cancel every QUEUED bulk search so the pool frees up.

    Only queued commands can be cancelled - Radarr/Sonarr return 409 for a
    started one, which is correct and expected; those few finish on their
    own and the pool drains behind them. Cancelling is safe and reversible:
    a cancelled search re-queues on the next scheduled or manual run, and
    the backlog it was working through is still recorded as wanted/missing.
    """
    cfg = require_queue_app(app_name)
    targets = [c for c in _get(cfg, "command")
               if c.get("status") == "queued" and c.get("name") in SEARCH_COMMANDS]

    cancelled, failed = 0, 0
    for command in targets:
        try:
            r = httpx.delete(f"{cfg['url']}/api/{cfg['api']}/command/{command['id']}",
                             headers={"X-Api-Key": cfg["key"]}, timeout=30)
            r.raise_for_status()
            cancelled += 1
        except httpx.HTTPError:
            failed += 1

    return {"targeted": len(targets), "cancelled": cancelled, "failed": failed}


def check_all(remediate: bool = True, now: datetime | None = None) -> dict:
    """Every queue-bearing app, with optional auto-remediation of the ones
    found starved. Safe to run unattended on the 5-minute autofix loop."""
    now = now or datetime.now(timezone.utc)
    per_app, remediated = {}, {}
    for app_name in QUEUE_ARR_APPS:
        verdict = detect(app_name, now)
        per_app[app_name] = verdict
        if remediate and verdict["starved"]:
            remediated[app_name] = clear_search_backlog(app_name)

    starved = sorted(a for a, v in per_app.items() if v["starved"])
    lagging = sorted(a for a, v in per_app.items() if v["lagging"] and not v["starved"])
    return {"apps": per_app, "starved": starved, "lagging": lagging, "remediated": remediated}

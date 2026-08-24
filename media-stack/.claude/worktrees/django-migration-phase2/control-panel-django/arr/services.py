"""Generic Radarr/Sonarr routes that dispatch on {app_name}, ported from the
FastAPI-era control-panel/services/arr/router.py for the Django/DRF rewrite.

Auth: every route here is the default tier (IsAuthenticatedOrServiceKey) -
the FastAPI-era current_user_or_service dependency was used on all 27
routes, including the mutating ones, because the stack-queue-autofix.fish
5-minute unattended cron loop and the stack-cli-arr-fleet skill's other
automation-invoked commands call them without an interactive session via
__stack_api's service key. No route in this app is session-only - a
regression to IsAuthenticatedSessionOnly here would silently break that
cron loop. See arr/api/views.py.

Transforms applied vs. the FastAPI-era source:
1. core.responses.fail()/ok()/now() and fastapi.Depends are replaced with
   core.api_base.ServiceError and plain dict/list returns; the view layer
   builds the {ok, message, time, ...} envelope via EnvelopeAPIView.ok().
2. The `except HTTPException` partial-failure branches (backlog_status,
   queue_errors) become `except ServiceError` - the Django port's
   wanted_missing_total/recent_import_rate_per_hour/arr_queue raise
   ServiceError instead of fastapi's HTTPException, and the behavior (one
   unreachable app degrades to a per-app error entry, not a 500) is
   identical.
3. The module-level api_hit_counts install()/register_host_label() calls
   are deliberately dropped - that module is a metrics/telemetry
   side-effect the migration spec doesn't require preserving (see the plan
   Task 17 Step 1 scope-trim note); the rest of the port is unaffected.
4. The FastAPI-era rate_limit() dependency is dropped - no in-process rate
   limiter in the Django port (same precedent as host/host_actions).
Every function name is otherwise the same as the source route handler
(route-verb suffix kept where the source used one, e.g. search_missing),
and the payload shapes are byte-identical.
"""
import os
from collections import Counter
from datetime import datetime, timezone

import docker
import httpx

from core import import_starvation
from core import settings as settings_core
from core.api_base import ServiceError
from core.arr_client import (
    ARR_APPS,
    PROWLARR_CFG,
    QUEUE_ARR_APPS,
    RADARR_APPS,
    RECENT_IMPORT_LOOKBACK_HOURS,
    arr_command,
    arr_queue,
    blocklist_and_research,
    current_queue_output_path,
    dd_test_file,
    dedup_suffix_hit,
    disable_autoredownload_if_storm,
    find_candidate_files,
    format_eta,
    get_movie_or_episode,
    human_size,
    import_candidate_queue_items,
    importing_queue_targets,
    nzbdav_api,
    recent_import_rate_per_hour,
    require_queue_app,
    stuck_queue_items,
    wanted_missing_total,
)
from core.docker_client import docker_client

ARR_LOG_CONTAINERS = {"radarr", "sonarr", "prowlarr"}

LOOP_MIN_OCCURRENCES = 2


def rss_sync(app_name: str) -> str:
    # Automation-invoked: stack-cli-arr-fleet skill's rss-sync command.
    cfg = arr_command(app_name, "RssSync")
    return f"{cfg['label']} RSS sync started."


def search_missing(app_name: str) -> str:
    # Automation-invoked: stack-cli-arr-fleet skill's search-missing command.
    if app_name not in ARR_APPS:
        raise ServiceError(f"Unknown app '{app_name}'.", status=404)
    cfg = ARR_APPS[app_name]
    arr_command(app_name, cfg["search_command"])
    return f"{cfg['label']} search for missing items started."


def search_status(app_name: str) -> dict:
    if app_name not in ARR_APPS:
        raise ServiceError(f"Unknown app '{app_name}'.", status=404)
    cfg = ARR_APPS[app_name]
    url = f"{cfg['url']}/api/{cfg['api']}/indexer"
    try:
        r = httpx.get(url, headers={"X-Api-Key": cfg["key"]}, timeout=15)
        r.raise_for_status()
        indexers = r.json()
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} indexer status check failed: {e}") from e
    enabled = bool(indexers) and all(i.get("enableRss") and i.get("enableAutomaticSearch") for i in indexers)
    return {"enabled": enabled}


def search_toggle(app_name: str, enabled: bool) -> str:
    # Automation-invoked: stack-cli-arr-fleet skill's search-toggle command.
    if app_name not in ARR_APPS:
        raise ServiceError(f"Unknown app '{app_name}'.", status=404)
    cfg = ARR_APPS[app_name]
    url = f"{cfg['url']}/api/{cfg['api']}/indexer"
    headers = {"X-Api-Key": cfg["key"]}
    try:
        r = httpx.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        indexers = r.json()
        for indexer in indexers:
            indexer["enableRss"] = enabled
            indexer["enableAutomaticSearch"] = enabled
            put = httpx.put(f"{url}/{indexer['id']}", json=indexer, headers=headers, timeout=15)
            put.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} indexer search toggle failed: {e}") from e
    state = "enabled" if enabled else "disabled"
    return f"{cfg['label']}: RSS sync + automatic search {state} on {len(indexers)} indexer(s)."


def command_backlog(app_name: str) -> dict:
    if app_name not in ARR_APPS:
        raise ServiceError(f"Unknown app '{app_name}'.", status=404)
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/command", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} command lookup failed: {e}") from e
    commands = r.json()
    counts = Counter(c.get("status") for c in commands)
    running = sorted(
        ({"id": c["id"], "name": c["name"], "started": c.get("started")} for c in commands if c.get("status") == "started"),
        key=lambda c: c["started"] or "",
    )
    queued = sorted((c for c in commands if c.get("status") == "queued"), key=lambda c: c.get("queued") or "")
    oldest_queued = [{"id": c["id"], "name": c["name"], "queued": c.get("queued")} for c in queued[:5]]
    return {
        "message": f"{cfg['label']}: {len(commands)} commands total "
                   f"({counts.get('completed', 0)} completed, {counts.get('queued', 0)} queued, {counts.get('started', 0)} running).",
        "total": len(commands), "counts": dict(counts), "running": running,
        "queued_total": len(queued), "oldest_queued": oldest_queued,
    }


def unstick(app_name: str) -> dict:
    # Automation-invoked: stack-cli-arr-fleet skill's unstick command.
    cfg = require_queue_app(app_name)
    items = stuck_queue_items(app_name)
    if not items:
        return {"message": f"No stuck downloads in {cfg['label']}.", "removed": [], "errors": []}
    removed, errors = [], []
    for q in items:
        title = q.get("title") or str(q["id"])
        try:
            r = httpx.delete(f"{cfg['url']}/api/{cfg['api']}/queue/{q['id']}",
                              params={"removeFromClient": "true", "blocklist": "true", "skipRedownload": "false"},
                              headers={"X-Api-Key": cfg["key"]}, timeout=20)
            r.raise_for_status()
            removed.append(title)
        except httpx.HTTPError as e:
            errors.append(f"{title}: {e}")
    if errors and not removed:
        raise ServiceError(f"Unstick failed for all {len(errors)} stuck item(s) in {cfg['label']}: {errors[0]}")
    message = f"Removed, blocklisted, and re-searching {len(removed)} stuck download(s) in {cfg['label']}."
    if errors:
        message += f" {len(errors)} failed."
    return {"message": message, "removed": removed, "errors": errors}


def unstick_importing(app_name: str) -> dict:
    # Automation-invoked: stack-cli-arr-fleet skill's unstick-importing command.
    cfg = require_queue_app(app_name)
    targets = importing_queue_targets(app_name)
    if not targets:
        return {"message": f"No downloads currently importing in {cfg['label']}.", "results": []}
    try:
        container = docker_client.containers.get(app_name)
    except docker.errors.NotFound:
        raise ServiceError(f"Container '{app_name}' not found.")

    results = []
    to_research: set[tuple[str, int]] = set()
    for t in targets:
        output_path = t.get("outputPath")
        title = t.get("title") or "(untitled)"
        if not output_path:
            results.append({"title": title, "verdict": "skipped", "detail": "no outputPath on queue item"})
            continue
        status, files = find_candidate_files(container, output_path)
        if status == "empty":
            results.append({"title": title, "verdict": "skipped", "detail": "outputPath exists but has no candidate file"})
            continue
        if status == "missing":
            blocklist = False
            detail = "outputPath does not exist on disk"
        else:
            readable, detail = dd_test_file(container, files[0])
            blocklist = not readable
        delete_failed = False
        for qid in t["queueIds"]:
            try:
                r = httpx.delete(f"{cfg['url']}/api/{cfg['api']}/queue/{qid}",
                                  params={"removeFromClient": "true", "blocklist": str(blocklist).lower(), "skipRedownload": "false"},
                                  headers={"X-Api-Key": cfg["key"]}, timeout=20)
                if r.status_code not in (200, 404):
                    r.raise_for_status()
            except httpx.HTTPError as e:
                results.append({"title": title, "verdict": "error", "detail": f"delete failed: {e}"})
                delete_failed = True
                break
        if delete_failed:
            continue
        if status == "missing":
            verdict = "path-missing-cleared"
        elif blocklist:
            verdict = "broken-blocklisted"
        else:
            verdict = "wedged-cleared"
        results.append({"title": title, "verdict": verdict, "detail": detail})
        if t.get("seriesId"):
            to_research.add(("series", t["seriesId"]))
        if t.get("movieId"):
            to_research.add(("movie", t["movieId"]))

    for kind, rid in to_research:
        body = {"name": "SeriesSearch", "seriesId": rid} if kind == "series" else {"name": "MoviesSearch", "movieIds": [rid]}
        try:
            httpx.post(f"{cfg['url']}/api/{cfg['api']}/command", json=body, headers={"X-Api-Key": cfg["key"]}, timeout=20)
        except httpx.HTTPError:
            pass

    broken_n = sum(1 for r in results if r["verdict"] == "broken-blocklisted")
    wedged_n = sum(1 for r in results if r["verdict"] == "wedged-cleared")
    missing_n = sum(1 for r in results if r["verdict"] == "path-missing-cleared")
    message = (f"{cfg['label']}: checked {len(targets)} importing item(s) - "
               f"{broken_n} broken/blocklisted, {wedged_n} wedged/cleared, {missing_n} missing-path/cleared.")
    return {"message": message, "results": results}


def import_starvation_status() -> dict:
    """Read-only view of core/import_starvation.py's two signals across every
    queue-bearing app. The mutating counterpart runs inside queue_autofix()
    below - this route exists for a human asking 'why is nothing importing'."""
    result = import_starvation.check_all(remediate=False)
    if result["starved"]:
        message = (f"{len(result['starved'])} app(s) starved of "
                   f"{import_starvation.REFRESH_COMMAND}: {', '.join(result['starved'])}.")
    elif result["lagging"]:
        message = f"{len(result['lagging'])} app(s) lagging on imports: {', '.join(result['lagging'])}."
    else:
        message = "Every app is importing in step with its grabs."
    return {"message": message, **result}


def queue_autofix() -> dict:
    # Automation-invoked: stack-queue-autofix.fish's 5-minute unattended
    # cron loop - the reason current_user_or_service was extended to cover
    # mutating routes at all (see core/security.py's docstring).
    #
    # Starvation runs FIRST and every cycle: while an app is starved its
    # queue reads empty, so every check below it would find nothing wrong
    # and report a healthy app. Clearing the search backlog here is what
    # makes the rest of this function's findings meaningful at all.
    starvation = import_starvation.check_all(remediate=True)

    threshold = settings_core.get_settings()["failed_pending_storm_threshold"]
    per_app = {}
    for app_name in QUEUE_ARR_APPS:
        items = arr_queue(app_name)
        failed = [q for q in items if q.get("trackedDownloadState") == "failedPending"]
        blocked = [q for q in items if app_name in RADARR_APPS and q.get("trackedDownloadState") == "importBlocked"]
        fixed, errors = blocklist_and_research(app_name, failed + blocked)
        storm_disabled = disable_autoredownload_if_storm(app_name, len(failed), threshold)
        per_app[app_name] = {
            "failed_pending": len(failed), "import_blocked": len(blocked), "fixed": fixed, "errors": errors,
            "autoredownload_disabled": storm_disabled,
        }

    nz = nzbdav_api("queue").get("queue", {})
    nzbdav_health = {"slots": len(nz.get("slots", [])), "paused": bool(nz.get("paused"))}

    total_fixed = sum(len(r["fixed"]) for r in per_app.values())
    total_errors = sum(len(r["errors"]) for r in per_app.values())
    storms = [a for a, r in per_app.items() if r["autoredownload_disabled"]]
    parts = [f"Fixed {total_fixed} stuck queue item(s) across radarr/sonarr."]
    if total_errors:
        parts.append(f"{total_errors} error(s).")
    if storms:
        parts.append(f"Disabled autoRedownloadFailed (retry storm) for: {', '.join(storms)}.")
    if starvation["starved"]:
        cancelled = sum(r["cancelled"] for r in starvation["remediated"].values())
        parts.append(f"Cleared {cancelled} queued search(es) starving imports on: "
                     f"{', '.join(starvation['starved'])}.")
    if starvation["lagging"]:
        parts.append(f"WARNING: imports lagging grabs on: {', '.join(starvation['lagging'])}.")
    if nzbdav_health["paused"]:
        parts.append("WARNING: NzbDAV queue is paused.")
    return {
        "message": " ".join(parts),
        "radarr": per_app.get("radarr"), "sonarr": per_app.get("sonarr"),
        "nzbdav": nzbdav_health, "import_starvation": starvation,
    }


def loop_candidates(app_name: str, hours: float = 6.0) -> dict:
    cfg = require_queue_app(app_name)
    id_field = "movieId" if app_name in RADARR_APPS else "episodeId"
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/history",
                       params={"eventType": 4, "pageSize": 500, "sortKey": "date", "sortDirection": "descending"},
                       headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} history lookup failed: {e}") from e

    cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
    groups: dict[int, dict] = {}
    for rec in r.json().get("records", []):
        target_id = rec.get(id_field)
        if target_id is None:
            continue
        date_str = rec.get("date", "")
        try:
            ts = datetime.fromisoformat(date_str.replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if ts < cutoff:
            continue
        g = groups.setdefault(target_id, {"releases": [], "count": 0})
        g["count"] += 1
        title = rec.get("sourceTitle")
        if title and title not in g["releases"]:
            g["releases"].append(title)

    candidates = [{"id": tid, **g} for tid, g in groups.items() if g["count"] >= LOOP_MIN_OCCURRENCES]

    loop_review_profile_threshold = settings_core.get_settings()["loop_review_profile_threshold"]
    series_counts: Counter = Counter()
    detail_by_id: dict[int, dict] = {}
    for c in candidates:
        detail = get_movie_or_episode(app_name, cfg, c["id"])
        detail_by_id[c["id"]] = detail or {}
        if app_name == "sonarr" and detail:
            series_counts[detail.get("seriesId")] += 1

    rows = []
    for c in candidates:
        detail = detail_by_id[c["id"]]
        monitored = bool(detail.get("monitored", True))
        has_file = bool(detail.get("hasFile", False))
        title = detail.get("title") or (c["releases"][0] if c["releases"] else str(c["id"]))
        if app_name == "sonarr" and detail:
            ep_num = detail.get("episodeNumber")
            season_num = detail.get("seasonNumber")
            scene_ep = detail.get("sceneEpisodeNumber")
            scene_season = detail.get("sceneSeasonNumber")
            scene_mismatch = bool(
                (scene_ep is not None and scene_ep != ep_num) or (scene_season is not None and scene_season != season_num)
            )
            title = f"{detail.get('series', {}).get('title', '')} S{season_num:02d}E{ep_num:02d} - {title}".strip(" -")
        else:
            scene_mismatch = False
        output_path = current_queue_output_path(app_name, c["id"], id_field)
        suffix_hit = dedup_suffix_hit(output_path)

        if not monitored:
            suggested, reason = "none", "Already unmonitored."
        elif suffix_hit:
            suggested, reason = "suffix-bug", "outputPath has a ' (N)' dedup suffix - NzbDAV's duplicate-nzb-behavior may have reverted to 'increment'. Check config, don't unmonitor."
        elif app_name == "sonarr" and series_counts.get(detail.get("seriesId"), 0) >= loop_review_profile_threshold:
            suggested, reason = "review-profile", f"{series_counts[detail.get('seriesId')]} episodes of this series are looping - check the quality profile/custom formats before mass-unmonitoring (Batwoman/Billions/Jack Ryan shape)."
        elif scene_mismatch:
            suggested, reason = "unmonitor", f"scene numbering mismatch (scene S{scene_season}E{scene_ep} vs Sonarr S{season_num:02d}E{ep_num:02d})."
        else:
            suggested, reason = "unmonitor", "genuine repeat failure, no known bug signature - scarcity or title/release mismatch."

        rows.append({
            "id": c["id"], "title": title, "occurrences": c["count"], "releases": c["releases"], "monitored": monitored,
            "has_file": has_file, "suggested_action": suggested, "reason": reason,
        })

    rows.sort(key=lambda r: r["occurrences"], reverse=True)
    return {"message": f"{cfg['label']}: {len(rows)} looping candidate(s) in the last {hours:g}h.",
            "app": app_name, "candidates": rows}


def unmonitor(app_name: str, ids: list[int]) -> dict:
    # Automation-invoked: stack-cli-arr-fleet skill's unmonitor command,
    # used from the loop-remediation toolkit's confirm-armed actions.
    cfg = require_queue_app(app_name)
    if not ids:
        raise ServiceError("No ids given.", status=400)
    if app_name in RADARR_APPS:
        payload = {"movieIds": ids, "monitored": False}
        url = f"{cfg['url']}/api/{cfg['api']}/movie/editor"
    else:
        payload = {"episodeIds": ids, "monitored": False}
        url = f"{cfg['url']}/api/{cfg['api']}/episode/monitor"
    try:
        r = httpx.put(url, json=payload, headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"Unmonitor failed: {e}") from e
    return {"message": f"Unmonitored {len(ids)} item(s) in {cfg['label']}.", "ids": ids}


def manual_import_candidates(app_name: str) -> list[dict]:
    cfg = require_queue_app(app_name)
    candidates = []
    for q in import_candidate_queue_items(app_name):
        folder, download_id = q.get("outputPath"), q.get("downloadId")
        if not folder or not download_id:
            continue
        try:
            r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/manualimport",
                           params={"folder": folder, "downloadId": download_id, "filterExistingFiles": "true"},
                           headers={"X-Api-Key": cfg["key"]}, timeout=30)
            r.raise_for_status()
        except httpx.HTTPError:
            continue
        for f in r.json():
            match = f.get("movie") or f.get("series") or f.get("author")
            episodes = f.get("episodes") or []
            file_payload = {
                "path": f.get("path"), "folderName": f.get("folderName"), "quality": f.get("quality"),
                "languages": f.get("languages"), "releaseGroup": f.get("releaseGroup"), "downloadId": f.get("downloadId"),
            }
            if app_name in RADARR_APPS:
                file_payload["movieId"] = match.get("id") if match else None
            elif app_name == "sonarr":
                file_payload["seriesId"] = (match or {}).get("id") or (episodes[0]["seriesId"] if episodes else None)
                file_payload["episodeIds"] = [e["id"] for e in episodes]
            episode_label = None
            if episodes:
                e = episodes[0]
                episode_label = f"S{e['seasonNumber']:02d}E{e['episodeNumber']:02d} - {e.get('title', '')}"
            candidates.append({
                "queue_title": q.get("title"), "name": f.get("name"), "relative_path": f.get("relativePath"),
                "size": human_size(f.get("size")), "quality": (f.get("quality") or {}).get("quality", {}).get("name"),
                "release_group": f.get("releaseGroup"), "rejections": [x.get("reason") for x in f.get("rejections", [])],
                "match_title": match.get("title") if match else None, "episode": episode_label, "file": file_payload,
            })
    return candidates


def manual_import_execute(app_name: str, payload: dict) -> str:
    # Automation-invoked: stack-cli-arr-fleet skill's manual-import command.
    cfg = require_queue_app(app_name)
    body = {"name": "ManualImport", "files": [payload]}
    try:
        r = httpx.post(f"{cfg['url']}/api/{cfg['api']}/command", json=body, headers={"X-Api-Key": cfg["key"]}, timeout=30)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise ServiceError(f"{cfg['label']} manual import failed: {e.response.text.strip() or e}")
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} manual import failed: {e}") from e
    name = payload["path"].rsplit("/", 1)[-1]
    return f'Import started for "{name}" in {cfg["label"]}.'


def manual_import_all(app_name: str) -> str:
    # Automation-invoked: stack-cli-arr-fleet skill's manual-import-all command.
    cfg = require_queue_app(app_name)
    id_field = "movieId" if app_name in RADARR_APPS else "seriesId"
    all_files = [c["file"] for c in manual_import_candidates(app_name)]
    files = [f for f in all_files if f.get(id_field) is not None]
    skipped = len(all_files) - len(files)
    if not files:
        msg = f"No importable files in {cfg['label']}."
        if skipped:
            msg += f" ({skipped} file(s) have no resolved match - needs Manual Import in the {cfg['label']} UI.)"
        return msg
    body = {"name": "ManualImport", "files": files}
    try:
        r = httpx.post(f"{cfg['url']}/api/{cfg['api']}/command", json=body, headers={"X-Api-Key": cfg["key"]}, timeout=30)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise ServiceError(f"{cfg['label']} bulk import failed: {e.response.text.strip() or e}")
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} bulk import failed: {e}") from e
    msg = f"Import started for {len(files)} file(s) in {cfg['label']}."
    if skipped:
        msg += f" ({skipped} file(s) skipped - no resolved match.)"
    return msg


def parse_air_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def missing_aired(app_name: str) -> list[dict]:
    if app_name not in ARR_APPS:
        raise ServiceError(f"Unknown app '{app_name}'.", status=404)
    cfg = ARR_APPS[app_name]

    if app_name in RADARR_APPS:
        try:
            r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie", headers={"X-Api-Key": cfg["key"]}, timeout=30)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ServiceError(f"{cfg['label']} movie lookup failed: {e}") from e
        results = []
        for m in r.json():
            if not m.get("monitored") or m.get("hasFile") or not m.get("isAvailable"):
                continue
            released = m.get("digitalRelease") or m.get("physicalRelease") or m.get("inCinemas")
            results.append({"title": m.get("title"), "year": m.get("year"), "aired": released})
        results.sort(key=lambda x: x["aired"] or "", reverse=True)
        return results

    cutoff = datetime.now(timezone.utc)
    results = []
    page = 1
    page_size = 250
    while True:
        try:
            r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/wanted/missing",
                           params={"page": page, "pageSize": page_size, "sortKey": "airDateUtc",
                                    "sortDirection": "ascending", "includeSeries": "true"},
                           headers={"X-Api-Key": cfg["key"]}, timeout=30)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ServiceError(f"{cfg['label']} missing lookup failed: {e}") from e
        data = r.json()
        records = data.get("records", [])
        if not records:
            break
        hit_future = False
        for ep in records:
            air = parse_air_date(ep.get("airDateUtc"))
            if air is None:
                continue
            if air > cutoff:
                hit_future = True
                break
            series = ep.get("series") or {}
            results.append({
                "series": series.get("title"), "episode": f"S{ep['seasonNumber']:02d}E{ep['episodeNumber']:02d}",
                "title": ep.get("title"), "aired": ep.get("airDateUtc"),
            })
        if hit_future or page * page_size >= data.get("totalRecords", 0):
            break
        page += 1
    results.sort(key=lambda x: x["aired"] or "", reverse=True)
    return results


def blocklist(app_name: str, limit: int = 50) -> dict:
    if app_name not in ARR_APPS:
        raise ServiceError(f"Unknown app '{app_name}'.", status=404)
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/blocklist",
                       params={"page": 1, "pageSize": limit, "sortKey": "date", "sortDirection": "descending"},
                       headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} blocklist lookup failed: {e}") from e
    data = r.json()
    records = [{"id": rec.get("id"), "title": rec.get("sourceTitle"), "date": rec.get("date"),
                "seriesId": rec.get("seriesId"), "movieId": rec.get("movieId")} for rec in data.get("records", [])]
    return {
        "message": f"{data.get('totalRecords', len(records))} total blocklist entry(ies) in {cfg['label']} ({len(records)} shown).",
        "total": data.get("totalRecords", len(records)), "records": records,
    }


def blocklist_clear(app_name: str) -> dict:
    # Automation-invoked: stack-cli-arr-fleet skill's blocklist-clear command.
    if app_name not in ARR_APPS:
        raise ServiceError(f"Unknown app '{app_name}'.", status=404)
    cfg = ARR_APPS[app_name]
    total_cleared = 0
    while True:
        try:
            r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/blocklist", params={"page": 1, "pageSize": 250},
                           headers={"X-Api-Key": cfg["key"]}, timeout=20)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ServiceError(f"{cfg['label']} blocklist lookup failed: {e}") from e
        ids = [rec["id"] for rec in r.json().get("records", [])]
        if not ids:
            break
        try:
            r = httpx.request("DELETE", f"{cfg['url']}/api/{cfg['api']}/blocklist/bulk", json={"ids": ids},
                               headers={"X-Api-Key": cfg["key"]}, timeout=20)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ServiceError(f"{cfg['label']} blocklist clear failed after removing {total_cleared}: {e}") from e
        total_cleared += len(ids)
    return {"message": f"Cleared {total_cleared} blocklist entry(ies) from {cfg['label']}.", "cleared": total_cleared}


def backlog_status() -> dict:
    result = {}
    for app_name in QUEUE_ARR_APPS:
        cfg = ARR_APPS[app_name]
        try:
            missing = wanted_missing_total(app_name)
            rate_per_hour, sample_count = recent_import_rate_per_hour(app_name)
        except ServiceError:
            result[app_name] = {"label": cfg["label"], "error": "unreachable"}
            continue
        item = {"label": cfg["label"], "missing": missing, "recent_imports_sampled": sample_count,
                 "rate_per_hour": round(rate_per_hour, 2)}
        if missing == 0:
            item["eta"] = "none - nothing missing"
        elif rate_per_hour > 0:
            item["eta"] = format_eta((missing / rate_per_hour) * 3600)
        else:
            item["eta"] = f"unknown - no imports in the last {RECENT_IMPORT_LOOKBACK_HOURS}h to measure a rate from"
        result[app_name] = item

    total_missing = sum(v.get("missing", 0) for v in result.values())
    return {"message": f"{total_missing} item(s) missing across {len(result)} apps.", "apps": result}


def logs(app_name: str, lines: int = 100) -> str:
    if app_name not in ARR_LOG_CONTAINERS:
        raise ServiceError(
            f"Unknown app '{app_name}' - use one of: {', '.join(sorted(ARR_LOG_CONTAINERS))}", status=400
        )
    try:
        c = docker_client.containers.get(app_name)
        return c.logs(tail=min(lines, 1000), timestamps=True).decode(errors="replace")
    except docker.errors.NotFound:
        raise ServiceError(f"Container '{app_name}' not found.")


def command_queue_summary() -> dict:
    out = {}
    for name, cfg in {**ARR_APPS, "prowlarr": PROWLARR_CFG}.items():
        try:
            r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/command", headers={"X-Api-Key": cfg["key"]}, timeout=20)
            r.raise_for_status()
            commands = r.json()
            counts = Counter(c.get("status") for c in commands)
            out[name] = {"total": len(commands), "queued": counts.get("queued", 0), "running": counts.get("started", 0)}
        except httpx.HTTPError as e:
            out[name] = {"error": str(e)}
    total_queued = sum(v.get("queued", 0) for v in out.values() if "error" not in v)
    return {"message": f"{total_queued} commands queued across {len(out)} apps.", "apps": out}


def recently_added(app_name: str, limit: int = 10) -> dict:
    if app_name not in ARR_APPS:
        raise ServiceError(f"Unknown app '{app_name}' - use one of: {', '.join(sorted(ARR_APPS))}", status=400)
    cfg = ARR_APPS[app_name]
    path = "/api/v3/movie" if app_name in RADARR_APPS else "/api/v3/series"
    try:
        r = httpx.get(f"{cfg['url']}{path}", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} lookup failed: {e}") from e
    items = sorted(r.json(), key=lambda i: i.get("added") or "", reverse=True)[:limit]
    out = []
    for i in items:
        stats = i.get("statistics") or {}
        out.append({
            "title": i.get("title"), "added": i.get("added"), "monitored": i.get("monitored"),
            "file_count": stats.get("movieFileCount") if app_name == "radarr" else stats.get("episodeFileCount"),
            "total_count": None if app_name == "radarr" else stats.get("episodeCount"),
        })
    return {"message": f"{len(out)} most recently added to {cfg['label']}.", "items": out}


def queue_errors() -> dict:
    out = {}
    for app_name in QUEUE_ARR_APPS:
        try:
            queue = arr_queue(app_name)
        except ServiceError:
            out[app_name] = {"error": "lookup failed"}
            continue
        errors = [{"title": q.get("title"), "status": q.get("trackedDownloadStatus"),
                   "messages": [m.get("title") for m in (q.get("statusMessages") or [])]}
                  for q in queue if (q.get("trackedDownloadStatus") or "ok").lower() != "ok"]
        out[app_name] = errors
    total = sum(len(v) for v in out.values() if isinstance(v, list))
    return {"message": f"{total} queue item(s) flagged with an error/warning across {len(out)} apps.", "apps": out}


def cutoff_unmet(app_name: str, limit: int = 20) -> dict:
    if app_name not in ARR_APPS:
        raise ServiceError(f"Unknown app '{app_name}' - use one of: {', '.join(sorted(ARR_APPS))}", status=400)
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/wanted/cutoff", params={"pageSize": limit, "sortKey": "title"},
                       headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} lookup failed: {e}") from e
    data = r.json()
    items = [{"title": rec.get("title") or rec.get("series", {}).get("title")} for rec in data.get("records", [])]
    return {"message": f"{data.get('totalRecords', len(items))} item(s) below quality cutoff in {cfg['label']}.",
            "items": items, "total": data.get("totalRecords")}


def import_lists(app_name: str) -> dict:
    if app_name not in ARR_APPS:
        raise ServiceError(f"Unknown app '{app_name}' - use one of: {', '.join(sorted(ARR_APPS))}", status=400)
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/importlist", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} lookup failed: {e}") from e
    items = [{"name": lst.get("name"), "enabled": lst.get("enabled"), "enableAutomaticAdd": lst.get("enableAutomaticAdd")}
             for lst in r.json()]
    return {"message": f"{len(items)} import list(s) configured for {cfg['label']}.", "items": items}


def import_list_implementations(app_name: str) -> dict:
    if app_name not in ARR_APPS:
        raise ServiceError(f"Unknown app '{app_name}' - use one of: {', '.join(sorted(ARR_APPS))}", status=400)
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/importlist/schema", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} lookup failed: {e}") from e
    items = sorted({s["implementation"]: s.get("implementationName", s["implementation"]) for s in r.json()}.items())
    return {"message": f"{len(items)} import-list implementation(s) available on {cfg['label']}.",
            "items": [{"implementation": k, "name": v} for k, v in items]}


def import_list_add(app_name: str, payload: dict) -> dict:
    # Automation-invoked by stack-plex-import-rss.fish,
    # stack-plex-import-watchlist.fish, stack-radarr-import-list.fish,
    # stack-sonarr-import-custom-list.fish, stack-tmdb-import-company.fish,
    # stack-tmdb-import-keyword.fish, and stack-trakt-import-list.fish via
    # __stack_api's service key (2026-08-06) - keep default tier.
    if app_name not in ARR_APPS:
        raise ServiceError(f"Unknown app '{app_name}' - use one of: {', '.join(sorted(ARR_APPS))}", status=400)
    cfg = ARR_APPS[app_name]
    try:
        schemas = httpx.get(f"{cfg['url']}/api/{cfg['api']}/importlist/schema", headers={"X-Api-Key": cfg["key"]}, timeout=20).json()
        folders = httpx.get(f"{cfg['url']}/api/{cfg['api']}/rootfolder", headers={"X-Api-Key": cfg["key"]}, timeout=20).json()
        profiles = httpx.get(f"{cfg['url']}/api/{cfg['api']}/qualityprofile", headers={"X-Api-Key": cfg["key"]}, timeout=20).json()
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} lookup failed: {e}") from e
    template = next((s for s in schemas if s["implementation"] == payload["implementation"]), None)
    if template is None:
        raise ServiceError(f"Unknown import-list implementation '{payload['implementation']}' for {cfg['label']}.", status=400)
    if not folders or not profiles:
        raise ServiceError(f"{cfg['label']} has no root folder / quality profile configured.")

    body = dict(template)
    body["name"] = payload["name"]
    body["enabled"] = True
    body["rootFolderPath"] = folders[0]["path"]
    body["qualityProfileId"] = profiles[0]["id"]
    if app_name == "radarr":
        body["enableAuto"] = True
        body["searchOnAdd"] = payload["search_on_add"]
        body["monitor"] = payload.get("monitor") or "movieOnly"
        body["minimumAvailability"] = payload["minimum_availability"]
    else:
        body["enableAutomaticAdd"] = True
        body["searchForMissingEpisodes"] = payload["search_on_add"]
        body["shouldMonitor"] = payload.get("monitor") or "all"
        body["monitorNewItems"] = payload.get("monitor") or "all"
    field_values = dict(payload["fields"])
    if payload["implementation"] == "PlexImport" and "accessToken" not in field_values:
        plex_token = os.environ.get("PLEX_TOKEN")
        if plex_token:
            field_values["accessToken"] = plex_token

    oauth_families = ("Trakt", "Simkl", "TMDbUser")
    family = next((f for f in oauth_families if payload["implementation"].startswith(f)), None)
    if family:
        oauth_field_names = {"accessToken", "refreshToken", "expires", "authUser"}
        try:
            existing_lists = httpx.get(f"{cfg['url']}/api/{cfg['api']}/importlist",
                                       headers={"X-Api-Key": cfg["key"]}, timeout=20).json()
        except httpx.HTTPError as e:
            raise ServiceError(f"{cfg['label']} lookup failed: {e}") from e
        donor = next(
            (lst for lst in existing_lists
             if lst["implementation"].startswith(family)
             and any(f["name"] == "accessToken" and f.get("value") for f in lst["fields"])),
            None,
        )
        if donor:
            for f in donor["fields"]:
                if f["name"] in oauth_field_names and f["name"] not in field_values:
                    field_values[f["name"]] = f.get("value")
        elif not any(k in field_values for k in oauth_field_names):
            raise ServiceError(
                f"No existing {family}-authenticated import list found on {cfg['label']} to reuse a token from - "
                f"authenticate one list of this type through {cfg['label']}'s own UI first (Settings -> Import Lists "
                f"-> Add -> {payload['implementation']}'s \"Authenticate\" button), then this endpoint can reuse it "
                f"for every list after.", status=409,
            )

    body["fields"] = [dict(f, value=field_values[f["name"]]) if f["name"] in field_values else f
                       for f in template["fields"]]

    try:
        r = httpx.post(f"{cfg['url']}/api/{cfg['api']}/importlist", json=body, headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise ServiceError(f"{cfg['label']} import-list creation failed: {e.response.text.strip() or e}")
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} import-list creation failed: {e}") from e
    return {"message": f"Import list '{payload['name']}' ({payload['implementation']}) added to {cfg['label']}.",
            "id": r.json().get("id")}


def customformat_snapshot(app_name: str) -> dict:
    if app_name not in ARR_APPS:
        raise ServiceError(f"Unknown app '{app_name}' - use one of: {', '.join(sorted(ARR_APPS))}", status=400)
    cfg = ARR_APPS[app_name]
    try:
        cf = httpx.get(f"{cfg['url']}/api/{cfg['api']}/customformat", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        cf.raise_for_status()
        profiles = httpx.get(f"{cfg['url']}/api/{cfg['api']}/qualityprofile", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        profiles.raise_for_status()
    except httpx.HTTPError as e:
        raise ServiceError(f"{cfg['label']} lookup failed: {e}") from e
    cf_names = {c["id"]: c["name"] for c in cf.json()}
    snapshot = {}
    for profile in profiles.json():
        snapshot[profile["name"]] = {cf_names.get(item["format"], str(item["format"])): item["score"]
                                      for item in profile["formatItems"]}
    return {"message": f"{len(cf_names)} custom format(s) across {len(snapshot)} profile(s) on {cfg['label']}.",
            "profiles": snapshot}

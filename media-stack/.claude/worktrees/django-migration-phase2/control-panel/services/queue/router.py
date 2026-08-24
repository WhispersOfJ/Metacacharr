"""Cross-app download-queue aggregation, ported from app.py (lines ~2944-3450) -
this route was missed during the Phase 3/5 backend migration (evolved-control-panel-backend
plan) and 404'd in production until this port; stack-queue-status was broken the whole time.

Samples every source's remaining-size/progress twice, QUEUE_SAMPLE_SECONDS apart, and
buckets each item into downloading/stalled/queued/importing using the *observed* delta
rather than trusting each app's own (frequently wrong) timeleft/progress reporting.
"""
import time

from fastapi import APIRouter, Depends, HTTPException

from core.api_hit_counts import install as install_hit_counter
from core.arr_client import ARR_APPS, QUEUE_ARR_APPS, arr_queue, format_eta, human_size
from core.nzbdav_client import nzbdav_api
from core.responses import ok
from core.security import current_user_or_service
from services.plex.router import plex_activities, plex_progress_snapshot

router = APIRouter(tags=["queue"])

install_hit_counter()

QUEUE_SAMPLE_SECONDS = 4


def _arr_sizeleft_snapshot(app_name: str) -> dict[int, int]:
    try:
        records = arr_queue(app_name)
    except HTTPException:
        return {}
    return {q["id"]: q.get("sizeleft") or 0 for q in records if q.get("sizeleft")}


def _nzbdav_mbleft_snapshot() -> dict[str, float]:
    try:
        slots = nzbdav_api("queue").get("queue", {}).get("slots", [])
    except HTTPException:
        return {}
    return {s["nzo_id"]: float(s.get("mbleft") or 0) for s in slots if s.get("status") == "Downloading"}


def _bucket_arr_item(q: dict, prev_sizeleft: dict[int, int]) -> tuple[str, dict]:
    title = q.get("title") or "?"
    size = q.get("size") or 0
    sizeleft = q.get("sizeleft") or 0
    item = {"title": title, "size": human_size(size)}
    if sizeleft > 0:
        item["size_left"] = human_size(sizeleft)
    if q.get("trackedDownloadState") in ("importPending", "importBlocked"):
        item["note"] = "fully fetched, waiting on import"
        return "importing", item
    if sizeleft <= 0:
        item["note"] = "queued, not yet started"
        return "queued", item
    prev = prev_sizeleft.get(q["id"])
    if prev is not None and prev > sizeleft:
        speed = (prev - sizeleft) / QUEUE_SAMPLE_SECONDS
        eta = sizeleft / speed if speed > 0 else float("inf")
        item["speed"] = f"{human_size(speed)}/s"
        item["eta"] = format_eta(eta)
        return "downloading", item
    item["note"] = "no progress observed (still caching, or stalled)"
    return "stalled", item


def _bucket_nzbdav_item(s: dict, prev_mbleft: dict[str, float]) -> tuple[str, dict]:
    title = s.get("filename") or "?"
    mb = float(s.get("mb") or 0)
    mbleft = float(s.get("mbleft") or 0)
    item = {"title": title, "size": f"{mb:.0f} MB", "size_left": f"{mbleft:.0f} MB"}
    if s.get("status") != "Downloading" or mbleft <= 0:
        item["note"] = "queued, not yet started" if mbleft > 0 else "fully fetched, waiting on import"
        return ("queued" if mbleft > 0 else "importing"), item
    prev = prev_mbleft.get(s["nzo_id"])
    if prev is not None and prev > mbleft:
        speed_mb = (prev - mbleft) / QUEUE_SAMPLE_SECONDS
        eta = mbleft / speed_mb if speed_mb > 0 else float("inf")
        item["speed"] = f"{speed_mb:.1f} MB/s"
        item["eta"] = format_eta(eta)
        return "downloading", item
    item["note"] = "no progress observed (still caching, or stalled)"
    return "stalled", item


def _bucket_plex_activity(a: dict, prev_progress: dict[str, int]) -> tuple[str, dict]:
    title = a.get("title") or "?"
    if a.get("subtitle"):
        title = f"{title}: {a['subtitle']}"
    progress = a.get("progress", 0)
    item = {"title": title, "progress": f"{progress}%"}
    prev = prev_progress.get(a["uuid"])
    if prev is not None and progress > prev:
        rate = (progress - prev) / QUEUE_SAMPLE_SECONDS  # percent per second
        eta = (100 - progress) / rate if rate > 0 else float("inf")
        item["eta"] = format_eta(eta)
        return "downloading", item
    item["note"] = "no progress observed (large section, or genuinely stalled)"
    return "stalled", item


@router.get("/api/queue-status")
def queue_status(_=Depends(current_user_or_service)):
    """Every *arr app's download queue plus NzbDAV's and Plex's own
    background activities (library scans, media analysis, etc), bucketed
    into downloading/stalled/queued/importing with a real speed/progress
    and ETA for anything actually observed to be draining - see the
    module comment above for why this measures live instead of trusting
    each app's own timeleft."""
    before_arr = {app_name: _arr_sizeleft_snapshot(app_name) for app_name in QUEUE_ARR_APPS}
    before_nzbdav = _nzbdav_mbleft_snapshot()
    before_plex = plex_progress_snapshot()
    time.sleep(QUEUE_SAMPLE_SECONDS)

    result = {}
    grand_total = 0
    for app_name in QUEUE_ARR_APPS:
        cfg = ARR_APPS[app_name]
        try:
            records = arr_queue(app_name)
        except HTTPException:
            result[app_name] = {"label": cfg["label"], "error": "unreachable"}
            continue
        buckets = {"downloading": [], "stalled": [], "queued": [], "importing": []}
        for q in records:
            bucket, item = _bucket_arr_item(q, before_arr[app_name])
            buckets[bucket].append(item)
        grand_total += len(records)
        result[app_name] = {"label": cfg["label"], "total": len(records), **buckets}

    try:
        slots = nzbdav_api("queue").get("queue", {}).get("slots", [])
        buckets = {"downloading": [], "stalled": [], "queued": [], "importing": []}
        for s in slots:
            bucket, item = _bucket_nzbdav_item(s, before_nzbdav)
            buckets[bucket].append(item)
        grand_total += len(slots)
        result["nzbdav"] = {"label": "NzbDAV", "total": len(slots), **buckets}
    except HTTPException:
        result["nzbdav"] = {"label": "NzbDAV", "error": "unreachable"}

    try:
        activities = plex_activities()
        buckets = {"downloading": [], "stalled": [], "queued": [], "importing": []}
        for a in activities:
            bucket, item = _bucket_plex_activity(a, before_plex)
            buckets[bucket].append(item)
        grand_total += len(activities)
        result["plex"] = {"label": "Plex", "total": len(activities), **buckets}
    except HTTPException:
        result["plex"] = {"label": "Plex", "error": "unreachable"}

    active = sum(len(v.get("downloading", [])) for v in result.values())
    return ok(
        f"{grand_total} item(s) across {len(result)} queues, {active} actively downloading.",
        queues=result,
    )

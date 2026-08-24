"""Cleanuparr routes, ported from app.py (lines ~4404-4425, ~4701-4722) -
migration gap closed after the auth cutover left these two routes 404ing
(they were never given a services/<name>/router.py, so main.py's
auto-discovery never mounted them - see the stack-cleanuparr-strikes fix
that surfaced this).

Both routes are read-only - current_user_or_service throughout, same
reasoning as the other sqlite-reading routes.
"""
import os
import sqlite3

from core.host_paths import HOST_CONFIG_DIR
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends

router = APIRouter(tags=["cleanuparr"])

SERVICE_META = {"label": "Cleanuparr", "health_check": None}


@router.get("/api/cleanuparr/instances")
def cleanuparr_instances(_=Depends(current_user_or_service)):
    """Which *arr apps Cleanuparr actually has a connected arr_instance for,
    vs. just an arr_configs type placeholder - the exact gap that historically
    left Lidarr and Whisparr (both since removed) completely uncovered by
    queue-cleaning/strikes despite both apps being fully functional at the
    time."""
    db_path = os.path.join(HOST_CONFIG_DIR, "cleanuparr", "cleanuparr.db")
    if not os.path.isfile(db_path):
        fail(f"{db_path} not present.")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT type FROM arr_configs")
    configured_types = {row["type"] for row in cur.fetchall()}
    cur.execute("SELECT name FROM arr_instances")
    connected = {row["name"].lower() for row in cur.fetchall()}
    con.close()
    gaps = sorted(t for t in configured_types if t not in connected and t != "readarr")
    if not gaps:
        return ok("Every configured app type has a connected instance.", connected=sorted(connected))
    return ok(f"{len(gaps)} app(s) have a config placeholder but no connected instance: {', '.join(gaps)}",
              connected=sorted(connected), gaps=gaps)


@router.get("/api/cleanuparr/strikes")
def cleanuparr_strikes(limit: int = 15, _=Depends(current_user_or_service)):
    """Recent strikes Cleanuparr has issued (stalled/slow/malware) - lives
    in events.db, a separate SQLite file from the arr_instances/arr_configs
    one cleanuparr_instances() above reads (Cleanuparr splits its own state
    across cleanuparr.db and events.db)."""
    db_path = os.path.join(HOST_CONFIG_DIR, "cleanuparr", "events.db")
    if not os.path.isfile(db_path):
        fail(f"{db_path} not present.")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        "SELECT s.created_at, s.type, d.title FROM strikes s "
        "JOIN download_items d ON d.id = s.download_item_id "
        "ORDER BY s.created_at DESC LIMIT ?", (limit,)
    )
    rows = [{"created_at": r["created_at"], "type": r["type"], "title": r["title"]} for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) FROM strikes")
    total = cur.fetchone()[0]
    con.close()
    return ok(f"{total} strike(s) total, showing {len(rows)} most recent.", items=rows, total=total)

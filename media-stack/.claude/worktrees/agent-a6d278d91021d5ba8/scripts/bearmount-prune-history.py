#!/usr/bin/env python3
"""Deletes every "Failed" entry from NzbDAV's SABnzbd-compatible history.

Same rationale this stack's now-removed NzbDAV (nzbdav-dev) prune script had
originally, then AltMount's, then BearMount's before nzbdav/nzbdav replaced
that too (2026-07-28, see STACK.md's History): a Failed history row has no
surviving output but can still block re-grabbing a matching release name,
so there's no reason to keep one once logged - safe to delete
unconditionally, regardless of age.

Filename/unit kept as "bearmount-prune-history" rather than renamed - the
installed systemd symlinks at ~/.config/systemd/user point at this exact
path, and renaming would break them without a separate out-of-repo fix.

Run every few hours by systemd/stack-bearmount-prune-history.{service,timer}.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

STACK_DIR = Path(__file__).resolve().parent.parent
# NzbDAV's SABnzbd-compatible API lives at the root /api (no prefix, unlike
# BearMount's Fiber router which mounted it under /sabnzbd).
NZBDAV_URL = "http://localhost:3000/api"


def env_get(key):
    env_path = STACK_DIR / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


# NzbDAV shares one key (FRONTEND_BACKEND_API_KEY) across its frontend
# proxy, SAB API, and admin API - unlike BearMount's separate
# BEARMOUNT_API_KEY.
NZBDAV_API_KEY = env_get("FRONTEND_BACKEND_API_KEY")

# Deletes fan out across threads rather than running serially - these are
# same-host HTTP calls, not a remote/rate-limited API. History can run in
# the tens of thousands of entries on this stack.
WORKERS = 20


def api_get(params, timeout=30):
    url = f"{NZBDAV_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def delete_one(slot):
    nzo_id = slot["nzo_id"]
    try:
        result = api_get({
            "mode": "history",
            "name": "delete",
            "value": nzo_id,
            "apikey": NZBDAV_API_KEY,
            "output": "json",
        })
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return False, f"failed to delete {nzo_id} ({slot.get('name')}): {e}"
    if result.get("status"):
        return True, None
    return False, f"delete rejected for {nzo_id} ({slot.get('name')}): {result.get('error')}"


def main():
    if not NZBDAV_API_KEY or NZBDAV_API_KEY == "changeme":
        print("NZBDAV_API_KEY not configured in .env", file=sys.stderr)
        return 1

    history = api_get({
        "mode": "history",
        "limit": 0,
        "apikey": NZBDAV_API_KEY,
        "output": "json",
    }, timeout=180)
    slots = history.get("history", {}).get("slots", [])
    failed = [s for s in slots if s.get("status") == "Failed"]

    deleted = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(delete_one, slot) for slot in failed]
        for future in as_completed(futures):
            ok, message = future.result()
            if ok:
                deleted += 1
            else:
                print(message, file=sys.stderr)
                errors += 1

    print(f"pruned {deleted}/{len(failed)} failed history entries ({errors} errors)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

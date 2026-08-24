#!/usr/bin/env python3
"""Triggers the diff-only Letterboxd tracked-list sync
(POST /api/arr/letterboxd/sync-tick) and blocks until it returns, so the
systemd unit's exit status is meaningful. Control Panel owns the actual
sync logic (services/letterboxd/router.py's letterboxd_sync_tick) - this
script is just a scriptable, authenticated client of its HTTP API, same
relationship every other scripts/*.py has to the container it drives.

Unlike scripts/poster-sync-fanart.py (which sends no auth header at all),
this script sends the X-Api-Key header that letterboxd_sync_tick's
current_user_or_service dependency requires - the same
CONTROL_PANEL_SERVICE_API_KEY .env value fish-functions/__stack_api.fish
uses for every other unattended stack-* call.

Run by systemd/stack-letterboxd-sync.{service,timer} - nightly.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

CONTROL_PANEL_URL = "http://localhost:8420"
DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _service_key() -> str | None:
    env_file = Path(os.environ.get("LETTERBOXD_SYNC_ENV_FILE", DEFAULT_ENV_FILE))
    if not env_file.is_file():
        return None
    for line in env_file.read_text().splitlines():
        if line.startswith("CONTROL_PANEL_SERVICE_API_KEY="):
            return line.split("=", 1)[1].strip()
    return None


def main() -> int:
    key = _service_key()
    if not key:
        print("No CONTROL_PANEL_SERVICE_API_KEY found in .env - can't authenticate.", file=sys.stderr)
        return 1

    req = urllib.request.Request(
        f"{CONTROL_PANEL_URL}/api/arr/letterboxd/sync-tick", data=b"{}",
        headers={"Content-Type": "application/json", "X-Api-Key": key}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3600) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = json.loads(e.read()).get("detail", {})
        print(f"sync-tick failed: {detail.get('message', str(e))}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"failed to reach Control Panel: {e}", file=sys.stderr)
        return 1

    print(body.get("message"))
    for result in body.get("results", []):
        added = len(result.get("added", []))
        failed = len(result.get("failed", []))
        print(f"  {result['url']}: {added} added, {failed} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

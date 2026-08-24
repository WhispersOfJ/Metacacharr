#!/usr/bin/env python3
"""Triggers each *arr app's own native Backup command (POST /api/v3/command
name=Backup). This produces the same .zip an app's own Settings -> Backup
screen creates on demand - portable across a version upgrade in a way a
raw SQLite file copy taken mid-write isn't guaranteed to be, and it's what
each app's own restore flow expects as input.

Scoped to Radarr and Sonarr - this repo's own established meaning of "the
arr apps" (see control-panel/app.py's ARR_APPS), which no longer includes
Lidarr/Readarr as of their removal. Prowlarr/Bazarr both have an equivalent
native backup mechanism too, but neither is "an arr app" by that same
convention, so both are left out here on purpose.

Run daily by systemd/stack-arr-backup.{service,timer}.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

STACK_DIR = Path(__file__).resolve().parent.parent
DISCORD_GREEN = 0x57F287
DISCORD_RED = 0xED4245

# Command polling: each app's own backup zip is small (a few MB at most,
# see backup-config.sh's exclusions for why the raw config dir is so much
# bigger), so this normally completes in seconds - but a 60s timeout was
# confirmed too tight live: Sonarr's own instance tracks ~300k episode
# records, and both apps have been observed at 80-111% CPU around backup
# time (03:40 daily), which pushes the native Backup command itself past
# 60s. Raised with real headroom rather than tightened further.
POLL_INTERVAL_SECONDS = 3
POLL_TIMEOUT_SECONDS = 240


def env_get(key):
    env_path = STACK_DIR / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


DISCORD_WEBHOOK_URL = env_get("DISCORD_WEBHOOK_URL")
HOST_LABEL = env_get("HOST_IP") or "Stack"

APPS = {
    "radarr": {"url": "http://localhost:7878", "key": env_get("RADARR_API_KEY"), "label": "Radarr"},
    "sonarr": {"url": "http://localhost:8989", "key": env_get("SONARR_API_KEY"), "label": "Sonarr"},
}


def api_request(base_url, api_key, method, path, body=None):
    url = f"{base_url}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def trigger_backup(app_name, cfg):
    """Starts the app's own Backup command and polls until it finishes.
    Returns (ok: bool, detail: str)."""
    if not cfg["key"] or cfg["key"] == "changeme":
        return False, f"{cfg['label']} API key not configured in .env"
    try:
        command = api_request(cfg["url"], cfg["key"], "POST", "/api/v3/command", {"name": "Backup"})
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        return False, f"{cfg['label']} backup failed to start: {e}"

    command_id = command.get("id")
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    status = command.get("status")
    while status not in ("completed", "failed") and time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        try:
            command = api_request(cfg["url"], cfg["key"], "GET", f"/api/v3/command/{command_id}")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            return False, f"{cfg['label']} backup status check failed: {e}"
        status = command.get("status")

    if status == "completed":
        return True, f"{cfg['label']} backup completed"
    if status == "failed":
        return False, f"{cfg['label']} backup failed: {command.get('message', 'no error message given')}"
    return False, f"{cfg['label']} backup still {status!r} after {POLL_TIMEOUT_SECONDS}s - not waiting longer"


def post_discord(embed):
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "changeme":
        print("DISCORD_WEBHOOK_URL not configured, skipping notification", file=sys.stderr)
        return
    payload = json.dumps({"embeds": [embed]}).encode()
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "media-stack-arr-backup/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15):
        pass


def main():
    results = [trigger_backup(name, cfg) for name, cfg in APPS.items()]
    ok_count = sum(1 for ok, _ in results if ok)
    lines = [detail for _, detail in results]

    embed = {
        "title": "*arr App Backups",
        "description": "\n".join(f"{'✅' if ok else '❌'} {detail}" for ok, detail in results),
        "footer": {"text": HOST_LABEL},
        "color": DISCORD_GREEN if ok_count == len(results) else DISCORD_RED,
    }
    post_discord(embed)

    for line in lines:
        print(line)
    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

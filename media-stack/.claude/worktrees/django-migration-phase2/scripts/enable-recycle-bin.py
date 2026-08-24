#!/usr/bin/env python3
"""One-off: enables every Servarr app's own Recycle Bin so a repeat of the
unexplained mass-deletion event (see README.md's Known gaps and limitations
section) lands recoverable content in a real folder instead of disappearing
outright. Not a fix for that event's still-unknown root cause - a
blast-radius mitigation.

Each app's recycle bin lives inside its own writable root (/data/movies,
/data/shows, /data/music, /data/adult) rather than a new bind mount, so
every app can hardlink into it instead of copying. Not a recurring job -
run once, or again after a config reset. Reuses the env_get()/api_request()
pattern from arr-app-backup.py.
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

STACK_DIR = Path(__file__).resolve().parent.parent


def env_get(key):
    env_path = STACK_DIR / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


APPS = {
    "radarr": {
        "url": "http://localhost:7878", "key": env_get("RADARR_API_KEY"), "label": "Radarr",
        "recycle_bin": "/data/movies/.recyclebin", "host_recycle_bin": STACK_DIR / "media/movies/.recyclebin",
        "api_version": "v3",
    },
    "sonarr": {
        "url": "http://localhost:8989", "key": env_get("SONARR_API_KEY"), "label": "Sonarr",
        "recycle_bin": "/data/shows/.recyclebin", "host_recycle_bin": STACK_DIR / "media/shows/.recyclebin",
        "api_version": "v3",
    },
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


def enable_recycle_bin(app_name, cfg):
    if not cfg["key"] or cfg["key"] == "changeme":
        return False, f"{cfg['label']} API key not configured in .env"
    api = cfg["api_version"]
    try:
        current = api_request(cfg["url"], cfg["key"], "GET", f"/api/{api}/config/mediamanagement")
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        return False, f"{cfg['label']} config read failed: {e}"

    if current.get("recycleBin"):
        return True, f"{cfg['label']} recycle bin already set ({current['recycleBin']}), left alone"

    # Every app here validates the path exists and is writable before
    # accepting it - PUID/PGID-owned already via the same host directory
    # each app's root folder already lives under, so no chown needed.
    cfg["host_recycle_bin"].mkdir(parents=True, exist_ok=True)

    current["recycleBin"] = cfg["recycle_bin"]
    current.setdefault("recycleBinCleanupDays", 7)
    try:
        api_request(cfg["url"], cfg["key"], "PUT", f"/api/{api}/config/mediamanagement/1", current)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        return False, f"{cfg['label']} config write failed: {e}"
    return True, f"{cfg['label']} recycle bin set to {cfg['recycle_bin']} (cleanup after {current['recycleBinCleanupDays']}d)"


def main():
    results = [enable_recycle_bin(name, cfg) for name, cfg in APPS.items()]
    for ok, detail in results:
        print(("OK  " if ok else "FAIL") + " " + detail)
    return 0 if all(ok for ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())

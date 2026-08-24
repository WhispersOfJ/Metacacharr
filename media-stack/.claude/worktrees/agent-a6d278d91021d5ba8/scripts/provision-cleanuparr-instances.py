#!/usr/bin/env python3
"""Provisions Cleanuparr's Arr instances and Seeker settings from this repo.

Why this exists: Cleanuparr keeps its entire Arr wiring in
config/cleanuparr/cleanuparr.db and nothing else. There is no config file,
no env var, no compose entry - so a rebuilt or restored DB silently drops
whatever was configured through the UI, with no error and no log line. That
already bit this stack once: radarr-anime and sonarr-anime ran with ZERO
Cleanuparr coverage (no stall/slow/failed-import strikes at all) purely
because nobody re-added them, and the containers being healthy and network-
reachable made it invisible. Reachability is not coverage.

Idempotent by design: existing instances are matched on name and updated,
missing ones are created, and nothing is ever deleted. Safe to run on every
deploy and safe to run twice in a row.

Usage:
    python3 scripts/provision-cleanuparr-instances.py [--dry-run]
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

STACK_DIR = Path(__file__).resolve().parent.parent
CLEANUPARR_URL = "http://localhost:11011/api/configuration"

# Cleanuparr groups instances under one config per app TYPE (all Radarr
# instances live under "radarr"), so anime peers are extra instances of the
# same type, not new types. "version" is a REQUIRED field the API rejects
# the request without - and it 200s on a config-level PUT while silently
# discarding an appended instance, so instances must go through the
# dedicated /instances endpoint instead.
INSTANCES = [
    {"type": "radarr", "name": "Radarr", "url": "http://radarr:7878/",
     "key_env": "RADARR_API_KEY", "version": 6},
    {"type": "sonarr", "name": "Sonarr", "url": "http://sonarr:8989/",
     "key_env": "SONARR_API_KEY", "version": 4},
]

# Seeker is the stack's only paced missing-content hunter. Left off, missing
# items need manual bulk searches, and a bulk search is what starves
# RefreshMonitoredDownloads and stops all imports (see the
# arr-import-starvation-diagnosis skill). activeDownloadLimit is the throttle
# that makes it safe where a manual mass-search is not.
SEEKER_INSTANCE_DEFAULTS = {
    "enabled": True,
    "activeDownloadLimit": 3,
    "minCycleTimeDays": 1,
    "monitoredOnly": True,
    "useCutoff": True,
    "useCustomFormatScore": True,
}
# proactiveSearchEnabled stays off deliberately: it searches for content
# before release, which is a different behavior from filling known gaps.
SEEKER_GLOBAL = {"searchEnabled": True, "proactiveSearchEnabled": False}


def env_get(key):
    env_path = STACK_DIR / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


def request(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{CLEANUPARR_URL}/{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw.strip() else {}


def provision_instances(dry_run):
    created, updated, failed = [], [], []
    for spec in INSTANCES:
        api_key = env_get(spec["key_env"])
        if not api_key:
            failed.append(f"{spec['name']}: {spec['key_env']} missing from .env")
            continue

        payload = {"enabled": True, "name": spec["name"], "url": spec["url"],
                   "apiKey": api_key, "version": spec["version"]}
        existing = next((i for i in request("GET", spec["type"])["instances"]
                         if i["name"] == spec["name"]), None)

        if dry_run:
            (updated if existing else created).append(spec["name"])
            continue

        try:
            request("POST", f"{spec['type']}/instances/test", payload)
        except urllib.error.HTTPError as e:
            failed.append(f"{spec['name']}: connection test failed ({e.code})")
            continue

        try:
            if existing:
                request("PUT", f"{spec['type']}/instances/{existing['id']}", payload)
                updated.append(spec["name"])
            else:
                request("POST", f"{spec['type']}/instances", payload)
                created.append(spec["name"])
        except urllib.error.HTTPError as e:
            failed.append(f"{spec['name']}: {e.code} {e.read().decode()[:120]}")

    return created, updated, failed


def provision_seeker(dry_run):
    """Runs after instances: Cleanuparr auto-creates a Seeker row per Arr
    instance, but disabled and with a 7-day cycle, so a newly added instance
    is present-but-inert until this enables it."""
    try:
        cfg = request("GET", "seeker")
    except urllib.error.HTTPError as e:
        print(f"FAILED: seeker config fetch failed ({e.code})", file=sys.stderr)
        return []
    cfg.update(SEEKER_GLOBAL)
    for instance in cfg.get("instances", []):
        instance.update(SEEKER_INSTANCE_DEFAULTS)
    if not dry_run:
        request("PUT", "seeker", cfg)
    return [i["instanceName"] for i in cfg.get("instances", [])]


def main():
    dry_run = "--dry-run" in sys.argv
    prefix = "[dry-run] " if dry_run else ""

    created, updated, failed = provision_instances(dry_run)
    for name in created:
        print(f"{prefix}created instance: {name}")
    for name in updated:
        print(f"{prefix}updated instance: {name}")
    for problem in failed:
        print(f"{prefix}FAILED: {problem}", file=sys.stderr)

    seeker_names = provision_seeker(dry_run)
    print(f"{prefix}seeker enabled for: {', '.join(seeker_names)}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

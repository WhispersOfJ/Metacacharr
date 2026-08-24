#!/usr/bin/env python3
"""Sweep container health (docker) and HTTP reachability across the media-stack.

Usage:
    monitor.py sweep [--json]
    monitor.py docker-only
    monitor.py http-only
    monitor.py watch [--interval SECONDS]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# service name -> (port, path). Update when a service's port/health endpoint changes.
HTTP_SERVICES = {
    "radarr": (7878, "/ping"),
    "sonarr": (8989, "/ping"),
    "prowlarr": (9696, "/ping"),
    "seerr": (5055, "/api/v1/status"),
    "control-panel": (8420, "/healthz"),
    "plex": (32400, "/identity"),
    "nzbdav": (3000, "/"),
    # Not "/" - that is the bundled WebUI and answers 200 with a dead backend
    # behind it. This endpoint needs no auth even with WS_SECURE_API_ENDPOINTS on.
    "watchstate": (8705, "/v1/api/system/healthcheck"),
}

# Scheduled jobs have no port and no persistent process, so HTTP reachability
# says nothing about them - the question is whether the timer actually fired
# recently and whether the last run succeeded. name -> (timer unit, max age in
# seconds before the run counts as stale).
#
# These are *user* units (systemctl --user), not system ones - every stack-*
# timer on this host is installed under ~/.config/systemd/user.
#
# Empty since PlexAniSync (the only entry) was decommissioned 2026-08-20 -
# check_timer() below stays as reusable infra for the next scheduled job.
SCHEDULED_JOBS = {}


def _systemctl_show(unit: str, properties: str) -> dict:
    """`systemctl --user show` as a dict. Empty on any failure - a missing unit
    is reported by the caller as not-installed, not as a crash."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show", unit, "--property", properties],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return {}
    values = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition("=")
        if key:
            values[key] = value
    return values


def check_timer(name: str, unit: str, max_age: int) -> tuple[bool, str]:
    """Freshness + last-result for a systemd timer-backed job.

    Two independent failure modes, both of which have to fail the check: the
    timer stopped firing (stale), or it fired and the job exited non-zero.
    """
    timer = _systemctl_show(unit, "LoadState,ActiveState,LastTriggerUSec")
    if not timer or timer.get("LoadState") != "loaded":
        return False, f"timer '{unit}' not installed"
    if timer.get("ActiveState") != "active":
        return False, f"timer '{unit}' is {timer.get('ActiveState', 'inactive')}, not active"

    service_unit = unit.rsplit(".", 1)[0] + ".service"
    service = _systemctl_show(service_unit, "Result,ExecMainStatus")
    result = service.get("Result", "")
    exit_status = service.get("ExecMainStatus", "")
    if result and result != "success":
        return False, f"last run failed (result={result}, exit={exit_status or '?'})"

    trigger = timer.get("LastTriggerUSec", "")
    # systemd prints "n/a" when the timer has never fired since it was enabled.
    if not trigger or trigger == "n/a":
        return True, "installed and active, has not fired yet"

    try:
        # Format: "Thu 2026-08-13 12:45:00 EDT" - drop the weekday and zone.
        parts = trigger.split()
        last = time.mktime(time.strptime(f"{parts[1]} {parts[2]}", "%Y-%m-%d %H:%M:%S"))
    except (IndexError, ValueError):
        return True, f"active, last fired {trigger} (unparsed)"

    age = int(time.time() - last)
    if age > max_age:
        return False, f"stale - last fired {age // 3600}h ago (max {max_age // 3600}h)"
    return True, f"last fired {age // 60}m ago, exit {exit_status or '0'}"


def docker_ps(compose_dir: Path) -> list[dict]:
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            cwd=compose_dir, capture_output=True, text=True, check=True, timeout=15,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"error running docker compose ps: {e}", file=sys.stderr)
        return []

    services = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            services.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return services


def check_http(name: str, port: int, path: str, timeout: float = 5.0) -> tuple[bool, str]:
    url = f"http://localhost:{port}{path}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        # A 401/403 still proves the service is up and answering.
        if e.code in (401, 403):
            return True, f"HTTP {e.code} (auth required, reachable)"
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"unreachable ({e.reason})"
    except TimeoutError:
        return False, "timeout"


def sweep(compose_dir: Path, do_docker: bool, do_http: bool) -> dict:
    report = {"docker": {}, "http": {}, "scheduled": {}}

    if do_docker:
        for svc in docker_ps(compose_dir):
            name = svc.get("Service", svc.get("Name", "?"))
            state = svc.get("State", "?")
            health = svc.get("Health", "")
            report["docker"][name] = {"state": state, "health": health}

    if do_http:
        for name, (port, path) in HTTP_SERVICES.items():
            ok, detail = check_http(name, port, path)
            report["http"][name] = {"ok": ok, "detail": detail}

    # Grouped with the HTTP pass rather than the docker one: both answer "is
    # this service doing its job", which docker state cannot say for a
    # container that is supposed to be Exited(0) between runs.
    if do_http:
        for name, (unit, max_age) in SCHEDULED_JOBS.items():
            ok, detail = check_timer(name, unit, max_age)
            report["scheduled"][name] = {"ok": ok, "detail": detail}

    return report


def print_report(report: dict) -> None:
    if report["docker"]:
        print("== Docker container health ==")
        for name, info in sorted(report["docker"].items()):
            marker = "OK  " if info["state"] == "running" and info["health"] in ("healthy", "") else "FAIL"
            print(f"  {marker}  {name:<24} state={info['state']:<10} health={info['health'] or 'n/a'}")

    if report["http"]:
        print("== HTTP reachability ==")
        for name, info in sorted(report["http"].items()):
            marker = "OK  " if info["ok"] else "FAIL"
            print(f"  {marker}  {name:<24} {info['detail']}")

    if report.get("scheduled"):
        print("== Scheduled jobs (systemd timers) ==")
        for name, info in sorted(report["scheduled"].items()):
            marker = "OK  " if info["ok"] else "FAIL"
            print(f"  {marker}  {name:<24} {info['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-dir", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="action", required=True)

    p_sweep = sub.add_parser("sweep")
    p_sweep.add_argument("--json", action="store_true")

    sub.add_parser("docker-only")
    sub.add_parser("http-only")

    p_watch = sub.add_parser("watch")
    p_watch.add_argument("--interval", type=int, default=30)

    args = parser.parse_args()

    if args.action == "sweep":
        report = sweep(args.compose_dir, True, True)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print_report(report)
    elif args.action == "docker-only":
        print_report(sweep(args.compose_dir, True, False))
    elif args.action == "http-only":
        print_report(sweep(args.compose_dir, False, True))
    elif args.action == "watch":
        try:
            while True:
                print(f"--- sweep at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
                print_report(sweep(args.compose_dir, True, True))
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nstopped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

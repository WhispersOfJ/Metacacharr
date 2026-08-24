---
name: health-monitor
description: Check container-level and HTTP-endpoint health across the whole media-stack in one pass — Docker healthcheck status plus a reachability probe for each web-facing service (Arr apps, Plex, Seerr, control-panel, etc.). Use for a general "is everything okay" sweep, after a host reboot, after a docker compose up, or when triaging a user report of "the stack seems broken" before diving into any single service. Trigger phrases: "is everything healthy", "check the stack", "what's down", "post-reboot check", "give me a health report".
---

# Health Monitor

Two independent signals, both checked, because they catch different failure modes:

1. **Docker healthcheck status** (`docker inspect` / `docker compose ps`) — catches a
   container that's crash-looping or whose own healthcheck is failing.
2. **HTTP reachability** — catches a container that's "healthy" per Docker but whose
   web UI/API isn't actually responding (e.g. still booting, or the app deadlocked
   without dying).

A service can fail either check independently — report both, don't collapse them into
a single up/down.

## Usage

```bash
python3 monitor.py sweep                     # full report: docker health + HTTP checks
python3 monitor.py sweep --json               # machine-readable output
python3 monitor.py docker-only                # skip HTTP checks (faster, useful mid-restart)
python3 monitor.py http-only                  # skip docker inspect (useful outside the host)
python3 monitor.py watch --interval 30        # repeat sweep every N seconds until Ctrl-C
```

Run from the repo root, or pass `--compose-dir`. HTTP endpoints and default ports are
defined in `monitor.py::HTTP_SERVICES`; update it if a service's port changes.

## Interpreting results

- Docker-healthy + HTTP-unreachable: likely still booting (check again in ~30s) or a
  reverse-proxy/network issue — don't restart immediately, re-check first.
- Docker-unhealthy: hand off to `docker-compose-manager restart <service>`, respecting
  the cascade map if the service is a mount owner.
- Both failing for a mount-owning service's dependents simultaneously (e.g. every Arr app
  down at once) strongly suggests a FUSE mount went stale — check
  `docker-compose-manager cascade-map` and the mount owner's own health first.

## Safety rules

- Read-only: this skill only observes (`docker inspect`, `docker compose ps`, HTTP GET).
  It never restarts or modifies anything — hand off findings to `docker-compose-manager`
  for remediation.

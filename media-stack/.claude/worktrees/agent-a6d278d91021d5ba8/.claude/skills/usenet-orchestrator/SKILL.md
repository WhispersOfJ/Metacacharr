---
name: usenet-orchestrator
description: Inspect and manage NzbDAV's download queue and health — the only download client this stack runs (torrent/debrid support was removed entirely in v11.0.0; NzbDAV (nzbdav-dev) was replaced by AltMount, then BearMount, then nzbdav/nzbdav - a super-fork of that same original lineage). `diagnose-stuck-file` is a documented no-op here — it was built around the original NzbDAV's specific log pattern and hasn't been re-confirmed against the current one, though it may apply again. Use when the user asks about stuck or failed downloads, wants to see what's queued, needs to clear a jammed queue item, or wants to confirm the download client is reachable by the Arr apps. Trigger phrases: "what's stuck in the download queue", "check nzbdav status", "clear failed downloads", "why isn't radarr grabbing anything".
---

# Usenet Orchestrator

Queries NzbDAV's own SABnzbd-compatible API directly (bypassing the Arr apps) to
answer "is the download client itself the problem?" before assuming it's an indexer,
mount, or Arr config issue. Complements `health-monitor` (which checks container-level
health) by checking *queue-level* health: stuck items, failed items, and reachability.

## Scope

- `nzbdav` — the only download client this stack runs (SABnzbd-compatible API,
  `nzbdav/nzbdav`, a maintained "super-fork" of `nzbdav-dev/nzbdav`, replacing BearMount
  as of 2026-07-28 - see STACK.md's History). Torrent/debrid support (Decypharr, Zurg,
  rclone-alldebrid, Zilean, Byparr) was removed entirely in v11.0.0 — nothing else to
  orchestrate here.
- `orchestrator.py::CLIENTS` is written generically (any SABnzbd/qBittorrent-API-
  compatible client can be added back) in case that ever changes, but as of now it only
  lists `nzbdav`.

Unlike BearMount (which owned its FUSE mount directly), NzbDAV is WebDAV-only - the
actual FUSE mount is a separate sidecar container, `nzbdav_rclone`. Mount-cascade
restarts are `docker-compose-manager`'s job (its cascade key is `nzbdav_rclone`, not
`nzbdav`); this skill only talks to the download-client queue API on `nzbdav` itself.

## Auth / config

```
NZBDAV_URL / NZBDAV_API_KEY   (defaults to http://localhost:PORT if unset)
```

`NZBDAV_API_KEY` falls back to `.env`'s `FRONTEND_BACKEND_API_KEY` if unset - NzbDAV
shares one key across its frontend proxy, SAB API, and admin API, unlike BearMount's
separate per-purpose keys. Never hardcode a real LAN IP or credential as a fallback —
env vars only, `localhost` default.

## Usage

```bash
python3 orchestrator.py queue nzbdav                     # list current queue items + state
python3 orchestrator.py failed nzbdav                     # list only failed/error items
python3 orchestrator.py retry nzbdav <item-id>            # re-queue a failed item
python3 orchestrator.py clear-failed nzbdav                # remove all failed items (asks first)
python3 orchestrator.py reachability                      # ping the configured client, report up/down
```

`diagnose-stuck-file` still exists as a subcommand but is a documented no-op: it was
built around the original NzbDAV (nzbdav-dev)'s repeating `.ids/<uuid> 404 Not Found` log
pattern. The current client's mount does expose a matching `.ids/` structure (confirmed
live 2026-07-28), so this diagnostic may well apply again — but that hasn't been verified
against real log output yet, so it still just prints an explanation rather than guessing.

## Interpreting results

- A client that's unreachable (`reachability` fails) almost always means the container
  is down or mid-restart — hand off to `docker-compose-manager status nzbdav` rather
  than digging further here.
- A client that's reachable but has a growing "failed" queue with the same error message
  repeated is usually an indexer/API-limit problem upstream in Prowlarr, not this skill's
  job to fix — report the pattern, don't guess at Prowlarr config.
- Stuck-but-not-failed items (state unchanged across repeated `queue` calls) often
  correlate with a stale FUSE mount — cross-check with `docker-compose-manager cascade-map`
  before assuming the download client itself is broken.
- Before recreating/restarting `nzbdav` or `nzbdav_rclone` for any reason, check the
  queue for pending/processing items first (`queue nzbdav`) - a recreate can strand
  in-flight items and, for `nzbdav_rclone` specifically, requires the full cascade
  restart of its 5 dependents (see `docker-compose-manager`).

## Safety rules

- `clear-failed` prompts for confirmation — it's a bulk destructive action on queue state.
- `retry` only touches the single item ID given; never retries an entire queue implicitly.

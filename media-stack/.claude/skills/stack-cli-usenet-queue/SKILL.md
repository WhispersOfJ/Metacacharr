---
name: stack-cli-usenet-queue
description: Exact fish CLI command reference for NzbDAV, Cleanuparr, and Prowlarr status/queue operations against this stack's Control Panel. Use whenever the user asks about the Usenet download queue/history, Cleanuparr strikes, or Prowlarr indexer state from the terminal. Trigger phrases: "check the nzbdav queue", "nzbdav history", "cleanuparr strikes", "prowlarr indexers".
---

# Stack CLI: Usenet & Queue Automation

<skill_scope skill="stack-cli-usenet-queue">
This is a command reference, not an operational tool: it exists so the exact fish function name, argument order, and output shape for every NzbDAV/Cleanuparr/Prowlarr terminal command in this stack is already known, without reading the fish source fresh each time. Every command here is a thin fish wrapper around Control Panel's own HTTP API (`http://192.168.4.20:8420`); the actual behavior lives in `control-panel/main.py` plus `services/nzbdav/router.py`, `services/cleanuparr/router.py`, and `services/prowlarr/router.py` (`app.py` is retired dead code, not the live source). Recyclarr is only a catalog listing (a candidate service in `control-panel/services/catalog/registry.py`) - it was never actually deployed, has no container, and `/api/recyclarr/status` does not exist (404 live) despite being documented elsewhere as a real route; there is no dedicated CLI command for it here. Maintainerr was decommissioned (see PLANS.md) - `services/maintainerr/router.py` and the `stack-maintainerr-*` commands no longer exist. NeutArr (missing-content hunting) was removed entirely 2026-07-24 - there is no `stack-neutarr-*` command anymore, and no automated hunting of any kind in this stack. The `stack-bearmount-*` fish functions were renamed to `stack-nzbdav-*` (2026-07-28) - they had drifted further than a stale label: the function bodies themselves still called the removed `/api/bearmount/*` routes and were fully broken (404) before the rename, not just misnamed. `stack-bearmount-restart` and `stack-bearmount-unstick-ffprobe-hang` were deleted outright rather than renamed - the former is redundant with `stack-container restart <name>` plus `docker-compose-manager`'s cascade-aware restart, the latter's mitigation was never ported to nzbdav/nzbdav (see FIXES.md) and has no current equivalent.

**Related skill:** `usenet-orchestrator` is a different mechanism entirely - a standalone Python script that talks to NzbDAV's own SABnzbd-compatible API directly (not through Control Panel) and can retry/clear-failed items. Reach for `usenet-orchestrator` for queue *mutation* (retry, clear-failed); reach for the commands here for quick read-only status checks.
</skill_scope>

## Calling convention

<calling_convention>
Some commands here (`stack-cleanuparr-instances`) go through the `__stack_api` helper and print a raw `message`. The rest `curl` their endpoint directly and pipe through an inline `python3 -c "..."` formatter that unwraps FastAPI's `{"detail": {...}}` shape if present, prints `data['message']`, then loops over the relevant list field with per-line formatting.

None of these read a `STACK_HOST_IP` environment variable - the Control Panel URL is a literal hardcoded string in every function.
</calling_convention>

## Command reference

<command_reference>
| Command | Args | What it does |
|---|---|---|
| `stack-nzbdav-queue` | none | NzbDAV's current Usenet download queue - category, name, status, percentage, MB left while downloading. Calls `control-panel`'s `/api/nzbdav/queue` route. |
| `stack-nzbdav-history` | `[limit]` (default 20) | Recent completed/failed downloads, with the failure message if one failed. Calls `/api/nzbdav/history`. |
| `stack-nzbdav-stats` | none | Aggregate queue/history counts - a summary instead of the raw dumps `stack-nzbdav-queue`/`stack-nzbdav-history` give. Calls `/api/nzbdav/stats`. |
| `stack-nzbdav-delete-failures` | none | Deletes every "Failed" entry from NzbDAV's history right now. On-demand version of the `stack-bearmount-prune-history.timer` job that already runs this every 4h (unit name kept as-is, see Resources) - useful because a Failed row blocks re-grabbing an NZB with a matching release name ("Duplicate nzb" error) even when nothing exists on disk for it. Calls `/api/nzbdav/delete-failures`. |
| `stack-cleanuparr-instances` | none | Which `*arr` apps Cleanuparr has an *actual connected instance* for, as opposed to just network-reachable - a real gap found live once (an app had network access and a config placeholder but no connected instance, so queue-cleaning silently wasn't covering it). |
| `stack-cleanuparr-strikes` | `[limit]` (default 15) | Recent stalled/slow/malware strikes Cleanuparr has issued. |
| `stack-prowlarr-indexers` | none | Every configured Prowlarr indexer's enabled state and sync priority. |
</command_reference>

## Common mistakes

<common_mistakes>
<general_anti_patterns>
- **Assuming a network-reachable Cleanuparr means it's covering an app.** Reachability and having an actual connected instance in Cleanuparr's own config are two different things - always check `stack-cleanuparr-instances`, not just that the container is up, before assuming strikes/cleanup are active for a given app.
- **There is no `stack-bearmount-unstick`/`set-connections` equivalent.** Both were workarounds for the *original* NzbDAV's specific bugs (a non-REST settings API; a history-query-hang that cascaded into Sonarr marking the client unavailable) that were never ported to AltMount or BearMount - neither confirmed to apply to the current nzbdav/nzbdav's actual API shape either, though it's the same lineage so worth re-checking if similar symptoms appear. Before restarting `nzbdav` or `nzbdav_rclone` for any reason, check the queue for pending/processing items first (see `usenet-orchestrator`) - a recreate can strand in-flight items, and `nzbdav_rclone` specifically needs the full 5-dependent cascade restart (`docker-compose-manager`).
</general_anti_patterns>
</common_mistakes>

## Resources

<resources>
**Local:**
- `~/.config/fish/functions/stack-nzbdav-*.fish`, `stack-cleanuparr*.fish`, `stack-prowlarr-indexers.fish` - the actual fish source these commands wrap
- `scripts/bearmount-prune-history.py` and its `stack-bearmount-prune-history.timer` unit - the recurring job `stack-bearmount-delete-failures` runs on demand (filename/unit kept as-is; content updated for NzbDAV's API)
- `control-panel/main.py` + `services/nzbdav/router.py`, `services/cleanuparr/router.py`, `services/prowlarr/router.py` in this repo - the real behavior behind every endpoint these commands call (routes renamed to `/api/nzbdav/*`)
</resources>

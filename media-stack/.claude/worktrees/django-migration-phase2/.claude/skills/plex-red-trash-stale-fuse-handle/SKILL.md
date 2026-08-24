---
name: plex-red-trash-stale-fuse-handle
description: "Use when Plex library items show the red trash-can / unavailable overlay in the web UI, especially a near-total wipe of one section (thousands of items, not a handful), and the underlying files are actually present and readable through the mount from other containers. Diagnoses a stale FUSE handle inside the plex container specifically — caused by nzbdav_rclone being recreated without cascading a restart to plex — that makes every stat() during a scan fail with 'Transport endpoint is not connected' / 'Socket not connected', which Plex then (correctly, from its own view) records as mass deletions. Separate from plex-marked-deleted-db-contention (SQLite write contention, a Plex-internal DB bug) — this one is a mount-layer problem with a mount-layer fix (restart plex, not just refresh)."
metadata:
  origin: manual
---

# Plex red trash-can from a stale FUSE handle after nzbdav_rclone recreate

**Context:** media-stack, Plex served over the nzbdav_rclone FUSE mount (`/mnt/remote/nzbdav` → `/data`). Applies whenever `nzbdav_rclone` was restarted or recreated more recently than `plex`, and a library scan ran against Plex afterward.

## Problem

Symptom: one or more library sections show the red "marked for deletion" trash-can overlay, often at a scale far beyond the DB-contention variant — e.g. 61,363 of 61,367 items in a Shows section (essentially the whole library), not a partial section. Files are still present, correctly symlinked, and readable through the mount **from every other container** (Radarr, Sonarr, Bazarr, Cleanuparr, Unpackerr) — the breakage is isolated to Plex's own mount namespace.

```bash
docker exec plex stat -L "/data/shows/<Title>/<file>.mkv"
```

If this returns `Transport endpoint is not connected` (or `Socket not connected` in the Plex log's `boost::filesystem` errors) while the same path stats fine from `radarr`/`sonarr`/`bazarr`, this is the bug — not a real mount outage, not DB contention.

## Root cause

`nzbdav_rclone` is the sole FUSE-mount-owning container in this stack. Every dependent (`radarr`, `sonarr`, `radarr-anime`, `sonarr-anime`, `plex`, `bazarr`, `unpackerr`, `cleanuparr`) holds a bind-mounted view into that mount. When `nzbdav_rclone` gets recreated (image update, config change, manual restart) without the cascade also restarting every dependent, a dependent that's still running keeps the *old* mount's file handle — which is now defunct. Any filesystem call against it returns `ENOTCONN`.

Plex is the dependent most likely to actually run a scan against `/data` unattended (scheduled library scans, Butler tasks), so it's usually the one that surfaces this first and worst: the scanner walks the whole library, every `stat()`/`file_size()` call fails, and Plex's scanner treats every one of those as "file is gone" — which mass-flags the section `deleted_at` in the DB. This is Plex behaving correctly given what it observed; the observation itself was wrong because the mount handle was stale.

Log signature in `Plex Media Server.log` (note: **not** `busy database` — this is a different error family from the SQLite-contention variant):

```
ERROR - Couldn't check for the existence of file "/data/...": boost::filesystem::status: Socket not connected [system:107]
ERROR - Couldn't get size of file "/data/...": boost::filesystem::file_size: Socket not connected [system:107]
```

## Diagnosis checklist

1. Check how long `nzbdav_rclone` and `plex` have each been running — if `nzbdav_rclone`'s uptime is *shorter* than `plex`'s, a cascade restart was missed:
   ```bash
   docker ps --filter name=nzbdav_rclone --format '{{.Names}}\t{{.Status}}'
   docker ps --filter name=plex --format '{{.Names}}\t{{.Status}}'
   ```
2. Confirm the stale handle directly inside the plex container:
   ```bash
   docker exec plex stat -L "/data/<section>/<known-good-title>/<file>" 2>&1
   ```
   `Transport endpoint is not connected` confirms it. (Note: `ls /data/...` can still succeed via cached dentries even when `stat` on a real file fails — don't stop at `ls`.)
3. Rule out a real mount-wide outage by checking the same path from a sibling dependent:
   ```bash
   docker exec radarr stat -L "/data/<section>/<same file, radarr's path>" 2>&1
   ```
   If radarr/sonarr/bazarr succeed while plex fails, the mount itself is fine — only plex's handle is stale.
4. Confirm via log grep that this is the socket-error variant, not `busy database`:
   ```bash
   docker exec plex bash -c 'grep -c "Socket not connected" "/config/Plex Media Server/Logs/Plex Media Server.log"'
   docker exec plex bash -c 'grep -c "busy database" "/config/Plex Media Server/Logs/Plex Media Server.log"'
   ```
5. Quantify the damage against the DB directly (faster and more precise than the web UI) — query from the host, since `sqlite3`/`python3` aren't in the plex container:
   ```bash
   DB="<plex-config>/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db"
   sqlite3 "$DB" "SELECT library_section_id, count(*) FROM metadata_items WHERE deleted_at IS NOT NULL GROUP BY library_section_id;"
   ```
   Cross-reference `min(deleted_at)`/`max(deleted_at)` against when `nzbdav_rclone` was last recreated to confirm the timing lines up.

## Fix

1. Check every FUSE-mount dependent for a stale handle first (step 3 above, run for all of `radarr`, `sonarr`, `radarr-anime`, `sonarr-anime`, `bazarr`, `unpackerr`, `cleanuparr`) — restart only the ones that are actually stale. In the observed incident only `plex` was affected; don't blanket-restart the whole cascade if it isn't necessary.
2. Restart the stale container(s):
   ```bash
   docker restart plex
   ```
   A plain restart is sufficient — this re-establishes the bind mount from inside a fresh container, it does not require touching `nzbdav_rclone`.
3. Wait for health, then re-verify the mount resolves:
   ```bash
   docker inspect plex --format '{{.State.Health.Status}}'
   docker exec plex stat -L "/data/<section>/<known-good-title>/<file>"
   ```
4. Trigger a refresh on every affected section:
   ```bash
   curl -s "http://localhost:32400/library/sections/<id>/refresh?X-Plex-Token=$PLEX_TOKEN"
   ```
5. This does not resolve instantly — Plex has to re-walk and re-confirm every flagged item. For a large section (tens of thousands of items) this can take upward of an hour. Track progress via the DB count from step 5 of diagnosis (it should be monotonically decreasing) rather than polling the activities feed continuously — the scan runs independently of your session once triggered.
6. Verify visually in the Plex web UI on a couple of previously-affected titles once the DB count is near zero.

## Non-obvious gotchas

- `ls` on the mount can succeed even while the mount is functionally dead for this purpose — cached directory entries don't require a live transport. Always verify with `stat` (or read) on a specific file, not a directory listing.
- This is triggered by an *upstream* maintenance action (recreating `nzbdav_rclone`) that had nothing to do with Plex directly — always check container uptimes relative to each other as step 1, don't assume the trigger was something Plex-side.
- Don't reach for `docker-compose-manager`'s full cascade restart reflexively — that cascade exists for when you're *about* to recreate `nzbdav_rclone` (recreate it, then cascade). Here `nzbdav_rclone` is already fine; you're cleaning up a *missed* cascade after the fact, so only the dependents that actually show a stale handle need restarting.
- `autoEmptyTrash` being disabled (standing config in this stack) means this never risks real data loss — same as the DB-contention variant, it's a stuck flag pending reconciliation.

## When to use

Trigger on: Plex library items showing the red "marked for deletion" / unavailable trash-can icon, especially when it affects a very large fraction of a whole section (not just a subset), and `docker exec plex stat -L <file>` returns `Transport endpoint is not connected` while the same file stats fine from Radarr/Sonarr/Bazarr. Check `nzbdav_rclone` vs `plex` container uptime as the first diagnostic step.

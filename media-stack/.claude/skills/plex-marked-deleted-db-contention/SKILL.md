---
name: plex-marked-deleted-db-contention
description: "Use when Plex library items show the red trash-can / unavailable overlay in the web UI while the underlying files are actually present and readable on disk. Diagnoses Plex's SQLite database getting stuck with items internally flagged 'marked as deleted' after a burst of concurrent scans/metadata writes (e.g. a large Sonarr/Radarr backfill overlapping a full library scan), and the restart-based fix that clears it. Separate from FUSE-mount hangs (fuse-hang-vs-slow-diagnosis) and rclone mtime-poisoning 404s (plex-direct-play-404-rclone-modtime) — this is a Plex-internal DB state bug, not a mount problem."
metadata:
  origin: manual
  stack: media-stack
---

# Plex red trash-can from SQLite write contention (items wrongly marked deleted)

**Context:** media-stack, Plex served over the nzbdav_rclone FUSE mount (`/mnt/remote/nzbdav` → `/data`). Applies whenever Plex's library scanning overlaps heavy concurrent write activity (a mass Arr backfill, a full section scan, several parallel metadata refreshes) on a single SQLite-backed library.

## Problem

Symptom: one or more library sections show items with a solid red trash-can icon over the poster in the Plex web UI ("marked for deletion" / unavailable). This can hit an entire section (seen: ~600/602 Anime Movies items) while sibling sections (Movies, Shows) look clean, which makes it easy to miss if you only spot-check the section you expect to be affected.

This is **not** evidence of actual data loss. Files referenced by these items are typically still present, correctly symlinked, and readable straight through the mount:

```bash
docker exec plex stat -L "/data/<section>/<Title>/<file>.mkv"
docker exec plex timeout 10 head -c 1024 "/data/<section>/<Title>/<file>.mkv" > /dev/null; echo $?
```

If `stat` succeeds and `head` exits 0, the file is fine — the problem is entirely inside Plex's database.

## Root cause

Plex's library database is a single-writer SQLite file. A burst of concurrent write pressure — a large Arr backfill importing many items in a short window, *plus* a full (not scoped) library section scan, *plus* several parallel per-item metadata-agent refreshes — can exceed SQLite's write-lock tolerance. The signature in `Plex Media Server.log`:

```
ERROR - Waited over 10 seconds for a busy database; giving up.
WARN - Held transaction for too long (...): NN seconds
WARN - Took too long (NN seconds) to start a transaction on ...
```

When a scan's transaction gets abandoned mid-write like this, the item it was processing can be left flagged as deleted in the DB even though the scanner never actually failed to find the file — it just never got to finish confirming it was there. Once contention is bad enough, this cascades into Plex's own internal state breaking, not just slow queries:

```
ERROR - Thread: Uncaught exception running async task which was spawned by thread ...: std::exception
ERROR - Saving activity history aborted with DB exception: std::exception
```

At this point a plain library refresh does **not** fix it. Plex's scanner skips folders it thinks are unchanged, and items already flagged deleted don't necessarily get revisited by every refresh call while the DB is still in this broken state — refreshes can appear to succeed (HTTP 200, activity registers) while producing no actual change. The write-ahead log (`com.plexapp.plugins.library.db-wal`) growing far past its normal size (tens of MB instead of low single-digit MB) is a corroborating signal that checkpoints aren't keeping up.

## Diagnosis checklist

1. Confirm it's not a real missing-file problem first (see Problem section above) — `stat`/`head` through the mount on 2-3 affected titles.
2. Check for the busy-database signature in the last few thousand log lines:
   ```bash
   docker exec plex bash -c 'tail -n 2000 "/config/Plex Media Server/Logs/Plex Media Server.log" | grep -c "busy database"'
   ```
   A steady stream (not just a handful) during the affected window confirms contention.
3. Check for the escalated internal-exception signature — this is the tell that a plain refresh won't be enough:
   ```bash
   docker exec plex bash -c 'grep -c "Uncaught exception\|Saving activity history aborted" "/config/Plex Media Server/Logs/Plex Media Server.log"'
   ```
4. Check what was actually running concurrently — look for an active full section scan stacked with several `library.update.item.metadata` jobs at the same time:
   ```bash
   curl -s "http://localhost:32400/activities?X-Plex-Token=$PLEX_TOKEN" | python3 -c "
   import sys,xml.etree.ElementTree as ET
   root=ET.fromstring(sys.stdin.read())
   for a in root: print(a.attrib.get('type'), a.attrib.get('title'), a.attrib.get('subtitle'), a.attrib.get('progress'))
   "
   ```
5. Confirm the WAL is oversized:
   ```bash
   ls -la "<plex-config>/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db-wal"
   ```
   Tens of MB+ (vs low single-digit MB baseline) supports the contention diagnosis.
6. Trigger a targeted section refresh and watch the log for the confirming line — this is the actual fingerprint of the bug, not an inference:
   ```bash
   curl -s "http://localhost:32400/library/sections/<id>/refresh?X-Plex-Token=$PLEX_TOKEN"
   docker exec plex bash -c 'grep "was marked as deleted" "/config/Plex Media Server/Logs/Plex Media Server.log"'
   ```
   `File '...' was marked as deleted, can't skip.` appearing for files you already confirmed are present is the definitive signature of this bug, as opposed to a genuinely missing file.

## Fix

1. If step 6 above shows the "marked as deleted, can't skip" lines but the section refresh *also* logs fresh `Uncaught exception`/`Saving activity history aborted` errors, don't keep retrying refreshes — the DB is still wedged. Restart the Plex container:
   ```bash
   docker restart plex
   ```
   This cleanly closes the DB connections (forcing a WAL checkpoint) and clears whatever bad in-memory state was causing the uncaught exceptions. Confirm the WAL shrank back to a normal size afterward.
2. Wait for `docker inspect plex --format '{{.State.Health.Status}}'` to report `healthy`.
3. Trigger the affected section's refresh again:
   ```bash
   curl -s "http://localhost:32400/library/sections/<id>/refresh?X-Plex-Token=$PLEX_TOKEN"
   ```
   Watch for `Scanning <Section Name>` to actually start in the activities feed and for `File '...' was marked as deleted, can't skip.` lines to resolve without a following exception — that's the reconcile actually completing this time.
4. Verify visually in the Plex web UI (not just via API/log) — the red trash-can overlay is a client-rendered flag on the poster grid; confirm by loading the section and checking a title you know was affected, ideally by searching for it directly rather than relying on "Recently Added" sort order (items whose deleted flag just cleared can jump in sort position).
5. If the underlying backfill/scan burst that caused this is still running, expect it can recur while that burst continues — this fix clears the current bad state, it doesn't prevent a fresh burst from reproducing it. If it recurs repeatedly during a known large backfill, consider avoiding overlapping a full (non-scoped) library scan with the backfill window (see `scoped-plex-library-refresh`).

## Non-obvious gotchas

- Don't jump to mount/FUSE diagnosis first just because trash cans look like "missing files" — verify the file through the mount before assuming it's a `fuse-hang-vs-slow-diagnosis` or `plex-direct-play-404-rclone-modtime` situation. Those are mount-layer and mtime-signature bugs respectively; this one is purely a Plex-internal DB state bug and neither of those fixes (mount restart, `--no-modtime` flag check) will touch it.
- A section-level refresh with `force=1` does not reliably help over a plain refresh here — the blocker isn't "scanner thinks nothing changed," it's the DB itself throwing exceptions mid-transaction. Only a Plex restart reliably clears the exception state observed in this incident.
- Canceling a stuck/redundant full-section scan via `GET /library/sections/<id>/refresh?cancel=1` or `DELETE /activities/<uuid>` is unreliable in practice (both returned success/plausible codes without actually stopping the scan in the incident this skill is based on) — don't rely on it as your primary contention-relief lever; a fast-running, mostly-unchanged full scan may just need to finish rather than be killed.
- `autoEmptyTrash` being disabled (a standing config in this stack, see project memory on mass-deletion incidents) means none of this ever risks a real deletion — the red trash-can state is purely a stuck flag pending reconciliation, not a countdown to data loss. Don't let the icon's urgency push you toward a destructive "fix."

## When to use

Trigger on: Plex library items showing the red "marked for deletion" / unavailable trash-can icon, especially right after or during a large Arr backfill or a full (non-scoped) library scan, when the files themselves check out fine through the mount.

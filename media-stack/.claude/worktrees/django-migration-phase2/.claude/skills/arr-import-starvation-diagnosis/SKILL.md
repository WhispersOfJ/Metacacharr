---
name: arr-import-starvation-diagnosis
description: "Use when Radarr/Sonarr is grabbing releases but nothing is importing, when files are landing in the download client's completed directory but the library never updates, or when a queue reports ZERO items yet the app is clearly still active. Diagnoses RefreshMonitoredDownloads being starved out of the command thread pool by a bulk search backlog (a mass MissingEpisodeSearch/MoviesSearch backfill), which stops imports AND empties the queue at the same time, so every ordinary queue-health check reads clean on a totally broken app. Distinct from arr-importblocked-triage (which assumes a populated queue) and from FUSE mount problems (fuse-hang-vs-slow-diagnosis) — nothing is wrong with the mount or the files here."
metadata:
  origin: incident-2026-08-08
  stack: media-stack
---

# Radarr/Sonarr import starvation from a bulk search backlog

**Context:** media-stack, NzbDAV as the sole download client across four Arr instances (radarr, radarr-anime, sonarr, sonarr-anime). Applies whenever a bulk search is queued in bulk — a missing-episode backfill, a mass movie search, a newly-added library's initial hunt.

## The symptom that gets reported

"The files are downloading but they are not showing up in Sonarr." The download client's completed directory keeps filling. Grabs keep appearing in history. The library never grows.

## Why every normal health check says everything is fine

`RefreshMonitoredDownloads` does two jobs in one command:

1. Polls the download client and **populates the app's queue**.
2. Triggers imports of completed items.

It is scheduled every 60 seconds, but it shares a thread pool with searches and has **no priority over them**. Queue a thousand `MoviesSearch` commands and it simply never gets a slot.

Because job 1 is what populates the queue, a starved app reports an **empty queue**. Every queue-shaped check — `trackedDownloadStatus` flags, `failedPending` counts, `importBlocked` counts, "is anything stuck" — reads perfectly clean. This is not a subtle failure that is hard to notice; it is a failure that actively reports itself as health.

**Never conclude an app is healthy from an empty queue.** That inference is what let the 2026-08-08 incident run for hours, and it produced a written all-green health report on two fully broken apps.

## Diagnosis

Two signals, both deterministic. Signal 1 is conclusive on its own.

**Signal 1 — a queued `RefreshMonitoredDownloads` older than ~5 minutes:**

```bash
curl -s "http://<host>:<port>/api/v3/command" -H "X-Api-Key: $KEY" | python3 -c "
import json,sys
from collections import Counter
cs=json.load(sys.stdin)
act=[c for c in cs if c['status'] in ('queued','started')]
print(Counter(c['name'] for c in act))
for c in cs:
    if c['name']=='RefreshMonitoredDownloads':
        print(c['status'], 'queued', c.get('queued'), '-> ended', c.get('ended'))
"
```

A `queued` entry whose `queued` timestamp is minutes old, sitting behind hundreds of `MoviesSearch` / `MissingEpisodeSearch`, is the diagnosis. Compare `queued` to `ended` on completed ones to measure how long it was starved.

**Signal 2 — grabs continuing while imports have stopped:**

```bash
# eventType 1 = grabbed, 3 = downloadFolderImported
for ev in 1 3; do
  curl -s "http://<host>:<port>/api/v3/history?pageSize=1&eventType=$ev&sortKey=date&sortDirection=descending" \
    -H "X-Api-Key: $KEY" | python3 -c "import json,sys;r=json.load(sys.stdin)['records'];print(r[0]['date'] if r else None)"
done
```

A last-grab timestamp far newer than last-import is the user-visible symptom. Pulling a page of history and finding it is **all** `grabbed` with zero `downloadFolderImported` confirms it instantly.

## Fix

Cancel the queued bulk searches so the pool frees up:

```bash
curl -s -X DELETE "http://<host>:<port>/api/v3/command/<id>" -H "X-Api-Key: $KEY"
```

- Only `queued` commands cancel. A `started` one returns **409 Conflict** — expected and fine; the few in flight finish on their own and the pool drains behind them.
- Cancelling is safe and reversible. The backlog is still recorded as wanted/missing, and a cancelled search re-queues on the next scheduled or manual run.
- Recovery is not instant. The starved `RefreshMonitoredDownloads` must finish its own long first pass before the queue appears. In the incident it took ~2 minutes after cancelling for sonarr-anime's queue to go 0 → 2713.

Then expect a **large** backlog of real work to surface at once: `importPending` in the thousands, plus `importBlocked` and `failedPending` items that were invisible while the queue was empty. Hand those to `arr-importblocked-triage`.

## Automated coverage

`core/import_starvation.py` implements both signals; `/api/arr/import-starvation` exposes the read-only view and `stack-arr-import-starvation` is the fish wrapper. Auto-remediation runs first in `/api/arr/queue-autofix`, on the 5-minute loop — deliberately before every other check in that route, since a starved app's empty queue makes the rest of it meaningless.

## Prevention

Any bulk search recreates this. Keep missing-searches in the low hundreds and let the queue drain between rounds, or use Cleanuparr's Seeker, which paces itself via `activeDownloadLimit`.

## Common mistakes

- **Reading an empty queue as health.** The single most important line in this file.
- **Restarting the container.** It clears the in-memory command queue, so it appears to fix things, but it also strands in-flight items and destroys the evidence. Cancel the queued commands instead.
- **Treating a slow-running search as hung.** Sample its `message` field twice a few minutes apart. In the incident a `SeriesSearch` looked frozen for 2h45m but was genuinely advancing one episode at a time — it was a victim of the same rate limiting, not the cause.
- **Assuming the mount broke.** Files were arriving in `/mnt/remote/nzbdav/completed-symlinks/` correctly the entire time. Check imports before ever suspecting FUSE.

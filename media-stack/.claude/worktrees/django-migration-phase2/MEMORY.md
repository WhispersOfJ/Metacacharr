# Session memory — 2026-07-18

Working notes from a single long session, kept for future reference. Not auto-loaded
context (see `README.md`/`CLAUDE.md`/`AGENTS.md` for those) — this is a plain summary of
what changed and why, in case a later session needs the history without re-deriving it
from `git log` + conversation scrollback.

## Sonarr import-queue investigation

Started from "cancel the search backlog and push rename again" and turned into a real
incident: Sonarr's import queue (971+ `importPending` items at peak) was repeatedly
stalling with zero progress despite `ProcessMonitoredDownloads` actively running.

Root cause, confirmed four separate times in one afternoon: a single queue item wedged in
`trackedDownloadState: "importing"` (never flagged `warning`/`error`, so invisible to the
existing Unstick feature) blocks Sonarr's single disk-access execution slot, silently
stalling every other item behind it. Two distinct failure modes found:

1. **Dead Usenet article** - the symlinked file under `/mnt/nzbdav/...` gives a real
   `Input/output error` on read (confirmed via `docker exec sonarr dd if=... of=/dev/null`).
   Sometimes takes ~30-40s to surface, not instant - `rclone`/`nzbdav` retries before
   giving up. Three of the four incidents were this (all `[FFF] Shingeki no Kyojin`
   multi-part releases, `.mkv.001`/`.mkv.008` naming - later confirmed NOT a bad-batch
   release, just two isolated dead articles out of the pack, so don't over-generalize a
   whole release group as bad from one dead episode).
2. **Missing path entirely** - `outputPath` doesn't exist on disk at all (not just
   unreadable). One incident. Different from #1: `test -e` fails immediately, no dd needed.

Diagnostic recipe (now the `unstick-importing` feature, see below): find the queue
record(s) in `importing` state, `docker exec` into the arr app's own container, check the
path exists, `dd` the first 5MB with a generous timeout (~40s) to distinguish dead-article
from wedged-but-fine. Broken → remove + blocklist. Wedged or missing-path → remove without
blocklist (neither is evidence the release itself is bad) + re-search.

Also cleared: a duplicate `Kaijuu 8-gou S2` batch (11 queue records, all one shared
download, episode-mapping mismatch not a dead file) and `Steins;Gate 0`'s ambiguous-naming
season pack (22 of 23 files shared one filename with no episode number - Sonarr couldn't
map them, not a dead-article case, blocklisted so it won't regrab the same bad naming).

## New feature: `/api/arr/{app}/unstick-importing`

Built into `control-panel/app.py`, wired into `stack-arr` as a fourth action
(`stack-arr <radarr|sonarr> unstick-importing`), and **mirrored to all three repos**
(`media-stack`, `Stackalicious`, `StackScripts` - bash + zsh in both siblings, per
`AGENTS.md`'s mirror obligation). Implements the diagnostic recipe above as a real
endpoint: dedupes queue records by `downloadId` (season packs fan out to one record per
episode sharing one download), tests one representative file per download, blocklists or
clears accordingly, then fires a fresh `SeriesSearch`/`MoviesSearch`.

Commits: `media-stack@46dc108`, `Stackalicious@ca6ce25`, `StackScripts@66a674f`.

## Correction: `AGENTS.md`'s zsh claim was stale

`media-stack/AGENTS.md` said both siblings' CLIs were bash-only and to never reintroduce
zsh. **False as of this session** - both `Stackalicious` and `StackScripts` re-added full
`.../zsh/` ports after a user need for zsh came back post-v2.0.0 (confirmed live against
both siblings' own `AGENTS.md` files, which document this and have a zsh-specific
lessons-learned footnote). Fixed in `media-stack@46dc108`. **Always verify a stale-doc
claim against the sibling repos' live state before trusting `media-stack/AGENTS.md` on
this point again** - it can drift.

## Labelarr: webhook mode enabled

`docker-compose.yml`'s `labelarr` service now runs `WEBHOOK_ENABLED=true` on port 9090
(bound `127.0.0.1` only, no auth on that endpoint per its own README warning),
`PROCESS_TIMER` stretched from the 1h default to `24h` as a fallback sweep. Plex Pass was
already confirmed in use elsewhere (`plex-webhook-listener.py`), so this was a real
optimization, not blocked on a missing subscription. The Plex-side webhook URL
registration (`http://192.168.4.20:9090/webhook` in Plex's own Settings → Webhooks) is a
manual, account-level step done live by the user - not tracked by this repo.
Commit: `media-stack@46dc108`.

## Kometa Quickstart added (pre-existing work, not mine - just isolated + committed)

A `quickstart` service (`kometateam/quickstart:latest`, port 7171) was already
deployed live (uncommitted) before this session touched it. Confirmed via inspection:
its own `./config/quickstart:/config` volume is **not** wired to the real
`config/kometa/config.yml` - deliberately separate, matches Quickstart's own docs (that
path holds its SQLite DB/history/logs, not the Kometa config itself). A config built
through its UI would need manual copying into `config/kometa/config.yml` to actually take
effect; nothing automates that link. Isolated cleanly from an unrelated dirty
`plex/duplicates` + `plex/tmdb-missing` feature sitting in the same files (see below) and
committed separately: `media-stack@1e60726`.

## `/api/plex/tmdb-missing` added (also pre-existing work, isolated + committed)

Was already live in the running `control-panel` container (picked up incidentally by an
earlier rebuild) but uncommitted. Tested working: returns every movie/show across every
library with neither a `tmdb://` Guid nor the legacy `com.plexapp.agents.themoviedb://`
agent id, via one `includeGuids=1` request per library rather than a per-item fetch. CLI
wrappers (`stack-tmdb-missing` in fish + bash/zsh in both siblings) already existed too.
Committed and mirrored: `media-stack@eff4984`, `Stackalicious@93d2cd1`,
`StackScripts@05a043c`. `tmdb_audit_report.csv` (the separate, already-committed
`scripts/audit-tmdb-links.py`'s default CSV output) is now gitignored rather than
committed - it's regenerated report data, not source, same pattern as `backups/`.

## Git workflow note for future sessions with mixed dirty state

Several times this session, the working tree had **two unrelated in-progress features
mixed into the same files** (my new work + pre-existing uncommitted work from an earlier
session I had no context on, e.g. Quickstart and `plex/duplicates`/`tmdb-missing` showing
up interleaved with `unstick-importing` in `app.py`/`README.md`/`docker-compose.yml`).
**Never `git add` a whole file in that situation** - it silently commits work you can't
vouch for. The technique used repeatedly: build the intended file content in a scratch
copy (HEAD content + only the known intended edit, via an anchor-based Python string
replace), `git hash-object -w` it, `git update-index --cacheinfo 100644,<blob>,<path>` to
stage that exact content without touching the working tree, then verify with
`git diff --cached` (should show only your change) and `git diff` (should show only the
remaining unrelated change). Validate the staged-only slice before committing with
`git stash push --keep-index` (runs CI-equivalent checks against exactly what will be
committed, not the mixed working tree), then `git stash pop` to restore the rest.

## Kometa config: Oscars-only, all other collections/overlays removed

`config/kometa/config.yml` (gitignored, live config - not in git history) reduced in two
passes: first removed `oscars` from `TV Shows`/`Anime Movies`/`Anime Shows` (kept in
`Movies` only), then a follow-up request stripped **everything else** too - `Movies` now
has `collection_files: [oscars]` and no `overlay_files` (ribbon removed), the other three
libraries have neither `collection_files` nor `overlay_files` at all. `remove_overlays:
true` kept on all four (correct behavior, not a leftover - with `overlay_files` gone this
is what actually strips any previously-applied overlays). `playlist_files` (top-level,
outside `libraries:`) deliberately left untouched - confirmed with the user this counts as
a separate global block, not a per-library "section." Not yet applied against Plex - needs
a manual `stack-kometa-run` (container's `sleep infinity` entrypoint means restarts don't
trigger a run - this is load-bearing, not a bug, see `docker-compose.yml`'s own comment on
the `kometa` service).

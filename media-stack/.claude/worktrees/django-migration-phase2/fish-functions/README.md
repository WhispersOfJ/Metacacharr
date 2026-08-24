# Fish functions

All fish functions used on this host, mirrored here from `~/.config/fish/functions/` for version control. Most target this project's Control Panel API at `192.168.4.20:8420`; a handful are general shell/host utilities unrelated to the stack.

Install with `scripts/fish-functions-install.py`, which symlinks every
`stack-*.fish` and `__stack_*.fish` into `~/.config/fish/functions/` and every
generated completion into `~/.config/fish/completions/`. It prunes dead
`stack-*` commands but never a `__stack_*` helper that exists only on the host,
since that would be the only copy.

## Arr instances

Every command that takes an Arr app accepts `radarr` or `sonarr` - the only
two Arr instances in this stack. (radarr-anime/sonarr-anime were retired
2026-08-18, merged into these two via genre/tag routing.) `__stack_arr_app`
validates the name, so every command shares one guard instead of each
re-implementing its own.

`stack-arr-toggle-search all` covers both.

## Tab completion

Every command has completions, generated from the functions themselves by
`scripts/fish-completions-generate.py` - argparse flags, `contains` guards, and
each `# Usage:` header. A gate test fails if a function changes and its
completion does not, so they cannot drift.

Container names and Plex Butler task names are resolved at tab time rather than
baked in, so a newly-added service is completable the moment it is up.

```fish
stack-arr <TAB>                # radarr sonarr
stack-arr radarr <TAB>         # rss-sync search-missing unstick unstick-importing
stack-container restart <TAB>  # live container names
stack-loop-exclude --<TAB>     # --yes
```

Regenerate after editing any function:

```fish
scripts/fish-completions-generate.py
scripts/fish-functions-install.py
```

---

## Personal shell utilities

Not stack-specific — general-purpose fish helpers.

- **`alacritty-use-theme <theme>`** — switch the active Alacritty theme (aliases.toml aware).
- **`backup <file>`** — copy a file to `<file>.bak`.
- **`claudehome`** — `cd ~/Claude` and launch Claude Code with permissions skipped and that directory added.
- **`cleanup`** — remove orphaned pacman packages in a loop until none remain.
- **`copy <dir1> <dir2>`** — recursive copy, trimming a trailing slash from the source first.
- **`history [args...]`** — fish's builtin history with timestamps shown, forwarding all arguments so subcommands like `history clear`/`history search` still work.
- **`__history_previous_command`** / **`__history_previous_command_arguments`** — bang-bang (`!!`) / bang-dollar (`!$`) history expansion support.
- **`TMDB`** — `cd` into the repo and run `scripts/audit-tmdb-links.py` against the Movies library, writing a CSV report.

## Core helper

- **`__stack_arr_app <name> [--container]`** — validates an Arr instance name (`radarr` or `sonarr`). Every app-taking command funnels through it, so the accepted names are defined once rather than in separate guards.
- **`__stack_containers`** — container names for tab completion, live from Docker with `docker-compose.yml` as a fallback.
- **`__stack_plex_butler_tasks`** — the Butler task names, read out of `stack-plex-butler.fish` itself so the completion cannot drift from what the command validates.
- **`__stack_api <METHOD> <PATH> [JSON_BODY]`** — private helper every `stack-*` function funnels through. Calls Control Panel's API and prints its `message` field, handling both response shapes (`{"ok","message",...}` on success, FastAPI's `{"detail": {...}}` wrapper on an error). Exit status mirrors the API's own `ok` field.

## Container control & stack status

- **`stack-status`** — live running/health state of every container.
- **`stack-container <restart|stop|start> <name>`** — control a single container.
- **`stack-restart-all [-y|--yes]`** — restart every container in the stack; confirms first unless `-y` is given.
- **`stack-resource-check`** — containers missing an explicit `mem_limit`/`cpus`.
- **`stack-oom-check`** — containers Docker has recorded an OOM-kill for.
- **`stack-image-check`** — checks every pinned image tag for a newer registry digest (no pull).
- **`stack-top [cpu|mem] [limit]`** — top containers by CPU or memory usage.
- **`stack-disk-config-sizes`** — per-app `config/` directory size, largest first.
- **`stack-docker-disk-usage`** — Docker disk usage broken down by images/containers/volumes/build cache.
- **`stack-mount-health`** — checks every known FUSE mountpoint resolves cleanly.
- **`stack-perms-check`** — config files unreadable by group/other (won't get backed up).
- **`stack-version`** — README's declared version plus a live container count.
- **`stack-help`** — lists every `stack-*` command with a one-line description.

## Radarr / Sonarr (general)

- **`stack-arr <radarr|sonarr> <rss-sync|search-missing|unstick|unstick-importing>`** — trigger RSS sync, a missing search, or clear a wedged queue item. `unstick` only touches items the app itself flagged; `unstick-importing` targets a different failure mode — a download stuck in `trackedDownloadState "importing"` while `trackedDownloadStatus` stays `ok`, so it never trips the normal flag.
- **`stack-arr-toggle-search <radarr|sonarr|all> <on|off>`** — turn RSS sync + automatic search on/off for every indexer, without touching manual search. Useful for pausing new grabs while an import queue drains.
- **`stack-arr-logs <radarr|sonarr|prowlarr> [lines]`** — tail an app's container log directly.
- **`stack-arr-backlog <radarr|sonarr>`** — the app's internal command-queue backlog (searches, RSS sync, bulk moves).
- **`stack-arr-import-backlog`** — items sitting on "waiting on import" across both apps, grouped by release rather than printed per-episode.
- **`stack-arr-import-candidates <radarr|sonarr>`** — files stuck in the queue ready to manually import, numbered for `stack-arr-import`.
- **`stack-arr-import <radarr|sonarr> <index>`** — import one file by index from `stack-arr-import-candidates`.
- **`stack-arr-import-all <radarr|sonarr>`** — import every candidate in one call instead of one at a time.
- **`stack-arr-missing-aired <radarr|sonarr>`** — monitored items with no file that have already aired/released, filtering out upcoming ones.
- **`stack-arr-queue-errors`** — queue items across every app already flagged as a problem by the app itself.
- **`stack-arr-import-starvation`** — why nothing is importing when the queue looks empty and clean. `RefreshMonitoredDownloads` both polls the download client and triggers imports, so a bulk search backlog that starves it out of the command pool stops imports *and* empties the queue at once, making every other queue check read healthy on a fully broken app (2026-08-08 incident). Read-only; the auto-remediation runs inside `stack-queue-autofix`. See the `arr-import-starvation-diagnosis` skill.
- **`stack-queue-autofix`** — blocklists+re-searches `failedPending` items in Radarr/Sonarr and Radarr's `importBlocked` items (always remove+research, no manual-import attempt first), disables `autoRedownloadFailed` if a retry storm is detected (≥15 failedPending in one pass), clears any search backlog starving imports, and reports NzbDAV queue health. Distinct from `unstick` — `unstick` only catches `trackedDownloadStatus warning/error`, which `failedPending` items don't set. Powers the recurring 5-minute queue-monitoring loop.
- **`stack-arr-blocklist <radarr|sonarr> [limit]`** — recent blocklisted releases.
- **`stack-arr-clear-blocklist <radarr|sonarr> [-y|--yes]`** — clear every blocklisted release; confirms first unless `-y`.
- **`stack-arr-list-implementations <radarr|sonarr>`** — every import-list type the app's build supports, configured or not.
- **`stack-import-lists <radarr|sonarr>`** — configured import lists and their enabled state.
- **`stack-cutoff-unmet <radarr|sonarr> [limit]`** — items below their quality profile's cutoff (have a file, just not the target quality).
- **`stack-arr-recently-added <radarr|sonarr> [limit]`** — recently added items with file/episode status.
- **`stack-customformat-diff <radarr|sonarr>`** — diffs current custom-format scores against the last check, then updates the cache.
- **`stack-command-queue-summary`** — command-queue backlog across radarr/sonarr/prowlarr at once.
- **`stack-queue-status`** — every app's download queue with live-measured speed/ETA (two samples, ~4s apart).
- **`stack-backlog-status`** — every app's wanted/missing backlog with a throughput-projected ETA.
- **`stack-sonarr-fix-episode-monitoring`** — fixes any episode left unmonitored under a monitored Sonarr series/season (season 0 left alone).

## List imports (Radarr/Sonarr)

Most take `[--no-search] [--no-monitor] [--dry-run]`; list-scraping ones also take `[--limit N]`.

- **`stack-letterboxd-radarr <film-url>`** — add one Letterboxd film to Radarr, scraping its TMDb id server-side.
- **`stack-letterboxd-radarr-list <list-url>`** — add every film in a Letterboxd list.
- **`stack-letterboxd-radarr-watchlist <user-url>`** — add every film in a user's watchlist.
- **`stack-letterboxd-radarr-watched <user-url>`** — add every film a user has watched.
- **`stack-letterboxd-radarr-collection <collection-url>`** — add every film in a Letterboxd film collection.
- **`stack-letterboxd-radarr-filmography <role> <slug>`** — add a person's whole filmography by crew role (actor, director, writer, producer, editor, cinematography, composer, etc).
- **`stack-letterboxd-radarr-popular`** — add Letterboxd's current popular films.
- **`stack-letterboxd-radarr-list-random`** — picks one random URL from a cached list of featured Letterboxd lists and imports it, removing it from the cache so a future run won't repeat it.
- **`stack-mdblist-import <mdblist-list-url>`** — import a public MDBList list, routing movies to Radarr and TV to Sonarr in one call.
- **`stack-trakt-import-list <radarr|sonarr> <trakt-username> <trakt-listname> <display-name> [--no-search]`** — add a public Trakt list as an import list.
- **`stack-radarr-import-list <list-url> <display-name> [--no-search]`** — add a hosted Radarr-list-format JSON URL as a Radarr import list.
- **`stack-sonarr-import-custom-list <base-url> <display-name> [--no-search]`** — add a generic JSON/RSS feed as a Sonarr import list.
- **`stack-tmdb-import-company <tmdb-company-id> <display-name> [--no-search]`** — add a studio's filmography as a Radarr import list.
- **`stack-tmdb-import-keyword <tmdb-keyword-id> <display-name> [--no-search]`** — add a TMDB keyword-filtered list as a Radarr import list.
- **`stack-plex-import-watchlist <radarr|sonarr> [--no-search]`** — add your own Plex watchlist as a native import list (uses Plex's own OAuth token already set up in that app).
- **`stack-plex-import-rss <radarr|sonarr> <plex-watchlist-rss-url> [--no-search]`** — add a Plex Watchlist RSS feed URL as an import list (polls the public feed instead of using an account token).

### Tracked lists (nightly diff-only sync)

The one-shot commands above import a list once. These register a list for the nightly
diff-only sync instead (`systemd/stack-letterboxd-sync.timer`, 04:00 daily), so only titles
added to the list since the last run get pushed. A tracked list stays synced until it is
explicitly untracked. Both families take `[--label TEXT]` on `track`.

- **`stack-letterboxd-radarr-track <list-url> [--label TEXT]`** — register a Letterboxd list for the nightly sync.
- **`stack-letterboxd-radarr-untrack <list-url>`** — stop syncing a tracked Letterboxd list.
- **`stack-letterboxd-radarr-tracked`** — every Letterboxd list currently registered.
- **`stack-letterboxd-radarr-history`** — recent Letterboxd sync runs and what each added.
- **`stack-mdblist-radarr-track <list-url> [--label TEXT]`** — same, for an MDBList list.
- **`stack-mdblist-radarr-untrack <list-url>`** — stop syncing a tracked MDBList list.
- **`stack-mdblist-radarr-tracked`** — every MDBList list currently registered.
- **`stack-mdblist-radarr-history`** — recent MDBList sync runs.

### Loop remediation

For a title that keeps getting grabbed, failing, and re-grabbed. `stack-queue-autofix`'s
history is what identifies the loop; these three act on it.

- **`stack-loop-candidates <radarr|sonarr>`** — titles or episodes with 2+ `downloadFailed` events in the recent autofix history, with a suggested remediation for each.
- **`stack-loop-unmonitor <radarr|sonarr> <id> [-y|--yes]`** — unmonitor a confirmed looping movie or episode. Confirms first unless `-y`.
- **`stack-loop-exclude <movie-id> [-y|--yes]`** — add a Radarr movie to Exclusions. The durable fix: unmonitoring alone gets undone by the next import-list sync. Radarr only, Sonarr has no episode-level equivalent.

## Ratings

Standalone `OMDB_KEY`/`MDBLIST_KEY` secrets — no other app dependency.

- **`stack-rating-imdb <imdb-id>`** — a title's IMDb rating via OMDb.
- **`stack-rating-mdblist <imdb-id>`** — a title's MDBList score plus its IMDb sub-rating if MDBList has one.

## Prowlarr

- **`stack-prowlarr-indexers`** — every configured indexer's enabled state and priority.

## Plex

- **`stack-plex <scan|empty-trash|optimize-db|clean-bundles>`** — trigger a Plex maintenance action.
- **`stack-plex-libraries`** — list Plex library names.
- **`stack-plex-empty-trash [library ...]`** — empty trash on one library, or every library if none given.
- **`stack-plex-analyze [library ...]`** — queue deep media analysis (loudness, chapter thumbnails, intro/credits/ad markers, voice activity) for one library, or all of them.
- **`stack-plex-duplicates [min_gb]`** — flag movies carrying redundant duplicate files well beyond a normal multi-version upgrade.
- **`stack-plex-sessions`** — who's watching what right now, direct play vs transcode per session.
- **`stack-plex-recently-added [limit]`** — what's actually finished importing and become visible in Plex (distinct from `stack-arr-recently-added`, which shows what was added to management, not necessarily downloaded).
- **`stack-plex-updates`** — checks whether Plex has a newer release on its current channel (check only, doesn't apply it — this stack pins Plex deliberately).
- **`stack-tmdb-missing`** — scans every movie/show library for items with no TMDb link, writes them to `~/missing.txt`.

### Plex Butler tasks

`stack-plex-butler <task>` fires one on demand (run with no args for the full list); each also has its own dedicated wrapper:

- **`stack-plex-butler-all`** — fire every Butler task, one request at a time (the 19 named tasks plus `optimize-db` and `clean-bundles`). Sequential on purpose: 21 maintenance jobs at once against the same Plex DB and FUSE mount is how the stale-handle/contention incidents started.

- **`stack-plex-automatic-updates`** — Plex's own app-update check.
- **`stack-plex-backup-database`** — back up Plex's database.
- **`stack-plex-clean-cache-files`** — delete old cache files.
- **`stack-plex-clean-log-files`** — delete old supplemental log files.
- **`stack-plex-deep-media-analysis`** — full deep analysis across every library.
- **`stack-plex-garbage-collect-blobs`** — garbage-collect unused metadata blobs.
- **`stack-plex-garbage-collect-media`** — garbage-collect unused library media records.
- **`stack-plex-generate-ad-markers`** — generate ad-break markers.
- **`stack-plex-generate-chapter-thumbs`** — generate chapter thumbnail (BIF) files.
- **`stack-plex-generate-credits-markers`** — generate end-credits markers.
- **`stack-plex-generate-intro-markers`** — generate intro markers.
- **`stack-plex-generate-media-index`** — generate media index files for fast seeking.
- **`stack-plex-generate-voice-activity`** — generate voice-activity data for dialogue boost.
- **`stack-plex-loudness-analysis`** — analyze audio loudness for volume leveling.
- **`stack-plex-music-analysis`** — analyze music library audio.
- **`stack-plex-process-assets`** — process pending local assets (posters, themes, etc).
- **`stack-plex-refresh-epg`** — refresh Live TV/DVR EPG guide data.
- **`stack-plex-refresh-libraries`** — refresh metadata for every library.
- **`stack-plex-refresh-local-media`** — refresh local media file changes.
- **`stack-plex-upgrade-media-analysis`** — re-run analysis for items whose analysis version is outdated.

## NzbDAV

- **`stack-nzbdav-queue`** — current Usenet download queue.
- **`stack-nzbdav-history [limit]`** — recent download history (completed/failed).
- **`stack-nzbdav-stats`** — aggregate queue/history counts.
- **`stack-nzbdav-delete-failures`** — delete every "Failed" entry from history (a Failed row can block re-grabbing a release with a matching name).
- **`stack-nzbdav-dedup-check`** — verifies `api.duplicate-nzb-behavior` is still `mark-failed`. Guards against the return of the `(2)`/`(3)`-suffix `importBlocked` bug, where a duplicate grab lands as "Title (2)" and the Arr app cannot import it.

## Cleanuparr

- **`stack-cleanuparr-instances`** — which *arr apps Cleanuparr actually has a connected instance for.
- **`stack-cleanuparr-strikes [limit]`** — recent stalled/slow/malware strikes.

## Seerr

- **`stack-seerr-requests [pending|approved|available|all]`** — media requests sitting in Seerr, by status.

## Backup

- **`stack-claude-full-backup`** — one-off full `~/Claude` tree tar.zst backup to Dropbox, dated and not overwritten in place.

## Notifications

- **`stack-notify-test`** — send a real test message to the stack's Discord webhook.

## Host / system diagnostics

- **`stack-disk-free [warn-pct] [crit-pct]`** — real-filesystem disk free space with pass/warn/fail marks.
- **`stack-disk-health`** — SMART health summary for every physical disk.
- **`stack-mem-pressure`** — kernel PSI (pressure stall info) for memory, CPU, and IO.
- **`stack-kernel-check`** — compares the running kernel against the installed one (a mismatch means a reboot is needed).
- **`stack-reboot-check`** — checks for a pending-reboot marker and cross-references `stack-kernel-check`.
- **`stack-uptime-report`** — uptime, load average, and whether the last shutdown was clean.
- **`stack-zombie-check`** — lists zombie/defunct processes and their parent.
- **`stack-service-failed`** — `systemctl --failed` across both system and user manager instances.
- **`stack-timer-status`** — enabled state + last-run result for every `stack-*.timer` unit.
- **`stack-cron-list`** — system timers, user timers, and crontab entries in one view.
- **`stack-journal-errors`** — error-or-worse journal entries since last boot, summarized by unit.
- **`stack-journal-size [--vacuum-size SIZE]`** — journald's on-disk usage; optionally vacuum it down.
- **`stack-firewall-status`** — active nftables rule summary plus every listening port.
- **`stack-ssh-doctor`** — checks `~/.ssh` exists, `known_hosts` has a GitHub entry, and a private key is present and loadable.
- **`stack-git-status-all`** — `git status --short` across every repo directly under `~/Claude`.
- **`stack-pkg-updates`** — pending pacman + AUR updates.
- **`stack-pkg-update [--yes]`** — run the actual system update (confirmation-gated).
- **`stack-pkg-history [N]`** — tail of pacman's transaction log.
- **`stack-pkg-orphans [--remove]`** — list (or remove) orphaned packages.
- **`stack-pkg-clean-cache [keep-N]`** — vacuum pacman's package cache to the last N versions per package.
- **`stack-aur-audit`** — cross-checks installed packages against Arch security advisories, or lists AUR/foreign packages if `arch-audit` isn't installed.
- **`stack-flatpak-updates [--apply]`** — list, or apply, pending Flatpak updates.
- **`stack-log-levels [reset]`** — check, or reset, every Servarr app's log level.

The 2026-07-30 awesome-arr batch (Tautulli, Wrapperr, Maintainerr, Lingarr, Prefetcharr)
was fully decommissioned (see PLANS.md) — their fish commands are gone.

## 2026-08 additions — new-services batch (PLANS.md Phases 1–3)

### WatchState (Phase 6)

Keeps its own record of what has been watched, fed from Plex by **both** a scheduled import (hourly at :25, skipping 02:00-05:59 so it never overlaps the poster sync, Arr backup, Letterboxd sync or Plex's Butler window) **and** a webhook. Both stay on: upstream warns webhooks drop events, so neither is redundancy to remove.

- **`stack-watchstate-status`** — tracked item count, when the import last ran and when it runs next, whether one is queued. Also reports `export_enabled`, which is off by design — export writes watch state back *into* Plex — so a silent flip shows up here.
- **`stack-watchstate-import-now`** — queues an out-of-schedule import. Queued, not run: WatchState's dispatcher picks it up within a minute, so the result appears in `stack-watchstate-status`, not in this command's output.
- **`stack-watchstate-history [title] [limit]`** — watch history, newest first, optionally filtered to matching titles (partial names work). Each row carries `via` (which backend reported it) and `updated_at`, which is how a webhook-delivered event is told apart from one the scheduled import picked up.

---
name: stack-cli-plex-kometa
description: Exact fish CLI command reference for Plex operations against this stack's Control Panel (library scan/maintenance, watch sessions/history, duplicates, TMDb-link audit, Butler tasks, watchlist/RSS import). Use whenever the user asks to scan Plex, check who's watching, find duplicate files, check for a Plex update, run a Butler task, generate markers, or import a Plex watchlist to Radarr/Sonarr from the terminal. Trigger phrases: "scan plex", "who's watching", "empty plex trash", "find duplicate movies", "check plex update", "what's missing a tmdb link", "generate intro markers", "run butler task", "refresh epg", "import plex watchlist to radarr", "deep media analysis".
---

# Stack CLI: Plex

<skill_scope skill="stack-cli-plex-kometa">
This is a command reference, not an operational tool: it exists so the exact fish function name, argument order, and output shape for every Plex terminal command in this stack is already known, without reading `~/.config/fish/functions/stack-plex*.fish` fresh each time. Every command here is a thin fish wrapper around Control Panel's own HTTP API (`http://192.168.4.20:8420`); the actual behavior lives in `control-panel/main.py` plus the relevant `control-panel/services/<name>/router.py` (`services/plex/router.py` for the commands below). Kometa is deployed and live in this stack - see the `stack-cli-usenet-queue`/other skills or `services/kometa/router.py` for its commands. Tautulli (and Wrapperr) were decommissioned entirely on 2026-08-20 - see PLANS.md - and no longer have a router or fish commands.
</skill_scope>

## Calling convention

<calling_convention>
Most commands here `curl` their endpoint directly and pipe through an inline `python3 -c "..."` formatter that unwraps FastAPI's `{"detail": {...}}` shape if present, then prints `data['message']` followed by any list items. A few bare ones (`stack-plex-libraries`) go through the `__stack_api` helper instead; for `/api/plex/libraries` specifically the response has no `message` key (it's a bare JSON array of `{key, title}` objects), so `__stack_api`'s fallback prints the full indented JSON array rather than a message string.

None of these read a `STACK_HOST_IP` environment variable - the Control Panel URL is a literal hardcoded string in every function.

Every `stack-plex-<butler-task-name>` command (`stack-plex-clean-cache-files`, `stack-plex-generate-intro-markers`, etc.) is a fixed one-line wrapper around `POST /api/plex/butler/<task>` - same generic route `stack-plex-butler` hits with a variable task name. They exist so a task can be named directly instead of remembering `stack-plex-butler`'s exact string.
</calling_convention>

## Command reference

<command_reference>
| Command | Args | What it does |
|---|---|---|
| `stack-plex` | `<scan\|empty-trash\|optimize-db\|clean-bundles>` | One Plex maintenance action: `scan` refreshes every library section for new files, `empty-trash` permanently removes already-deleted items, `optimize-db` runs Plex's own DB optimization, `clean-bundles` removes metadata bundles Plex no longer needs. |
| `stack-plex-libraries` | none | Lists Plex library names - the input `stack-plex-empty-trash` takes. |
| `stack-plex-updates` | none | Checks whether Plex has a newer release on its current channel. Check only - this stack pins Plex's image deliberately and never auto-applies an update. |
| `stack-plex-empty-trash` | `[library name]` (none = every library) | Empty trash scoped to one named library (case-insensitive match against the Plex title; quote multi-word titles, e.g. `"TV Shows"` - all args are joined into a single library name, not iterated as separate targets) instead of everything. |
| `stack-plex-duplicates` | `[min_gb]` (default 5.0) | Flags movies whose combined file size looks like more than one real release stacked up (well beyond a single legitimate multi-version upgrade). Real incident: found ~700GB of redundant duplicate releases in one session this way. |
| `stack-plex-sessions` | none | Who's watching what right now - user, title, direct-play vs. transcode decision, progress, per session. |
| `stack-plex-recently-added` | `[limit]` (default 15) | What actually finished importing and became visible in Plex. Distinct from `stack-arr-recently-added` (see the `stack-cli-arr-fleet` skill), which shows what was added *to Radarr/Sonarr's management*, not necessarily downloaded or visible yet. |
| `stack-tmdb-missing` | none | Scans every movie/show library for items with no TMDb link (neither the new nor legacy Plex agent's Guid) and writes them to `~/missing.txt`. Overwrites on every run - a rescan tool, not an appending log. |
| `stack-plex-butler` | `<task>` | Fires any named Plex Butler task; run with no args or an unknown task to print the full accepted-task list (kept only in `control-panel/app.py`'s `PLEX_BUTLER_TASKS`, not duplicated here, so it can't drift). `optimize-db`/`clean-bundles` are NOT in this list - they're `stack-plex` subcommands instead. |
| `stack-plex-analyze` | `[library name]` (none = every library) | Queues Plex's per-item deep analysis (loudness, chapter thumbs, intro/credits/ad markers, voice activity) scoped to one named library (quote multi-word titles) via `PUT /library/sections/{key}/analyze`. Narrower than the Butler `deep-media-analysis` task below - use this to re-analyze just the library whose settings changed. |
| `stack-plex-deep-media-analysis` | none | Butler task `DeepMediaAnalysis` - runs full deep analysis (loudness, chapter thumbs, markers, voice activity) server-wide in one Plex-side pass. Not a fish-level composite that calls the individual `generate-*`/`loudness-analysis` commands below one by one - it's a single Butler task Plex itself bundles those into. |
| `stack-plex-upgrade-media-analysis` | none | Butler task `UpgradeMediaAnalysis` - re-runs analysis server-wide for items whose analysis version is outdated. Same relationship to the individual tasks as `deep-media-analysis` above: one bundled Plex-side task, not a fish loop over the others. |
| `stack-plex-loudness-analysis` | none | Butler task: analyze audio loudness for volume leveling. |
| `stack-plex-music-analysis` | none | Butler task: analyze music library audio. |
| `stack-plex-generate-ad-markers` | none | Butler task: generate ad-break markers for eligible media. |
| `stack-plex-generate-credits-markers` | none | Butler task: generate end-credits markers for eligible media. |
| `stack-plex-generate-intro-markers` | none | Butler task: generate intro markers for eligible media. |
| `stack-plex-generate-voice-activity` | none | Butler task: generate voice-activity data (used for dialogue boost). |
| `stack-plex-generate-chapter-thumbs` | none | Butler task: generate chapter thumbnail (BIF) files. |
| `stack-plex-generate-media-index` | none | Butler task: generate media index files used for fast seeking. |
| `stack-plex-garbage-collect-blobs` | none | Butler task: garbage-collect unused metadata blobs. |
| `stack-plex-garbage-collect-media` | none | Butler task: garbage-collect unused library media records. |
| `stack-plex-clean-cache-files` | none | Butler task: delete old Plex cache files. |
| `stack-plex-clean-log-files` | none | Butler task: delete old supplemental Plex log files. |
| `stack-plex-process-assets` | none | Butler task: process pending local assets (posters, themes, etc). |
| `stack-plex-refresh-libraries` | none | Butler task `RefreshLibraries` - refreshes metadata for every library server-wide, on Plex's own Butler schedule/mechanism. Not the same call as `stack-plex scan` (a direct library-section refresh) - see common mistakes. |
| `stack-plex-refresh-local-media` | none | Butler task `RefreshLocalMedia` - refreshes local media *file* changes (new/changed files on disk), distinct from `refresh-libraries`' metadata refresh. |
| `stack-plex-refresh-epg` | none | Butler task: refresh Live TV/DVR EPG guide data. Only meaningful if Live TV/DVR is configured; this stack otherwise has no EPG source. |
| `stack-plex-automatic-updates` | none | Butler task: trigger Plex's own app-update check. Unrelated to library media - same read-only-ish caveat as `stack-plex-updates` (doesn't apply an update). |
| `stack-plex-backup-database` | none | Butler task: back up Plex's database to its own configured backup directory (a Plex-internal backup, unrelated to any stack-level backup mechanism). |
| `stack-plex-import-watchlist` | `<radarr\|sonarr> [--no-search]` | Adds your own Plex account watchlist as a native import list (`PlexImport`) on the given app. Requires that app's Plex OAuth link already set up - this only creates the list entry, not the auth link. `--no-search` skips triggering a search on add. |
| `stack-plex-import-rss` | `<radarr\|sonarr> <plex-watchlist-rss-url> [--no-search]` | Adds a public Plex Watchlist RSS feed URL (from `https://app.plex.tv/desktop/#!/settings/watchlist`) as an import list (`PlexRssImport`). Polls the public RSS feed instead of using your account token - see common mistakes for how this differs from `stack-plex-import-watchlist`. |
</command_reference>

## Common mistakes

<common_mistakes>
<general_anti_patterns>
- **Confusing the two "recently added" commands.** `stack-arr-recently-added <app>` (arr-fleet skill) is about management state in Radarr/Sonarr; `stack-plex-recently-added` is about what Plex itself has actually indexed and made playable. A title can show in one and not the other - that gap is itself diagnostic (added to management but not yet imported, or imported but Plex hasn't scanned yet).
- **Expecting `stack-tmdb-missing` to print results inline.** It writes to `~/missing.txt` and only prints a count - read that file for the actual list, don't assume the terminal output is complete.
- **Suggesting `stack-plex-updates` will apply an update.** It's read-only by design; this stack manually bumps Plex's pinned image tag rather than trusting Watchtower with it (see this repo's CLAUDE.md on image pinning policy).
- **Confusing `stack-plex-refresh-libraries` with `stack-plex scan`.** Both refresh library metadata, but `refresh-libraries` is Plex's own Butler task (`RefreshLibraries`, server-wide, runs on Plex's internal Butler mechanism); `stack-plex scan` calls the direct library-section refresh endpoint. `stack-plex-refresh-local-media` is different again - it refreshes local media *file* changes on disk, not metadata.
- **Confusing the two Plex watchlist import commands.** `stack-plex-import-watchlist` uses your own Plex account token directly (`PlexImport` - requires that app's Plex OAuth already linked); `stack-plex-import-rss` instead polls a public RSS feed URL (`PlexRssImport`, no account token needed on the app side, but the RSS URL itself must be fetched from your Plex watchlist settings page first). They're not interchangeable and use different Radarr/Sonarr import-list implementations.
- **Assuming `stack-plex-deep-media-analysis`/`stack-plex-upgrade-media-analysis` are fish-level composites that call the individual `generate-*`/`loudness-analysis`/`music-analysis` commands.** They aren't - each is its own single Plex Butler task (`DeepMediaAnalysis`/`UpgradeMediaAnalysis`) that Plex bundles server-side; the fish/Control-Panel layer never loops over the narrower tasks itself.
- **Treating `stack-plex-backup-database` as this stack's real backup mechanism.** It only triggers Plex's own internal DB backup to its configured directory. As of 2026-08-12 this stack has no stack-level backup mechanism of any kind (restic was removed entirely, see `stack-cli-infra-ops`'s common mistakes).
</general_anti_patterns>
</common_mistakes>

## Resources

<resources>
**Local:**
- `~/.config/fish/functions/stack-plex*.fish`, `stack-tmdb-missing.fish` - the actual fish source these commands wrap (the `stack-plex*` glob already covers every Butler-task, analysis, and import-list wrapper added above - no per-file listing needed)
- `control-panel/main.py` + `services/plex/router.py` in this repo - the real behavior behind every endpoint these commands call
</resources>

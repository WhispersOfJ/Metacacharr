---
name: stack-cli-arr-fleet
description: Exact fish CLI command reference for Radarr/Sonarr operations against this stack's Control Panel (queue, backlog, missing/cutoff-unmet items, manual import, RSS sync, unstick, import-list implementations, custom-format-diff), plus Bazarr subtitle operations (history, provider status, missing search, wanted). Use whenever the user asks to check, search, import, or unstick something in Radarr or Sonarr from the terminal, check custom-format score changes, list import-list implementation types, or check Bazarr subtitle status/history. Trigger phrases: "search missing on radarr", "what's stuck in sonarr's queue", "import this file", "check the arr backlog", "cutoff unmet", "recently added to radarr", "what import list types does radarr support", "did any custom format scores change", "bazarr history", "missing subtitles".
---

# Stack CLI: Arr Fleet

<skill_scope skill="stack-cli-arr-fleet">
This is a command reference, not an operational tool: it exists so the exact fish function name, argument order, and output shape for every Radarr/Sonarr terminal command in this stack is already known, without reading `~/.config/fish/functions/stack-arr*.fish` fresh each time. Every command here is a thin fish wrapper around Control Panel's own HTTP API (`http://192.168.4.20:8420`) - the wrapper adds argument validation and human-readable formatting, nothing more; the actual behavior lives in `control-panel/main.py` plus `control-panel/services/arr/router.py`, `services/bazarr/router.py`, and `services/queue/router.py` (`app.py` is retired dead code, not the live source).

**Related skills:** `arr-config-sync` operates at a different layer - it backs up/restores/diffs Radarr/Sonarr *configuration* (root folders, quality profiles, indexers) via their REST APIs directly, not runtime queue/backlog state, and doesn't go through Control Panel or these fish commands at all. Reach for that skill when the question is about config, this one when it's about what's currently happening in the queue/backlog.

Bazarr is included in this skill, not a separate one, because it exists purely to watch Radarr/Sonarr's libraries for missing subtitles and fetch them - it has no independent library of its own, so its commands belong with the fleet they serve.
</skill_scope>

## Calling convention

<calling_convention>
Every command in this file follows one of two shapes:

1. **Bare API passthrough** - `__stack_api METHOD /api/path` (a private fish helper). Prints the response's `message` field and exits 0/1 based on the response's `ok` field. No custom formatting.
2. **Custom formatter** - `curl` the endpoint directly, pipe through an inline `python3 -c "..."` that unwraps FastAPI's `{"detail": {...}}` HTTPException shape if present, prints `data['message']`, then loops over a list field (`items`, `apps`, etc.) with per-line formatting specific to that command.

All commands validate `radarr`/`sonarr` as the only accepted app argument (case-sensitive, exact match) before making the request, and print a `Usage: ...` line to stderr and return 1 on a bad invocation - run a command with no args (or `-h`) to see its own usage line rather than guessing the argument order.

None of these commands take a `--host` flag or read a `STACK_HOST_IP` environment variable, despite what other docs in this repo family suggest - the Control Panel URL is a literal hardcoded string in every function. Run them from any machine on the LAN or Tailscale mesh; the target host doesn't change.
</calling_convention>

## Command reference

<command_reference>
| Command | Args | What it does |
|---|---|---|
| `stack-arr` | `<radarr\|sonarr> <rss-sync\|search-missing\|unstick\|unstick-importing>` | Triggers one maintenance action. `unstick` only touches items the app itself flagged (warning/error state). `unstick-importing` is a separate failure mode - a download wedged in `importing` state that never lights up that flag; this reads the first few MB of the file through the app's own container mount to distinguish a genuinely dead article from a merely-wedged slot, blocklists only the former, then re-searches either way. |
| `stack-arr-backlog` | `<radarr\|sonarr>` | The app's internal command-queue backlog (searches, RSS syncs, bulk moves) - what's currently running and the oldest queued items. Surfaces a hung command silently backing up everything behind it. |
| `stack-arr-import-candidates` | `<radarr\|sonarr>` | Numbered list of files stuck in the queue that are ready to manually import. Use the printed index with `stack-arr-import`. |
| `stack-arr-import` | `<radarr\|sonarr> <index>` | Imports the candidate at `<index>` from the list `stack-arr-import-candidates` just printed - re-fetches the list fresh first since it can change between calls, so the index must come from a call made just before. |
| `stack-arr-import-all` | `<radarr\|sonarr>` | Imports every current candidate in one `ManualImport` call instead of one call per file. |
| `stack-arr-missing-aired` | `<radarr\|sonarr>` | Monitored + no file + already aired/released, excluding upcoming items. Fills a real gap: Sonarr's own Wanted/Missing has no filter for this and gets buried under not-yet-aired episodes; Radarr has a native equivalent this mirrors. |
| `stack-arr-queue-errors` | none | Only queue items an app has already flagged as a problem itself, across radarr+sonarr in one call - quick triage instead of scanning each app's own full queue grid. |
| `stack-cutoff-unmet` | `<radarr\|sonarr> [limit]` (default 20) | Items with a file that's below the quality profile's cutoff - the app keeps upgrade-searching these. |
| `stack-import-lists` | `<radarr\|sonarr>` | Configured import lists (Trakt, other *arr instances, etc.) and each one's enabled/auto-add state. |
| `stack-arr-list-implementations` | `<radarr\|sonarr>` | Every import-list implementation type that app's build supports (Simkl, TMDb Company/Keyword/User, Plex, Custom, etc), whether configured or not - discovery aid before adding a new import list via the `stack-cli-discovery-import` skill's add-a-list commands. |
| `stack-customformat-diff` | `<radarr\|sonarr>` | Diffs current custom-format scores against the last time this ran, then updates its cache. Neither app logs format-score edits made through the API, so this is the only way to see what changed since the last check. |
| `stack-arr-recently-added` | `<radarr\|sonarr> [limit]` (default 10) | What was added *to management* most recently, with file/episode counts - spot-checks whether a fresh add has actually been searched yet. Distinct from `stack-plex-recently-added` (see the `stack-cli-plex-kometa` skill), which shows what's actually visible in Plex. |
| `stack-arr-logs` | `<radarr\|sonarr\|prowlarr> [lines]` (default 100) | Tails that app's container log directly. |
| `stack-command-queue-summary` | none | Backlog across radarr+sonarr+prowlarr at once - the aggregate view of what `stack-arr-backlog` shows one app at a time. |
| `stack-queue-status` | none | Every download queue (radarr, sonarr, nzbdav, plex activities) with a live-measured speed and ETA. Takes ~4s: it samples twice, since each app's own progress/timeleft reporting is unreliable in this stack. |
| `stack-backlog-status` | none | Every app's wanted/missing count with a throughput-projected ETA, based on recent import rate - a fundamentally different measurement from `stack-queue-status` (nothing here is mid-transfer, there's no size to drain). |

**Bazarr (subtitles):** Bazarr watches Radarr/Sonarr's libraries and fetches subtitles for anything missing them - it has no library of its own.

| Command | Args | What it does |
|---|---|---|
| `stack-bazarr-history` | `[limit]` (default 20) | Recent subtitle download history (movies and episodes), newest first - successes and failures both. |
| `stack-bazarr-provider-status` | none | Per-provider throttle/error state for every enabled subtitle source - catches a provider silently rate-limited or erroring on every request, invisible from a plain enabled/disabled list. |
| `stack-bazarr-search-missing` | none | Triggers Bazarr's missing-subtitle search now instead of waiting for its own scheduler (default every 6h). |
| `stack-bazarr-wanted` | none | Movies/episodes Bazarr still has no subtitle for, across both libraries. |
</command_reference>

## Common mistakes

<common_mistakes>
<general_anti_patterns>
- **Treating `stack-arr-import`'s index as stable across calls.** The candidate list can change between listing and importing (a queue item can clear itself). Always call `stack-arr-import-candidates` immediately before using an index with `stack-arr-import`, not from a stale list seen earlier in the conversation.
- **Reaching for `unstick` when the real problem is a wedged import.** `unstick` only acts on items the arr app's own `trackedDownloadStatus` already flagged warning/error - a download stuck in `importing` state with no error flag needs `stack-arr unstick-importing` instead, a distinct action with a distinct detection method (a live read-test against the file, not just a status check).
- **Assuming `stack-queue-status` returns instantly.** It deliberately takes ~4 seconds (two samples) to compute a real speed/ETA rather than trusting each app's own unreliable progress reporting - don't retry it thinking it hung.
- **Expecting `stack-customformat-diff` to show anything on its first run.** It has no baseline yet on a first call - it just writes the current snapshot to `~/.cache/stack-cli/customformat-<app>.json` and reports "nothing to diff against yet." Real diffs only appear from the second run onward.
</general_anti_patterns>
</common_mistakes>

## Resources

<resources>
**Local:**
- `~/.config/fish/functions/stack-arr*.fish`, `stack-cutoff-unmet.fish`, `stack-import-lists.fish`, `stack-customformat-diff.fish`, `stack-arr-recently-added.fish`, `stack-command-queue-summary.fish`, `stack-queue-status.fish`, `stack-backlog-status.fish`, `stack-bazarr-*.fish` - the actual fish source these commands wrap
- `control-panel/main.py` + `services/arr/router.py`, `services/bazarr/router.py`, `services/queue/router.py` in this repo - the real behavior behind every endpoint these commands call
</resources>

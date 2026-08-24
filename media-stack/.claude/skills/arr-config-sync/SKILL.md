---
name: arr-config-sync
description: Backup, restore, and diff configuration (root folders, quality profiles, indexers, download-client settings, notification connections) across the Arr-stack apps — Radarr, Sonarr, Prowlarr — via their REST APIs. Use when the user asks to back up an Arr app's config before a change, restore it after something breaks, compare config between two apps, or replicate a setting (e.g. a root folder or download client) across all Arr apps at once. Trigger phrases: "back up radarr config", "sync indexers to all arr apps", "what changed in sonarr's config", "restore radarr settings", "add this root folder to every arr app".
---

# Arr Config Sync

Talks to the Radarr/Sonarr/Prowlarr REST APIs (all share the same
Servarr API shape — `/api/v3` for the *arr apps, `/api/v1` for Prowlarr) to export,
diff, and replicate configuration as JSON. Covers root folders, download clients,
indexers, notification connections, and full-app backup/restore snapshots — for
quality-profile/custom-format work specifically, see the `trash-guides-applier` skill
(Recyclarr, this stack's former scheduled sync for that, was removed entirely in v11.2.0).

## Auth

Each app needs its API key, read from environment variables (never hardcode a key
in a command or file):

```
RADARR_URL / RADARR_API_KEY
SONARR_URL / SONARR_API_KEY
PROWLARR_URL / PROWLARR_API_KEY
```

`*_URL` defaults to `http://localhost:<default-port>` if unset (7878/8989/9696
respectively) — override to the docker-internal hostname (e.g. `http://radarr:7878`) when
running inside the compose network, or the LAN-facing URL when running from the host.
Never hardcode a real LAN IP as the default — that must come from the environment.

## Usage

```bash
# Snapshot one app's config to a timestamped JSON file
python3 sync.py backup radarr --out ./backups/

# Restore a specific section from a backup file (dry-run by default)
python3 sync.py restore radarr ./backups/radarr-2026-07-13T12:00:00.json --section rootfolder --apply

# Diff config between two apps of the same kind is not meaningful (different schemas),
# but you CAN diff the same app's config against an older backup:
python3 sync.py diff radarr ./backups/radarr-2026-01-01T00:00:00.json

# Replicate a root folder across every configured *arr app
python3 sync.py add-root-folder --path /media/movies --apps radarr
python3 sync.py add-root-folder --path /media/shows --apps sonarr

# List what apps are reachable/configured right now
python3 sync.py list-apps
```

## Sections covered

`rootfolder`, `downloadclient`, `indexer`, `notification`, `qualityprofile` (read-only
export — use `trash-guides-applier` to *write* quality profiles, since that's where the
TRaSH-Guides source of truth lives).

## Safety rules

- `restore` is dry-run unless `--apply` is passed: it prints a diff of what would change
  before touching anything.
- Never delete existing entries on restore/sync — only add or update by matching `id`/`name`.
  Removing a root folder or indexer a user is actively relying on is a destructive action
  outside this skill's scope; flag it instead of doing it silently.
- Back up before restoring: `restore` refuses to run if no backup file is given.

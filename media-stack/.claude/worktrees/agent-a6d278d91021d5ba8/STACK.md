# STACK.md

Detailed reference for this media-stack repo: architecture facts, known landmines,
incident history, gotchas, and workflow playbooks. Split out of CLAUDE.md 2026-07-25
to keep CLAUDE.md small — CLAUDE.md still carries the short-sentence/verification rules
Claude Code must follow; this file is pure reference material, read on demand per-section
rather than loaded whole every turn.

**CORRECTION, 2026-07-31 — read this before trusting any narrative below about the Usenet
client or the awesome-arr companion apps, both went through more churn than the prose below
was ever updated to reflect:**
- **Usenet client, current state**: `nzbdav`/`nzbdav_rclone` (added 2026-07-28), NOT
  AltMount and NOT BearMount — those are two generations stale. Full lineage: original
  NzbDAV → **AltMount** (2026-07-23) → AltMount's rebrand/fork **BearMount** (2026-07-24) →
  current **`nzbdav`/`nzbdav_rclone`** (2026-07-28, a different, unrelated codebase despite
  the name reuse — WebDAV-only, no native FUSE mount, hence the separate `nzbdav_rclone`
  sidecar). See CLAUDE.md's Commands section and this file's own later, dated entries for
  `nzbdav`-specific gotchas (SAB-API queue checks, the FUSE-mount cascade rules, the native
  `/api/delete-webdav-item`/`/api/update-config` endpoints found 2026-07-31 — see this file's
  entry near that date).
- **Tautulli and Kometa are back**: removed entirely in v11.9.0 (see README History), both
  **reinstalled 2026-07-30** as part of a 6-app "awesome-arr companions" addition (Tautulli,
  Wrapperr, Maintainerr, Prefetcharr, Lingarr) plus Kometa reinstalled separately
  in the same window — all running now, confirmed live via `docker compose ps`. Kometa's
  former Quickstart companion was **not** reinstalled and remains genuinely gone. Do not
  trust any older line below claiming Tautulli/Kometa's removal is "complete and final" —
  that claim is superseded.
- **Recyclarr and quality profiles**: Recyclarr was reinstalled 2026-07-23 (targeting
  TRaSH-Guides stock profiles), then **removed entirely a second time 2026-07-31**, in the
  same pass that consolidated both Radarr and Sonarr down to a single quality profile each
  named `Anything`. See README History `[11.12.0]` for the full detail, including the two
  non-obvious holdouts that blocked profile deletion (import lists' own default-profile
  setting, and — Radarr-only — all 903 Collections, no bulk editor exists for those).

When in doubt about current app inventory, `docker compose ps` / `docker-compose.yml`
itself is ground truth — this file's prose narrative has drifted stale multiple times
across this repo's history and will likely do so again.

## What this is

A Docker Compose media-acquisition-and-serving stack, one `docker-compose.yml`: indexes content
via Prowlarr, requests via Seerr, organizes via two `*arr`-family apps (Radarr/Sonarr — Lidarr
was removed entirely in v10.9.9 and Whisparr in v10.12.0, see below; Bindery, the ebook `*arr`,
was retired in v10.9.8 along with its reader Calibre-Web; no ebook app currently in the stack),
fetches via Usenet exclusively through **AltMount**, and serves via **Plex** (real, current
state as of 2026-07-23 — confirmed live via `docker compose ps`, `/library/sections`, and
`docker-compose.yml` itself, not assumed from older narrative in this file).

**CORRECTION, 2026-07-24: AltMount itself was fully removed and replaced by BearMount**
(`ghcr.io/whispersofj/bearmount`, container name `bearmount`, mount `/mnt/bearmount`, host
port 8082) — a full rebrand/fork of AltMount at `github.com/WhispersOfJ/bearmount`, same
codebase lineage. Every `altmount` reference below (container name, `/mnt/altmount`, routes,
`.env` vars, scripts) is historical narrative, not current state — read it for the reasoning,
substitute `bearmount` for the actual name. Same cutover pattern as NzbDAV→AltMount: every
pre-cutover symlink broke, and this time Radarr/Sonarr were also fully purged (0 movies/series
tracked) at the user's explicit request, keeping only Import Lists so libraries repopulate
from scratch. Don't assume the old movie/series counts or symlink targets are still valid.

Jellyfin briefly
replaced Plex on 2026-07-22 and was fully reverted back to Plex the same day after repeated
unresolved library-scan hangs; Jellyfin/Jellystat/jellystat-db were removed entirely in that
reversion (see the dedicated History entry below) — there is no Jellyfin anywhere in this stack.
NzbDAV (Usenet client) was removed entirely 2026-07-23 and replaced by AltMount, for the same
reason (an unfixed upstream connection-leak bug) — see the landmines section for the full
incident and PR references. **Tautulli, Kometa, and Kometa's Quickstart companion are fully
removed, corrected 2026-07-24** — `docker-compose.yml` has zero references to any of the
three (confirmed via `grep`), reversing a 2026-07-23 correction in this same file that claimed
they were "present-but-dormant" with live compose blocks/images; that "present-but-dormant"
claim was itself stale by the time it was checked again. Treat their removal (compose blocks,
`config/tautulli/`, `config/kometa/`, `config/quickstart/`) as complete and final.
**Torrent and debrid support (Decypharr, Zurg, rclone-alldebrid, Zilean, zilean-postgres,
Byparr) was removed entirely in v11.0.0, by explicit request** — every acquisition goes through
Usenet, no exceptions (see the landmines/History sections below for the full removal, including
a real consequence found mid-execution: those apps never downloaded real bytes, only symlinked
into a live FUSE mount streamed from the debrid provider, so removing them immediately broke
playback for the ~3.65% of the library that was debrid-sourced, not just future acquisitions).
Usenet had already been the preferred protocol since a v10.14.1 policy change (a deliberate
reversal of the stack's original debrid-first design) before this final removal. There is no
adult content library in this stack anymore: Plex's own Adult library was removed in v10.9.9,
and Whisparr (which managed the underlying files/root folder) plus Stash (which cataloged it)
were both removed in v10.12.0, along with the files themselves. There is no anime library in
this stack either as of v10.19.0 (also removed by explicit request, not a dead-app cleanup —
see the landmines section below), and no self-hosted DebridMediaManager as of v10.20.0 (same
reasoning, same section). **As of 2026-07-23, every root folder is enforced back to 100%
symlinks with zero real media files on local disk** — AltMount's `import.import_strategy` is
`SYMLINK` (not `NONE`) and both Radarr's and Sonarr's `copyUsingHardlinks` is `true`; see the
dedicated History entry below for why this had regressed and how it was fixed and verified live
(a real symlink into `/mnt/altmount` that actually streams, not just a config value).
`control-panel/` is the one custom-built component (a FastAPI dashboard, redesigned entirely
2026-07-23 — no boxes/tabs, a permanently pinned log console, see the dedicated entry below);
everything else is off-the-shelf images wired together in `docker-compose.yml`.

**This stack currently has zero backup coverage, deliberately, as of 2026-08-12** — restic was
removed entirely at the user's explicit request while a new backup solution is being decided.
This time the removal is total, not a stop/unlink: both the local (`~/backups/stack-restic-repo`,
453GB) and offsite (`~/Dropbox/stack-restic-repo-offsite`) repo data were deleted, along with
`scripts/backup-config.sh`, `scripts/backup-claude-dir.sh`, the `stack-backup`/`stack-claude-backup`
systemd units, every `stack-backup-*`/`stack-newapps-backup-check` fish function, and the
control-panel `_restic` helper and `/api/backup-*` routes. `scripts/arr-app-backup.py` (Radarr/
Sonarr's own native Backup command, not restic) is untouched and still runs. Do not assume any
restic-based recovery path exists — there is none until a replacement is built.

**`README.md` is the only documentation in this repo besides raw config** — it merges what used
to be README/TECHNICAL/CHANGELOG into one document, organized by subsystem, ~1,900 lines with a
linked table of contents. Read the relevant section there before making changes; this file only
covers what you need to get oriented and the things that aren't obvious from reading one file in
isolation.

**This stack has no public downstream mirror — see `AGENTS.md`.** `StackMaster` (and before it,
`Stackalicious`/`StackScripts`) were deleted outright from GitHub, most recently 2026-07-21,
for privatization. Every `stack-*` command lives only in this host's own fish functions plus
this repo's `control-panel/app.py` — nothing to mirror anywhere.

## Full service inventory (all 17, by subsystem)

**Stale, multi-generational — see the CORRECTION block near the top of this file first.**
This section still describes Jellyfin as the media server, `nzbdav` on the wrong port/mount
path, and the old TRaSH-tier quality profiles (superseded 2026-07-31 by a single `Anything`
profile per app) — predates the Jellyfin-to-Plex revert and everything after it. Kept as
relationship-map narrative for the services that *haven't* changed shape since, not as a
source of current facts; `docker-compose.yml` plus README's service table are ground truth
for current inventory. Not a duplicate of README's service table (image/port/profile) — this
is the *relationship* map: what each service actually talks to, so a question about any one
container can be answered without re-reading `docker-compose.yml` end to end. `core` = no
`profiles:` line, comes up on a bare `docker compose up -d`; `extras` = needs `--profile
extras`. **Also stale**: no `profiles:` split exists in `docker-compose.yml` at all anymore —
every service starts on a bare `docker compose up -d`.

**Indexing** — `prowlarr` (core, indexer manager, pushes indexers to Radarr/Sonarr via
`fullSync`; Usenet indexers only as of v11.0.0 — every torrent indexer, plus the `Zilean`
Torznab entry, was disabled then deleted, see the landmines/History sections).

**FUSE mount owners** — `nzbdav-rclone` (core, mounts NzbDAV's own WebDAV filesystem at
`/mnt/nzbdav`, `depends_on: condition: service_healthy` on `nzbdav` itself, not just compose
start-order — the only FUSE mount left in this stack as of v11.0.0).

**`*arr` apps** — `radarr` (core, port 7878, movies, `/data/movies`) ·
`sonarr` (core, port 8989, TV, `/data/shows`) — both single-quality-profile ("ANY") as of
v11.2.0 until 2026-07-23, when Recyclarr was reinstalled (see History) — both apps now also
carry real TRaSH-tier profiles (Radarr: HD Bluray + WEB / Remux + WEB 2160p / Low Quality;
Sonarr: WEB-1080p / WEB-2160p / Low Quality) alongside "Any", synced daily 6am by Recyclarr.
Existing movies/series were deliberately left on "Any", not reassigned to a tier.

**Usenet** — `nzbdav` (core, port 3001→3000, WebDAV-streamed Usenet, SABnzbd-API compatible,
**the only download client on both Radarr and Sonarr as of v11.0.0** — was priority-1 behind
Decypharr's priority-2 fallback until debrid was removed entirely, see the top-of-file
description) · `nzbdav-rclone` (see FUSE mount owners above — same container, listed once).

**Requests** — `seerr` (core, port 5055, Radarr/Sonarr only — no adult-content or music/ebook
data model, moot now that those app families are gone anyway).

**Media server** — `jellyfin` (core, `lscr.io/linuxserver/jellyfin:latest`, port 8096, bridge
networking on `stacknet` — replaced `plex` entirely 2026-07-22, see the Historical incidents
section below for the full migration. Two libraries, matching Plex's final two exactly: Movies
(`/data/movies`), Shows (`/data/shows`). Same VAAPI hardware-transcode device
(`/dev/dri/renderD128`) carried over from Plex's config. **Its compose block has no
`/mnt/nzbdav` mount** (unlike every other root-folder consumer — Radarr, Sonarr, Unpackerr,
Cleanuparr all bind it) — every root folder is 100% symlinks into that FUSE mount (see
Architecture facts below), so this looks like the exact same class of bug Stash's first deploy
hit: a library scan that completes with no error and finds nothing playable, because every
`readlink` resolves to a path that doesn't exist inside this container's own mount namespace.
Not yet confirmed live either way — flagged here as an unverified, high-suspicion gap, not a
confirmed bug, since verifying it means actually watching something and this pass was
documentation-only.)

**Monitoring** — `tautulli` removed entirely 2026-07-22, same session as the rest of the
Plex-to-Jellyfin migration (Plex-only, nothing left to monitor once Plex was gone; initially
left orphaned pointed at a dead media server, then fully removed on explicit follow-up
request — compose block, `config/tautulli/`, and its `control-panel/app.py` routes' container
listing entry all gone; the two `/api/tautulli/*` history/stats routes themselves were left as
documented dead code, same treatment as `/api/plex/*`, since they already 503 gracefully once
`config/tautulli/config.ini` doesn't exist) · `jellystat` + `jellystat-db` (extras, port 8087,
Jellyfin stats/history, the Tautulli-equivalent — `jellystat-db` is `postgres:18.1`, this
stack's first Postgres dependency since `zilean-postgres` was removed in v11.0.0, still with no
backup-coverage plan, a known gap, see Backup/DR section below). Both containers are up,
healthy, and fully configured — confirmed live via `jellystat-db`'s own `app_config` table
(real `JF_HOST`/`JF_API_KEY`, admin user `bear` matching Jellyfin's real user ID) and a
populated `jf_library_items` table (7,799 rows synced). `beszel`/`beszel-agent` (Glances'
v10.9.9 replacement) removed entirely in v11.2.0, by explicit request — no host/container
resource-monitoring hub currently in this stack.

**Subtitles** — `bazarr` (extras, port 6767, watches Radarr/Sonarr for missing subtitles;
reinstalled from scratch in v11.3.0 after being removed entirely in v10.2.0, no prior config
survived; wired to both apps post-boot via its own `/api/system/settings` form-encoded
endpoint — see README's dedicated section for the gotchas in that endpoint before touching it
again; provider list narrowed in v11.4.0 to 9 English-capable, non-anime-exclusive sources).

**Sports PVR** — none. `sportarr` was added 2026-07-23 and **removed entirely 2026-07-24**,
by explicit request, after its Plex metadata integration turned out to be structurally
broken (see History `[Sportarr removed]` below) and the user chose full removal over
further debugging.

**Dashboard** — `control-panel` (extras, port 8420, the one custom-built component —
`build:` from `./control-panel`, not a pulled image; talks to `docker.sock` plus every app's
own HTTP API; no auth, CSRF/Origin-Host validated only; see the dedicated gotchas section
below).

**Metadata/overlays** — none currently in this stack. `kometa` and its `quickstart` companion
(the official Kometa-Team config-building wizard) were **removed entirely 2026-07-22** when
Plex was replaced by Jellyfin, after confirming directly against `kometa-team/kometa`'s own
`config-schema.json` that Kometa has no `jellyfin`/`emby` top-level connection property, only
`plex` — several blog-post sources (e.g. jellywatch.app) claiming Kometa supports Jellyfin are
wrong/outdated as of this check; real Jellyfin support is an open, unimplemented feature
request (features.jellyfin.org/posts/2899). Initially just stopped (`docker compose stop
kometa quickstart`, config/compose untouched) in case that changed upstream soon, then fully
removed at the user's explicit follow-up request: both compose service blocks deleted,
`config/kometa/` and `config/quickstart/` deleted (`config/kometa/config.yml`'s real
credentials — Trakt client ID/secret, GitHub PAT, OMDb/MDBList keys — backed up to
`~/backups/removed-configs/kometa-config.yml.bak-2026-07-22` first, unlike Plex's config which
was pure app-internal state; OMDb/MDBList keys promoted to real `OMDB_KEY`/`MDBLIST_KEY` `.env`
secrets and wired into `control-panel/app.py`'s `/api/ratings/*` routes, which used to read
them live off Kometa's file), `control-panel/app.py`'s `/api/kometa/run` route and
`KometaRunRequest` model deleted outright (not left dead like the Plex routes — no
missing-env-var fallback existed for it to degrade into), `CONTAINER_LABELS` entries for both
containers removed. `labelarr` (TMDb-keywords-as-Plex-labels) removed entirely in v11.2.0, by
explicit request — no item-level Plex label automation currently in this stack, and no
collections/overlays automation of any kind now either, following Kometa's removal.

**Post-processing** — `unpackerr` (extras, no port, RAR extraction for Radarr/Sonarr's
downloads).

**Auto-updates** — `watchtower` (extras, no port, digest/channel-tag images only — Plex used to
be deliberately excluded from its train via a manually-bumped version tag; Jellyfin is not
excluded the same way — `lscr.io/linuxserver/jellyfin:latest` is a mutable channel tag, so
Watchtower auto-updates it like any other channel-tag image unless this is deliberately
changed, see Image pinning policy).

**Queue cleanup / missing-content hunting** — `cleanuparr` (extras, port 11011, strikes +
malware-block + stalled-download cleanup). **`neutarr` was removed entirely 2026-07-24**,
after its hunting flood caused a real cascading incident (see the landmines section) —
there is no automated missing-content/quality-upgrade hunting of any kind in this stack now.

## Commands

```bash
# Validate compose config (what CI runs) — needs a .env first, dummy values are fine
cp .env.example .env
docker compose config --quiet
docker compose --profile scheduled config --quiet

# Lint (what CI runs, no repo-local ruff config — defaults). Scope widened
# 2026-08-14: it was `control-panel/app.py scripts/*.py`, which left the live
# backend (main.py, core/, services/, models/) entirely unlinted after app.py
# was retired from the image CMD in the 2026-08-05 rewrite.
ruff check control-panel/ scripts/ tests/
shellcheck scripts/*.sh  # CI excludes config/, media/, usenet/

# Rebuild and pick up control-panel changes — app.py AND static/ (CSS/JS/HTML) are both
# baked into the image at build time via the Dockerfile's COPY, not bind-mounted, so a plain
# `restart` serves the old files untouched even after editing them on disk.
docker compose build control-panel
docker compose up -d control-panel

# control-panel reads .env at container-*create* time only — a plain restart won't
# pick up a .env change here, it needs force-recreate
docker compose up -d --force-recreate control-panel

# Bring up the stack. There is no `extras` profile any more (it was removed with the
# core/extras split); `up -d` starts all 26 daemon services. plexanisync is the one
# profiled service — a run-to-completion job, normally fired by systemd/plexanisync.timer
# rather than by hand.
docker compose up -d
docker compose --profile scheduled up -d plexanisync

# MANDATORY before recreating/restarting/stopping the download client for ANY reason
# (config change, mem_limit tweak, unrelated debugging - the reason does not matter, see
# CLAUDE.md's 2026-07-23 repeat-incident entry, which carried across both rebrands).
# The queue directory is NOT a persistent volume, so any recreate wipes queued NZBs and
# each resulting failure silently unmonitors + permanently blocklists the affected
# Radarr/Sonarr item. Confirm pending/processing is 0 first, or drain the queue before
# touching the container.
#
# The old `sqlite3 config/bearmount/bearmount.db "SELECT status, COUNT(*) FROM
# import_queue ..."` form documented here is dead — bearmount was replaced by
# nzbdav/nzbdav on 2026-07-28 and config/bearmount/ no longer exists. Check the queue
# through the API instead, which works regardless of the current schema:
stack-nzbdav-queue

# Unit tests (added 2026-07-22) — the control-panel backend's pure logic (helpers, CSRF
# middleware, bucketing/ETA math, and since the 2026-08-05 rewrite the services/ routers
# via FastAPI's TestClient) plus scripts/*.py's pure logic, all with docker.sock,
# httpx, and urllib network calls mocked out; no real stack/daemon needed. Now part of
# CI (validate.yml), alongside the compose/ruff/shellcheck checks below.
# This host's Python is externally-managed (PEP 668) - pip install below refuses with
# "externally-managed-environment" outside a venv: `python3 -m venv /tmp/venv &&
# /tmp/venv/bin/pip install -r control-panel/requirements.txt -r requirements-dev.txt &&
# /tmp/venv/bin/pytest`.
pip install -r control-panel/requirements.txt -r requirements-dev.txt
pytest
```

CI (`.github/workflows/validate.yml`) runs compose-config validation, ruff, shellcheck,
the `tests/` unit suite above, and a build-only Dockerfile check — no torrent/live-stack
verification. **The unit suite only covers pure logic reachable with everything mocked**
(docker.sock, each app's HTTP API, `urllib`/`httpx` calls) — it does not replace exercising
a change against the real running stack (curl an endpoint, check `docker logs`, load the
dashboard), which is still the only way to verify anything that actually talks to a live
container. That's the pattern this project's own README follows throughout its history
section, and there's no substitute for it for that class of change.

## Architecture facts that span multiple files

- **Root folders for every `*arr` app live on regular disk (`./media/<type>` → `/data/<type>`),
  never on `nzbdav-rclone`'s `/mnt/nzbdav` FUSE mount.** That mount is read-only in practice
  (symlink/hardlink/copy all fail there with `EIO`; used to be true of Zurg's `/mnt/zurg` mount
  too, before torrent/debrid was removed entirely in v11.0.0 — see the landmine below). This
  has regressed silently before — a library rescan can reset an item's root folder back to
  `/mnt/<mount>/...` in an app's own database, which is invisible to git since it's app state,
  not stack config. If an import mysteriously stalls, check the item's resolved root folder
  before assuming a container/mount problem.
- **A root folder is 100% symlinks, never real files — any new service that reads one needs the
  same `/mnt/nzbdav` mount every existing consumer has, not just the root folder itself.**
  Confirmed as a real bug, not a hypothetical: Stash's first deploy (before it was removed
  entirely) mounted only `./media/adult:/data`, and every symlink under it was dangling from
  inside that container's own mount namespace — a real library scan completed in seconds with
  no error and found 0 scenes, because every `readlink` resolved to a path
  (`/mnt/nzbdav/.ids/...`) that simply didn't exist in that container. Silent, not a crash —
  check this first if a new container reading an existing root folder reports an empty/tiny
  library despite the source clearly having content.
- **FUSE-mount-owning containers and their dependents restart independently, and that's a real
  failure class, not a hypothetical.** `nzbdav-rclone` (the only FUSE-mount-owning container
  left as of v11.0.0, since Zurg/Decypharr/rclone-alldebrid were removed entirely) owns
  `/mnt/nzbdav`; every other container that bind-mounts that path (Radarr, Sonarr, Plex,
  Unpackerr, Cleanuparr) keeps a stale reference after the owner restarts and needs its own
  restart to recover — this does not self-heal. Confirmed live again 2026-07-18 during the
  torrent/debrid removal itself: recreating `nzbdav-rclone` and all five dependents in the same
  batch left every dependent unable to start at all (`transport endpoint is not connected`)
  until `nzbdav-rclone` was restarted alone first and the stale host mount cleared with `sudo
  umount -l /mnt/nzbdav`. `control-panel/app.py`'s `/api/stack/restart-all` encodes the known
  ordering (`MOUNT_PREREQS` → `MOUNT_PROVIDERS` → everything else → `MOUNT_DEPENDENTS` last),
  but it's a hand-maintained set, not derived from `docker-compose.yml` — if you add a new
  service that owns or depends on a FUSE mount, that set needs a manual update or the ordering
  silently stops covering it. See README's "Whole-stack restart: mount-order aware" section.
  **Still literally `{"radarr", "sonarr", "plex", "unpackerr", "cleanuparr"}` as of the
  2026-07-22 Plex-to-Jellyfin migration** — `control-panel/app.py` is unreworked (see the
  Historical incidents entry below), so `restart-all` still tries to restart a container named
  `plex` that no longer exists in `docker-compose.yml` (a harmless no-op against the Docker SDK,
  not a crash, but dead weight) and does not include `jellyfin` at all — worse, Jellyfin's own
  compose block doesn't even bind `/mnt/nzbdav` right now (see the Media server entry above),
  so whether it needs to be in this set at all is unresolved until that's confirmed.
- **Control Panel (`control-panel/app.py`) is the only in-repo application code.** FastAPI, talks
  to `docker.sock` (via `docker` SDK) plus every app's own HTTP API (via `httpx`), no database, no
  auth beyond CSRF/Origin-Host validation on mutating requests (this stack is LAN-only by design —
  see README's Security section for why an earlier Traefik+Authelia+CrowdSec layer was built,
  verified working, and then reverted). `static/` is vanilla JS/CSS served straight off disk, no
  build step.
- **The `stack-*` CLI is not in this repo.** It's a set of fish functions tracked in
  `~/.dotfiles`, all calling Control Panel's HTTP API — treat `control-panel/app.py`'s routes as
  the actual interface contract; the CLI is a thin client over them.
- **Image pinning is deliberately inconsistent by policy, not oversight**: channel tags for hotio
  images, version tags where upstream cuts real releases, digest pins where the running `:latest`
  build is ahead of any tagged release, and (historically) a manually-bumped version tag for Plex
  specifically, kept off Watchtower's auto-update train. Plex is gone as of 2026-07-22 (replaced
  by Jellyfin, see the Historical incidents entry below); Jellyfin's `lscr.io/linuxserver/jellyfin:latest`
  is a mutable channel tag, not a version pin, so it does *not* carry forward Plex's old
  exception — Watchtower auto-updates it same as any other channel-tag image unless that's
  deliberately changed. Watchtower only auto-updates the channel-tag-pinned subset — check which
  category an image falls into before assuming a version bump is either safe or something
  Watchtower will ever pick up on its own.
- **`config/<app>/` holds real plaintext secrets** wherever an app stores its own config (e.g.
  `config/nzbdav/db.sqlite`'s `ConfigItems` table holds the Usenet provider's real
  username/password), is gitignored, and is not reproducible by `docker compose up` or
  re-pulling images — as of the 2026-08-12 restic removal there is no automated backup
  mechanism protecting this at all (see Backup/DR section below). `scripts/backup-claude-dir.sh`
  is also gone; do not assume any Dropbox tar of `~/Claude` still exists or is being refreshed.
- **Zurg's content-routing config (`config/zurg/config.yml`) had a real, repeated failure
  mode, worth remembering even though Zurg itself is gone as of v11.0.0**: a group whose *app*
  was removed didn't stop misrouting content, it just started misrouting into a path nothing
  served anymore, silently — happened three separate times (the `music`/`adult` groups
  outliving Lidarr/Whisparr's removal with bare keywords like `FLAC`/`Wicked`/`XXX`
  false-positive-matching 43+ real movies; the anime groups outliving the anime library
  removal by one release). **The generalizable lesson: when removing an app that owns a
  content-routing group or filter of any kind, removing the group itself has to be part of
  that same removal checklist** — nothing else in this stack ever caught it on its own (no
  library, no queue, no alert reads a dead path). See README's
  [The debrid pipeline: removed](README.md#the-debrid-pipeline-removed) section for the full
  incident writeup.
- **A service can be fully connected at the `docker-compose.yml` level and still not actually be
  wired into the *app* it's talking to.** Cleanuparr and NeutArr both auto-discover which
  `*arr` apps exist, but each still needs its own internal instance registration (Cleanuparr's
  own `arr_instances` DB table; NeutArr's own per-app JSON config) before it actually does
  anything for that app — found live as a real gap: Lidarr and Whisparr (both since removed) had
  network access to Cleanuparr and config-type placeholders, but no connected instance, so
  queue-cleaning/strikes silently weren't covering either app. When auditing "is X wired to Y,"
  check the receiving app's own config/API for a real instance entry, not just that the container
  can reach it. NeutArr regenerates a blank-credential placeholder file for any app type it knows
  about (`eros.json`, `whisparr.json`) on every restart even after that config is deleted — inert
  (no URL/key means it can never connect), not a sign the removal didn't take.
- **Every service should have `mem_limit`/`cpus` — verify with `docker stats`, not by grepping for
  the string `mem_limit:` near a service block.** The `x-common` anchor (`<<: *common`) does not
  set either; ten services silently had neither for an unknown stretch of this project's history,
  confirmed live via `docker stats` reporting the full host memory ceiling as several containers'
  limit instead of a real number. A new service needs its own explicit `mem_limit`/`cpus` lines
  regardless of whether it uses `<<: *common`.
- **Lidarr was removed entirely in v10.9.9** — `docker-compose.yml` service block gone,
  `config/lidarr` deleted, `control-panel/app.py`'s `ARR_APPS`/`QUEUE_ARR_APPS`/
  `CONTAINER_LABELS`/`LOG_LEVEL_APPS`/`ARR_LOG_CONTAINERS` all updated, `LIDARR_API_KEY` gone from
  `.env`/`.env.example`, Prowlarr's Lidarr application-sync entry deleted via its own API,
  NeutArr's Lidarr state/config files deleted. The stale Lidarr row this left in Cleanuparr's
  SQLite `arr_instances` table was cleaned up the same day — no REST endpoint exists for that
  table, so the container was stopped first (avoiding a live WAL-mode write), the row and its
  orphaned parent `arr_configs` row deleted directly, then restarted healthy.
- **Whisparr (and Stash, its cataloging app) were removed entirely in v10.12.0** — same recipe as
  Lidarr above, plus a few things Lidarr's removal didn't need to touch: `./media/adult` (Whisparr's
  root folder, 100% symlinks, no real media) deleted; the live Cleanuparr SQLite row deleted in
  the same pass this time, not left as a residual gap (six referencing tables confirmed zero
  orphaned rows before deleting); `/api/neutarr/hunt/eros` (an endpoint whose only purpose was
  triggering Whisparr's hunt cycle) removed outright, not just left orphaned; Decypharr's
  `categories` list in `config/decypharr/config.json` (gitignored, live config) had `"whisparr"`
  dropped. The `*arr` app family in this stack is now Radarr/Sonarr only.
- **Anime support was removed entirely in v10.19.0, by explicit request** — unlike Lidarr/
  Whisparr this wasn't a dead-app cleanup, it was a live, populated content category (122
  Radarr movies, 159 Sonarr series) removed on purpose. Touched: both library entries
  (`deleteFiles=true`, including 15.7GB of real, non-debrid-backed local files under
  `anime-movies` — this stack's "root folders are 100% symlinks" assumption above does not hold
  universally, that was the exception), both Plex libraries, both root folders, the
  `[Anime] Remux-1080p` quality profile and its 33 dedicated custom formats on both apps,
  Zurg's `anime-shows`/`anime-movies` content-routing groups, the `rclone-alldebrid-anime`
  service and `/mnt/all-anime` mount, Kometa's `Anime Movies`/`Anime Shows` library blocks and
  MyAnimeList credentials, `scripts/sort-anime-movies.py` and its systemd units,
  `control-panel/app.py`'s anime references, `PLAN.md` (a never-implemented dual-instance
  proposal), and 8 live Prowlarr indexers that are anime-dedicated by content even though their
  names don't say so (`Nyaa.si`, `SubsPlease`, `Mikan`, `dmhy`, etc. — disabled, not deleted).
  A live Sonarr Trakt import list literally named "Anime" (`enableAutomaticAdd: true`, 12h
  refresh) was found only by checking `/api/v3/importlist` directly — it doesn't live in any
  tracked file, and left in place would have silently re-added anime series on its next
  refresh. See README's History `[10.19.0]` for the full incident, including two more
  supply-chain-style gaps a naive file/config grep wouldn't have caught.
- **DebridMediaManager (self-hosted) was removed entirely in v10.20.0, by explicit request.**
  Four services (`dmm-mysql` - 4GB real MySQL data, permanently deleted with no dump kept;
  `dmm-redis`; `dmm-migrate`; `debridmediamanager`), `scripts/import-imdb-data.py` and its
  daily systemd timer (existed solely to feed `dmm-mysql`'s search index), Control Panel's
  `/api/dmm/status` route plus `pymysql`/`cryptography` from `requirements.txt`, and five
  env vars (`MDBLIST_KEY`/`OMDB_KEY`/`TRAKT_CLIENT_ID`/`TRAKT_CLIENT_SECRET`/`GH_PAT`) that
  turned out to be DMM-exclusive despite this file's own prior wording implying they were
  shared with Kometa — Kometa's `config.yml` carries independent hardcoded copies, not env-var
  substitution, so those five had zero other consumers once DMM's compose block was gone.
  **Deliberately kept, not an oversight**: Zilean's own `Zilean__Dmm__EnableScraping` (scrapes
  DMM's public hashlist website, unrelated to the self-hosted app) and Control Panel's
  `/api/zilean/search` (calls Zilean's own `/dmm/search` endpoint) — same name, different
  feature, confirmed by reading source before touching either. A removal-script bug was caught
  mid-execution: the first attempt at renumbering README's service table matched `zurg`'s row
  too, because its sponsor image (`ghcr.io/debridmediamanager/zurg@...`) contains the literal
  substring "debridmediamanager" — same false-positive class as the anime purge's "URANiME"
  release group, caught by a row-count sanity check, not assumed clean.
- **Adminer removed in v10.9.9, no replacement (for now).** Briefly swapped for CloudBeaver
  (`dbeaver/cloudbeaver:24.3.0`) same version, but that was reverted immediately at the user's
  request — not a fan of the tool, no substitute picked yet. There is currently no web DB GUI
  in this stack; moot now anyway, since `zilean-postgres` (its one-time subject) was itself
  removed along with the rest of the debrid layer in v11.0.0 — no Postgres instance runs in
  this stack anymore.
- **Glances and Dozzle removed entirely in v10.9.9, no data preserved.** Neither had a config
  volume, so there was nothing on disk to clean up. Glances powered Control Panel's Overview
  "Host CPU/memory/disk/uptime" tiles via `/api/system/stats` — that endpoint and those tiles
  are gone too, not just left degraded (Control Panel itself was never re-wired to Beszel below).
  A Prometheus + Grafana monitoring stack was also researched and briefly proposed the same
  session, then cancelled before anything was built or added to `docker-compose.yml`.
  **Glances' replacement, `beszel`/`beszel-agent`, was itself removed entirely in v11.2.0** —
  see [History](README.md#history). This stack currently has no host/container
  resource-monitoring hub of any kind.

## Known current landmines (not historical — still true as of last audit)

- **CHANGED 2026-07-25 — BearMount switched from `mount_type: rclone` to `mount_type: fuse`**
  (native, built-in FUSE mount - no external rclone subprocess, no RC API layer). Motivated by
  this file's own documented rclone-subprocess-lifecycle bugs (the subprocess-reap race, "Failed
  to kill rclone process", "Force unmount failed" - all specifically about managing rclone as a
  *separate child process*, not the mount itself). `config/bearmount/config.yaml`: top-level
  `mount_type: fuse` (was `rclone`), `rclone.mount_enabled: false` (explicit, to avoid any
  ambiguity about which subsystem owns the mount). The existing `fuse:` config section was
  already present with sensible values matching AltMount's own documented recommended FUSE
  settings almost exactly (`attr_timeout_seconds: 30`, `max_cache_size_mb: 128`,
  `max_read_ahead_mb: 128`) - no further tuning needed there. Verified live: real content
  readable through `/mnt/bearmount` immediately after the switch, zero new mount-table leaks,
  real Plex playback confirmed.
  **New Control Panel routes added first, deliberately, before the switch**: `GET /api/bearmount/
  fuse/status`, `POST /api/bearmount/fuse/start`, `POST /api/bearmount/fuse/stop`, `GET
  /api/bearmount/health/stats`, `GET /api/bearmount/health/corrupted` - proxying BearMount's own
  JWT-authenticated REST API (separate entirely from the SABnzbd-compatible API `bearmount_api()`
  already used for queue/history, which takes `BEARMOUNT_API_KEY` as a query param instead).
  Auth: `POST /api/auth/login` with the fixed username `admin` + `BEARMOUNT_ADMIN_PASSWORD` (this
  already existed in `.env`), then the returned JWT must be sent as an **`X-JWT` header** on
  every subsequent call - `Authorization: Bearer <token>` was tried first and rejected (401),
  confirmed live. The `JWT` cookie itself is scoped to `domain=<HOST_IP>` (`COOKIE_DOMAIN` in
  compose), so it will never be sent back on a container-to-container call (`http://bearmount:
  8080`, a different domain) - this is the same cookie-domain gotcha this file already documents
  for AltMount's old `COOKIE_DOMAIN` setting, now confirmed to also apply to BearMount's own
  auth. `control-panel/app.py`'s `_bearmount_jwt()` caches the token in memory (24h lifetime
  observed) and re-logs in on expiry or a live 401, matching the existing pattern other
  app.py auth helpers use. `BEARMOUNT_ADMIN_PASSWORD` needed adding to `docker-compose.yml`'s
  `control-panel` environment block too (the same "needs adding in two places" gotcha already
  documented elsewhere in this file for poster-sync keys).
  **A real, confirmed incident happened validating this, worth remembering**:
  `POST /api/fuse/start`/`stop` operate directly on the raw FUSE layer **independent of the
  `mount_type` config value** - calling `start` while `mount_type` was still `rclone` (i.e.
  testing the routes *before* the switch, as originally planned) mounted a second, competing
  FUSE filesystem on top of the already-live rclone mount at the identical path. The subsequent
  `stop` call unmounted *both* layers together, leaving BearMount's real serving mount empty
  (`/mnt/bearmount/movies: No such file or directory`, not the usual "transport endpoint not
  connected" - a plain empty mountpoint this time) and hung Plex in the process. **These two
  endpoints are only safe to exercise once `mount_type` is genuinely `fuse`** - there is no way
  to validate them safely beforehand; the correct sequencing is build-the-routes, then switch
  the config, then exercise the routes for real as the first live test, not before. Recovered
  via `docker compose restart bearmount` (plain restart re-establishes the configured mount
  cleanly) rather than a full recreate, since the container itself never crashed.
  **A second, separate hang was found the same session, immediately after switching**: once
  genuinely in `fuse` mode, calling `/api/fuse/stop` for a real (now-safe) test succeeded and
  cleanly unmounted, but the *following* `/api/fuse/start` and even a plain `/api/fuse/status`
  call both hung indefinitely (30s+, no response) even though BearMount's base HTTP server
  stayed fully responsive (`GET /` and the Docker healthcheck both fine throughout) - a lock or
  goroutine specific to the FUSE-management code path, not a whole-process hang. `docker exec`
  worked the whole time (ruling out a genuine D-state/kernel-level hang). Cleared the same way:
  `docker compose restart bearmount` - no host-level mount corruption this time (`stat
  /mnt/bearmount` succeeded cleanly, unlike the rshared-abort incidents elsewhere in this file).
  **Every BearMount restart/mount-cycle still requires restarting the 5 `MOUNT_DEPENDENTS`
  afterward** - confirmed this still applies identically under `mount_type: fuse` (Plex held a
  stale `Transport endpoint is not connected` reference after each of the two restarts above,
  cleared only once `plex radarr sonarr unpackerr cleanuparr` were themselves restarted) - this
  class of bug is about the *mount instance* changing on any owner restart, not about which
  mount implementation owns it.
- **CHANGED 2026-07-25 — Plex's real-time filesystem-triggered library updates
  (`FSEventLibraryUpdatesEnabled`) disabled; replaced with `ScheduledLibraryUpdateInterval: 21600`
  (every 6h), deliberately, to fix the actual root cause of the repeated busy-database/hang
  incidents documented in the entries below.** Investigation found neither Radarr/Sonarr nor
  BearMount have any direct Plex notification wired up at all (Radarr's/Sonarr's only
  configured notification is a webhook *to BearMount*, `onDownload`; `config/bearmount/
  config.yaml` has zero Plex references) - the real trigger for every real-time library update
  was Plex's own inotify-based filesystem watcher reacting to every single new symlink the
  instant Radarr/Sonarr created it. During the sustained ~30-40 imports/minute burst this
  session (from clearing 1,774 import list exclusions), that meant a real Plex library-update +
  SQLite write roughly every 1-2 seconds, continuously - the actual mechanism behind the
  repeated `ViewStateSync`/`Push`-triggered "Waited over 10 seconds for a busy database" errors
  and the hangs that followed one of them. **Fixed by disabling per-file real-time updates
  entirely and relying only on the existing scheduled scan** (`ScheduledLibraryUpdatesEnabled`
  was already on, interval bumped from the 3600s/hourly default to 21600s/6h) - this converts
  continuous per-file write pressure into one batched scan every 6 hours. Real tradeoff, chosen
  deliberately: new content takes up to 6h to appear in Plex automatically now, instead of
  seconds. A manual `/api/plex/scan` (or `stack-plex-scan`) still triggers an immediate scan on
  demand at any time - use that after a real import batch if you don't want to wait for the
  scheduled window. **If this stack's import rate ever drops back to normal (steady trickle,
  not a mass backlog), consider re-enabling `FSEventLibraryUpdatesEnabled` and/or shortening
  the interval back toward 900-3600s** - this 6h value was chosen for an extreme, temporary
  load spike, not as a permanent architecture decision. Check via `GET /:/prefs` (`X-Plex-Token`
  required) for the live `FSEventLibraryUpdatesEnabled`/`ScheduledLibraryUpdateInterval` values
  before assuming either is still set this way.
- **A live incident hit mid-way through applying the above fix, worth noting as its own data
  point**: the `PUT /:/prefs` call itself timed out (Plex was already deep in SQLite
  contention when the request landed), and by the time recovery started, Plex was found
  genuinely D-state hung (same signature as every other entry in this section - unkillable via
  `docker kill`, `docker exec` failing with the nsexec/ns-ipc error). Recovered via the same
  established Tier 3 procedure (drain queue check, FUSE abort, host mountpoint `transport
  endpoint is not connected` cleared with `sudo umount -l /mnt/bearmount`, BearMount recreated
  and content-verified, 5 dependents restarted) - by now a well-rehearsed, low-drama recovery
  each time it recurs, confirming last session's `stop_grace_period` fixes keep the *cleanup*
  fast and low-blast-radius even though they don't prevent this specific hang trigger (a
  genuinely wedged FUSE syscall, not a shutdown-timing issue) from occurring in the first place.
  Only 6 blocklist casualties out of 959 queued items, cleaned up the same way as every prior
  occurrence.
- **FIXED 2026-07-25 — Plex itself had the exact same missing-`stop_grace_period` bug already
  fixed for BearMount below, and it bit hard: a Control Panel Tier 1 auto-restart (the
  *automated recovery action*) produced a genuine unkillable D-state hang instead of fixing
  anything.** Sequence, confirmed from Plex's own log: a `ViewStateSync` request (Plex's
  watch-progress cloud sync, unrelated to the library/FUSE mount) hit the same "Waited over 10
  seconds for a busy database" SQLite contention already documented below, logged `[ViewStateSync]
  Encountered exception: std::exception` (just its generic handler catching that timeout - not a
  new bug in its own right), and 9 seconds later the health monitor correctly detected
  `busy_db > 0` and fired its Tier 1 restart. Plex received a clean SIGTERM and began an orderly
  shutdown sequence (logged in full) - but the container's `StartedAt` never advanced and it was
  left genuinely unkillable (`docker kill` failed with `"tried to kill container, but did not
  receive an exit event"`), requiring the full Tier 3 FUSE-abort recovery to clear - same
  procedure as a real hang, including the same "abort disconnects the host mountpoint, blocking
  BearMount's own recreate until `sudo umount -l /mnt/bearmount` clears it" complication
  documented below. **Plex had no `stop_grace_period` set at all** (unlike BearMount, fixed
  earlier the same day) - under real load (heavy concurrent import/analysis), Plex's own shutdown
  needs more than Docker's 10s default to complete, same root cause as BearMount's. Fixed with
  `stop_grace_period: 90s` on Plex's compose block, matching BearMount's value. **Verified live
  under the exact same real load that triggered the failure**: a fresh Tier 1 restart completed
  cleanly and Plex was healthy again within ~15s, no hang, no Tier 3 needed. If a Control Panel
  auto-restart of *any* mount-adjacent container ever produces a hang instead of fixing one again,
  check `stop_grace_period` on that specific service first - this is now a known, recurring
  pattern, not a one-off.
- **ROOT CAUSE FOUND AND FIXED 2026-07-25 — this is very likely *the* answer to "why does this
  stack need restarting multiple times an hour."** Full research pass across BearMount's own
  logs, the host mount table, and Docker's shutdown behavior found two compounding structural
  bugs, not just the downstream FUSE-hang symptoms this file already documented extensively:
  1. **BearMount's own graceful shutdown legitimately takes ~40s, but nothing told Docker to
     wait that long.** `config/bearmount/bearmount.log` shows 21 SIGTERM-triggered shutdowns in
     the ~22 hours before this fix, every one hitting the identical pattern: the actual FUSE
     unmount succeeds almost instantly (`"All mounts unmounted successfully"` logs within the
     same millisecond as the shutdown starting), but two harmless-looking internal bugs
     downstream of that eat the rest of the time anyway - a subprocess-reap race that wastes a
     hardcoded 10s waiting to confirm rclone exited (it already had; the wait was pointless) and
     then fails to kill it ("os: process already finished"), followed by the HTTP server's own
     `Shutdown()` call hitting a **hardcoded 30s** internal context deadline
     (`"Error shutting down server","error":"context deadline exceeded"`, reproduced at exactly
     30.000s after "Shutting down server..." every single time it was checked). Total: ~40-43s
     measured live. **`docker-compose.yml` had no `stop_grace_period` set on bearmount at all**,
     meaning Docker's 10s default SIGKILL almost certainly fired mid-sequence on every one of
     those 21 restarts - after the mount was already safely torn down, but before the container
     process itself could exit cleanly. A container SIGKILLed mid-shutdown is exactly the kind
     of abnormal termination this file's own (partial, see below) mount-leak mitigation blamed
     for the downstream hangs. In effect: **restarting BearMount to recover from a hang was
     itself, almost every time, producing another unclean termination** - the "fix" was feeding
     the disease. **Fixed**: `stop_grace_period: 90s` added to bearmount's compose block, well
     above the measured ~43s worst case.
  2. **A real, actively-growing host-level mount-table leak, not just old residue.** A prior
     same-day fix attempt (see the entry directly below this one) added `:rprivate` to
     bearmount's nested `bearmount-import` bind mount, believing it would stop that mount from
     leaking into the host's shared `/mnt` peer group on recreate. Confirmed live this pass that
     it doesn't: `:rprivate` only controls whether *that* mount relays *further* propagation
     events going forward - it can't retroactively stop the mount-creation *event itself* from
     being observed by the parent's (the host's) peer group, which happens the instant the
     nested mount is created, regardless of what flag gets applied to it afterward. **A single
     controlled `docker compose up -d --force-recreate bearmount` (with BearMount's own
     `import_queue` confirmed empty first, per this file's hard rule) doubled the host's
     `/mnt/bearmount-import` mount-table entries from 127 to 255 in one recreate** - direct,
     reproducible proof the leak was still live, not fixed. This is very likely also what the
     original incident's "16,384 stacked entries -> misleading 'no space left on device'"
     resolved into being a *recurring*, not one-time, failure mode, given how often BearMount
     was being restarted (see bug 1). **Fixed**: replaced the broad `/mnt:/mnt:rshared` bind
     (the whole host `/mnt` tree, with `bearmount-import` nested inside it) with a narrow
     `/mnt/bearmount:/mnt/bearmount:rshared` bind - the *only* path that actually needs shared
     propagation, since that's where BearMount's own rclone FUSE mount gets created at runtime
     and other containers' `:rslave` binds on that same path depend on seeing it. `bearmount-
     import` now gets a plain, non-nested, default-propagation bind, the same pattern radarr/
     sonarr already used correctly for this exact directory (confirmed live: their mounts of it
     never leaked at all). **Verified live, not just configured**: a `docker compose up -d
     --force-recreate bearmount` with the fixed config added *zero* new host mount entries
     (511 before, 511 after); a second, independent restart the same session also added zero.
     The ~500 already-accumulated leaked entries (they'd grown further during testing before
     the fix landed) were cleaned up with `sudo umount -A /mnt/bearmount-import` - safe because
     that host path is never referenced as a bind *source* anywhere in `docker-compose.yml`
     (only `./media/bearmount-import` is; the host-side `/mnt/bearmount-import` mounts were pure
     propagation-leak byproducts with no legitimate consumer), and confirmed independently that
     `/mnt/bearmount` itself - the actual Plex-playback-critical mount - had exactly one clean
     entry throughout, never affected by any of this. Host mount table went from 700+ back to a
     baseline 61 after cleanup.
  3. **A third, smaller regression found in the same pass**: `config/bearmount/config.yaml`'s
     `import.max_processor_workers` had drifted back to `2` (last modified 2026-07-24, a full
     day after the entry elsewhere in this file that documents pinning it to `1` following a
     real OOM near-miss with two large multi-part archives analyzed concurrently). Reverted to
     `1`, matching the still-valid original reasoning - `mem_limit` is `6g` now (raised at the
     time of that incident), but nothing re-validated 2-workers-under-load against that limit,
     so this was silent, un-reasoned drift back into a previously-identified risk, not a
     deliberate re-tuning.
  **If BearMount instability or frequent restarts ever recur, check `stop_grace_period` is still
  set and `docker-compose.yml`'s bearmount volumes still use the narrow `/mnt/bearmount` bind
  before re-deriving this from scratch** - both are easy for a future edit to silently
  reintroduce (e.g. a well-meaning "let's just bind mount all of /mnt for simplicity" edit, or a
  Watchtower/image update resetting `config.yaml`).
- **FIXED 2026-07-25 — `_restart_bearmount_cascade()` (backing both Tier 2 restart-cascade and
  Tier 3 unstick) had never actually worked in production, confirmed live.** It shelled out to
  `subprocess.run(["docker", "compose", "up", "-d", "--force-recreate", "bearmount"], cwd=repo_root)`
  where `repo_root` was computed from `__file__` — inside the container that resolves to `/`,
  not a real compose project directory, and the `docker` CLI binary isn't installed in the
  control-panel image at all (only the Python SDK, via the mounted `docker.sock`). Every real
  Tier 2/3 call therefore crashed with a bare `FileNotFoundError` after already doing its
  destructive part (Tier 3's FUSE abort killed Plex's container outright, un-killable by a plain
  `docker kill` too — a genuine D-state hang) but before ever recreating BearMount or restarting
  the 5 dependents, leaving Plex dead with no automatic recovery. Caught live when the new Plex
  health monitor (see below) triggered exactly this path. **Fixed** by replacing the subprocess
  call with `_recreate_container_via_sdk()` — stops, removes, and recreates the named container
  from its own inspected `Config`/`HostConfig`/`NetworkSettings` via `docker_client.api.*`,
  needing only the docker.sock already mounted, no CLI binary or repo bind-mount. Verified live:
  a real `/api/plex/restart-cascade` call recreated BearMount and all 5 dependents cleanly,
  `scan-health` response time dropped from ~15-30s (mid-hang) to <100ms, and a real byte read
  through the symlinked mount succeeded from inside Plex's container afterward. If this route
  breaks again, check `docker logs control-panel` for the underlying SDK error, not just the
  route's own generic message — this class of bug hid silently for as long as the feature has
  existed, since nothing exercised it end-to-end in the actual container until this incident.
- **Plex health monitor**: `scripts/plex-health-monitor.py`, run continuously by
  `systemd/stack-plex-health-monitor.service` (a long-running daemon, not a timer — added
  2026-07-25 since `/api/plex/scan-health` is stateless per call and nothing previously alerted
  or acted if nobody had the dashboard open). Polls every 15s, tracks library-scan progress
  across polls itself to detect real lag (alerts past 30s stuck, auto-restarts past 90s stuck),
  and classifies failures into the same three classes this file's landmines already document
  separately: a genuine FUSE/D-state hang (`dstate_threads`/`mount_ok`) → alerts and
  auto-triggers Tier 2 (`restart-cascade`); SQLite lock contention (`recent_busy_db_errors`) →
  alerts and auto-triggers Tier 1 (plain container restart, matching the documented "doesn't
  need the mount-cascade risk" guidance); plain scan-progress lag → alerts, then Tier 1 if it
  doesn't clear. **Tier 3 (unstick) is deliberately never auto-triggered** — its FUSE abort has
  documented history of tearing down BearMount's entire mount via `rshared` propagation when
  done carelessly; that stays a human call from the dashboard. Every auto-restart is edge-
  triggered and cooldown-gated (10 min) so a still-unhealthy container isn't restarted every
  poll. Alerts/recoveries post to Discord via the same `DISCORD_WEBHOOK_URL` every other script
  uses. **Needs an explicit `User-Agent` header on every outbound request** — Discord's
  Cloudflare-fronted webhook endpoint 403s the bare default `Python-urllib/3.x` User-Agent,
  confirmed live; same gotcha this repo's other `urllib`-based scripts already work around (see
  `plex-webhook-listener.py`/`arr-app-backup.py`/`scrape_letterboxd.py`), just not documented as
  its own landmine until this script hit it fresh. Also needs generous timeouts on the
  scan-health poll itself (30s, not the 15s first tried) — a genuinely hung Plex can make that
  one endpoint legitimately take up to ~15-20s to respond (it chains several `_bounded_exec`
  calls), and `urlopen` can raise a bare `TimeoutError` (not wrapped in `URLError`) on a read
  timeout, which needs catching as `OSError` or it crashes the daemon instead of just skipping
  a poll.
- **`echo 1 > /sys/fs/fuse/connections/<id>/abort` is NOT a safe, isolated way to clear one
  stuck FUSE request — confirmed live 2026-07-25 to tear down BearMount's entire mount, not
  just the one connection.** BearMount's `/mnt:/mnt:rshared` volume mount uses *symmetric*
  shared propagation (not a one-way slave relationship) between the host and BearMount's own
  container. Aborting a stuck connection this session left `/mnt/bearmount` a dead mountpoint
  everywhere — including inside BearMount's own container, not just the 5 downstream
  dependents — and a subsequent `sudo umount -l /mnt/bearmount` on the host (intended only to
  clear an already-dead reference) had the same symmetric-propagation effect. **A `ls`/`stat`
  against an empty-but-technically-mounted directory still exits 0 with no error** — this
  looks identical to "healthy" unless the actual content is checked, which is what let this
  go unnoticed through a full 5-container restart cascade that "succeeded" by every check
  that only tested exit codes. Real consequence: Plex's own library-verify scan ran against
  the now-empty mount right after its restart, found every symlink unavailable, and
  `autoEmptyTrash` silently deleted 600+ library items across both sections within about a
  second (confirmed via `Plex Media Server.log`'s `[LibraryTimeline] Scanner activity`
  lines — `0 added, N deleted`, N climbing fast). Real media files on disk were untouched
  (192 real movie folders confirmed intact) — this was metadata/library-record loss, not data
  loss, recovered via a fresh `/library/sections/{id}/refresh` since the underlying
  symlinks/files were fine once the mount was genuinely restored. **Recovery that actually
  worked**: restart BearMount itself (not just the 5 dependents) to force a fresh internal
  remount, verify real content is present (not just an empty dir) via something like
  `docker exec bearmount ls /mnt/bearmount/movies`, *then* restart the 5 dependents, then
  trigger a fresh Plex library refresh. `control-panel/app.py`'s `_restart_bearmount_cascade()`
  (used by both `/api/plex/restart-cascade` and `/api/plex/unstick`) now enforces this
  content-check step itself and refuses to restart the 5 dependents if BearMount's own mount
  comes back empty — don't bypass that check by restarting containers by hand outside those
  routes without doing the same verification manually first.
- **A per-container bind-mount view of BearMount's FUSE mount can go stale
  (`Transport endpoint is not connected`) independently of BearMount's own mount and
  independently of Docker's healthcheck** — confirmed live 2026-07-25. After a
  `restart-cascade`, BearMount's own mount and the host's view of `/mnt/bearmount` were
  both fine (`ls` succeeded, real content present), and Plex's container reported
  `healthy`, but Plex's *own* bind-mounted view of the same path still returned
  `Transport endpoint is not connected` — a restart-ordering race where Plex's mount
  namespace picked up the old FUSE connection before it was replaced. `_mount_test()` /
  `/api/plex/scan-health` correctly caught this (`mount_ok: false`, state
  `hung_confirmed`) since it execs `ls /mnt/bearmount` *inside the plex container*, not
  the host or BearMount — checking those two alone is not sufficient, always check from
  inside the actual dependent container that's suspected stuck. **Real consequence, same
  as the `abort`/`rshared` incident above but via a different trigger**: while the mount
  was stale, Plex's library-verify scan ran, found symlinks unavailable, and
  `autoEmptyTrash` (still `true`, no prior mitigation had disabled it) silently dropped
  Movies from ~549 items down to single digits before this was caught. **Fix**: restarting
  Plex alone (not BearMount — its queue was actively draining, healthy, not the broken
  part) refreshed its bind-mount view; confirmed real content from inside Plex's own
  container (`docker exec plex ls /mnt/bearmount/movies`) before letting it rescan, then
  it repopulated correctly (`N added, 0 deleted` climbing, no deletions logged this time).
  **Disabled `autoEmptyTrash` via `PUT /:/prefs?autoEmptyTrash=0` afterward** — this is now
  the second confirmed incident of this exact deletion trigger (see the `abort`/`rshared`
  entry above, and the 2026-07-13 Radarr/Sonarr-side occurrence further below); leaving it
  on means every future mount blip is a library-wipe risk, not just a display glitch.
- **`docker exec`/`container.exec_run` against a partially-wedged container does NOT
  reliably fail fast** — an earlier note in this file claimed it does (based on a healthcheck
  exec erroring in ~2s during a full hang); a live, earlier-stage FUSE hang 2026-07-25 (waiting
  count building on one connection, not yet a full hang) instead made `docker exec plex ps
  aux` hang past an 8s CLI timeout, which is exactly what made `/api/plex/scan-health` itself
  unresponsive to callers for a stretch. `control-panel/app.py`'s `_bounded_exec()` helper
  now wraps every `exec_run` call used by the Plex Health feature in a worker-thread timeout
  so a wedged exec can no longer hang the request thread — any *new* code that calls
  `exec_run` directly needs the same wrapper, don't assume a wedged container's exec calls
  are safe to leave unbounded.
- **Control Panel's compose service now carries `pid: host`, `cap_add: SYS_ADMIN`,
  `security_opt: apparmor:unconfined`, plus `/proc:/host-proc:ro` and
  `/sys/fs/fuse:/host-sys-fuse` (read-write)** — added 2026-07-25 for the Plex Health
  feature's Tier 3 "Force Unstick" mitigation (`/api/plex/unstick`). This is a real,
  meaningful increase in blast radius for an unauthenticated LAN-only service: an
  unauthenticated POST can now enumerate every host process under `/host-proc` and write to
  host `/sys/fs/fuse/connections/*/abort`. Mitigated the same way as the existing
  docker.sock access — Origin/Host validation, not a login gate — see the Security section's
  existing reasoning for why that tradeoff was accepted here too.
- **Plex Health feature (`GET /api/plex/scan-health`, `POST /api/plex/restart-cascade`,
  `POST /api/plex/unstick`) turns this session's own repeated by-hand FUSE/D-state and
  SQLite-lock-contention diagnosis into a real, always-visible Control Panel panel** — status
  tiles, sparkline history, a live Plex-log tail, and the three-tier mitigation buttons
  (Tier 1: existing plain container restart; Tier 2: `restart-cascade`, force-recreates
  BearMount + restarts the 5 `MOUNT_DEPENDENTS`; Tier 3: `unstick`, aborts wedged FUSE
  connections first). Both Tier 2 and Tier 3 are gated on BearMount's own `import_queue`
  being empty (same hard rule as every other BearMount recreate in this file) unless
  `?force=true` is passed. `stack-plex-restart-cascade`/`stack-plex-unstick` fish functions
  and matching `commands.json` palette entries exist for CLI/palette parity. See the two
  landmines above for real bugs this feature's first live use surfaced the same day it
  shipped — both are now fixed in the route logic itself, not just noted here.
- **Cleanuparr has its own independent missing-content hunter ("Seeker"), separate from
  NeutArr and from any Sonarr/Radarr import list** — found live 2026-07-25 still actively
  enabled (`seeker_configs.proactive_search_enabled`/`search_enabled` both `1`,
  `config/cleanuparr/cleanuparr.db`) and running every 30 minutes for both Radarr and Sonarr
  (843 job runs since 2026-07-10, per `config/cleanuparr/events.db`'s `job_runs` table),
  despite this file's own older guidance that Cleanuparr's built-in proactive search "should
  stay disabled so it doesn't redundantly hunt alongside NeutArr" — it evidently never was.
  This is a real, independent contributor to the 2026-07-24/25 mega-series-import-flood
  incidents (RuPaul's Drag Race, Snapped, Dimension 20, Modern Marvels) alongside NeutArr and
  the "Daddy's List" import list — don't assume disabling NeutArr alone stops unwanted
  automated hunting in this stack; Cleanuparr's Seeker is a second, easy-to-miss source of
  the exact same class of problem. **Disabled 2026-07-25** (`UPDATE seeker_configs SET
  proactive_search_enabled = 0, search_enabled = 0`, container stopped/backed-up/edited/
  restarted, same WAL-safety practice as every other live-DB edit in this file) - re-check
  this table if large unexpected import bursts ever recur, since re-enabling Seeker by
  mistake (or a Cleanuparr update resetting it) would silently reintroduce this. QueueCleaner
  (Cleanuparr's actual intended job - strikes/malware-block/stalled-cleanup) is unaffected and
  confirmed still legitimately useful: 4,147 runs since 2026-07-10, 696 strikes issued, but
  zero strikes in the 14 days before 2026-07-24 - a safety net that only fires when something
  is actually wrong, not noise.
- **BearMount's `config/bearmount/config.yaml` `queue_cleanup_rules` entries can have
  `action: blocklist_search`, which blocklists a failed release AND immediately fires a new
  search** — if an indexer keeps serving equally-bad releases for a given episode/series
  (fake/incomplete NZBs, wrong file types), this becomes a self-sustaining loop with no
  external trigger needed (confirmed live: RuPaul's Drag Race and Snapped looped for 4+
  hours, 500+ blocklist entries each, long after the original hunting tool that grabbed
  them was disabled). Symptom: Sonarr/Radarr's blocklist growing continuously with no
  RSS sync, no NeutArr-equivalent, and no active manual search running. Fix: unmonitor the
  affected series (stops Sonarr from acting on the retriggered search) rather than trying
  to catch it via `docker-compose-manager`/queue-clearing, which doesn't touch this loop at
  all since it's driven by BearMount's own queue-cleanup logic, not the download queue.
- **A Plex scan can freeze mid-scan for a second, distinct reason from the documented
  FUSE/D-state hang**: SQLite lock contention from an import burst. Symptom looks
  identical (progress % frozen, eventually no scanner subprocess running) but
  `Plex Media Server.log` shows `ERROR - Waited over 10 seconds for a busy database;
  giving up` repeating every ~10s, not a FUSE/mount error, and `docker logs bearmount`
  is silent for the whole window (mount itself stays fully responsive). Check for this
  log line before assuming a stuck scan needs the FUSE-abort fix — a plain
  `docker compose restart plex` clears it without any mount-cascade risk. Triggered by
  100+ near-simultaneous imports (e.g. a hunting tool's backlog draining all at once)
  flooding Plex's own SQLite writer via Radarr/Sonarr's per-import notify webhook.
- **`~/.dotfiles` fish functions and `control-panel/static/commands.json` both drift
  silently out of sync with `control-panel/app.py` after any rename or removal — neither
  is caught by testing `app.py` alone.** Found live: five fish functions for apps removed
  sessions ago (Kometa, all 6 Sportarr commands, both Tautulli commands) and five
  `commands.json` command-palette entries still pointing at `/api/nzbdav/*` (dead since
  the AltMount/BearMount rebrand) — all silently broken, none caught until specifically
  audited. After renaming or removing any app's routes, grep both
  `~/.dotfiles`'s `.config/fish/functions/*.fish` and this repo's `commands.json` for the
  old name, don't assume `app.py` being correct means the CLI/palette are too.
- **A new rclone-mount-owning container needs its `/mnt/<name>` host directory pre-created and
  `chown 1000:1000` before first start** - `/mnt` itself is root-owned, and the container can't
  `mkdir` under it (`permission denied`). Hit for both AltMount's and BearMount's first boot -
  not a one-off, expect this for any future rclone/FUSE-mounting service.
- **BearMount's config schema is stricter than AltMount's for `providers[*].last_speed_test_time`**
  - AltMount tolerated a plain RFC3339 string there; BearMount's decoder rejects anything but
    `null` or an omitted key ("expected a map or struct, got string"). Same underlying
    codebase/fork, a real behavior difference - don't assume a config.yaml copied from
    AltMount's loads as-is into BearMount.
- **Radarr/Sonarr have real bulk-delete endpoints**: `DELETE /api/v3/movie/editor` /
  `/api/v3/series/editor`, body `{movieIds|seriesIds: [...], deleteFiles: bool,
  addImportListExclusion: bool}`. Keep `addImportListExclusion: false` if the intent is "let
  Import Lists re-add these later" - `true` permanently blacklists them from list-based
  re-adding.
- **Once a compose service block is deleted, `docker compose stop/rm <service>` fails with
  "no such service"** even while the container itself is still running - use `docker stop
  <container_name>` / `docker rm <container_name>` directly for a container whose compose
  block is already gone.
- **Radarr's/Sonarr's `renameMovies`/`renameEpisodes` default to `false`** — a custom naming
  format string being set does nothing on its own; files keep their original scene-release
  names until this is explicitly turned on. Confirmed both were `false` on a freshly-wiped
  instance despite a full TRaSH naming format already configured.
- **Sonarr's real per-file TMDB-id naming token is bare `{TmdbId}`, not `{Series TmdbId}`** —
  the latter (TRaSH-Guides' own documented syntax) silently resolves to an empty string
  (`{tmdb-}` in the real folder name) rather than erroring. Confirmed live by testing several
  candidate tokens against a real series via `PUT /api/v3/series/editor` with `moveFiles:
  true`. Radarr's equivalent `{TmdbId}` (no `Movie ` prefix) is correct as documented.
- **Sonarr's/Radarr's `GET /api/v3/config/naming/examples` ignores its own query parameters**
  — it only ever reflects the currently-*saved* naming config, regardless of what format
  string is passed in. To test an unsaved format, save it for real and re-check, or trigger a
  real per-item recompute (`PUT /api/v3/series/editor` with `moveFiles: true`) against a
  series/movie that already has real IDs populated.
- **Sonarr's command queue can flood with hundreds of `RefreshSeries` entries during a heavy
  import burst** (peaked at 737 during the RuPaul's Drag Race backfill), starving every other
  queued command for minutes. `DELETE /api/v3/command/{id}` cannot cancel a running batch
  command (`409 Unable to cancel task`) — the only fix is `docker compose restart sonarr`,
  which clears the in-memory command queue (the DB-persisted download queue itself survives).
- **Prowlarr's Applications `GET` response always masks `apiKey` as `"********"`** — PUTting
  that response straight back (e.g. to force a sync) silently overwrites the real Radarr/Sonarr
  API key Prowlarr uses to connect with the literal mask string, breaking the connection.
  Always re-fetch the real key from the target app's own `config.xml` and overwrite the masked
  field before PUTting a round-tripped Applications entry back.
- **`config/bearmount/config.yaml`'s `import.max_processor_workers` is deliberately pinned at
  `1`, not the default `2`** — see the AltMount memory incident above (99.87% of a 2GiB limit
  hit when two large multi-part RAR archives were analyzed concurrently, since per-archive
  memory cost scales with part count and this library has several 50-70GB+ UHD remux releases).
  **If this is ever bumped back to 2+ for testing (a new processor, a throughput experiment,
  anything)**, treat it as reintroducing that exact risk, not a routine tuning change: watch
  `docker stats bearmount` live while a large multi-part archive is queued, and don't leave it
  at 2+ unattended unless `mem_limit` (currently 6g) has real headroom confirmed for two
  concurrent large-archive analyses, not just one. Revert to `1` if not actively testing.
- **A new poster-sync API key (`control-panel/app.py`) needs adding in two places, not one** —
  `.env` alone is not enough; it also needs an explicit line in `docker-compose.yml`'s
  `control-panel` `environment:` block (matching the existing `TMDB_KEY`/`FANART_KEY` lines),
  or the container never sees it even after `--force-recreate`. Confirmed missing `TVDB_KEY`
  from that passthrough list caused a working `.env` value to be invisible inside the container.

### Quick diagnosis: AltMount/Plex/Radarr/Sonarr symptoms from 2026-07-23

Fast symptom → cause → fix reference for the failure classes hit during the NzbDAV→AltMount
cutover, so a future session recognizes these immediately instead of re-deriving them from
scratch. Full incident narrative is in the History section below; this is the cheat-sheet.

- **Symptom: `ls`/any read on `/mnt/altmount` (or a bind-mounted subpath of it) returns
  `Input/output error`, `Socket not connected`, or `transport endpoint is not connected`,
  on the host or in ANY container that mounts it (Plex, Radarr, Sonarr, Unpackerr,
  Cleanuparr).**
  → Cause: the mount owner (`altmount`) was restarted/recreated and every dependent still
  holds a stale reference to the old mount instance — this is the exact same FUSE-mount-cascade
  class this file already documents for the old `nzbdav-rclone`, just with `altmount` as the
  sole owner now.
  → Fix: **never** `sudo umount` the mount yourself to "clear" it — if propagation is
  `rshared`, this tears down the real live mount too (confirmed live, made things worse this
  session). Instead: confirm `altmount` itself is healthy and its own `docker logs altmount`
  shows `"Successfully mounted WebDAV via RC"` recently, then `docker compose restart` (or
  `up -d --force-recreate`) the five dependents — `radarr sonarr plex unpackerr cleanuparr` —
  in one batch. Verify with `docker exec <name> sh -c "ls /mnt/altmount"` on each afterward,
  don't assume it worked.
- **Symptom: the above happens even right after `altmount` itself was *just* restarted, and
  `docker logs altmount` shows repeating `ERROR : IO error: couldn't list files: 401
  Unauthorized` in `/config/rclone.log` (or via `docker exec altmount cat /config/rclone.log`).**
  → Cause: this is the real upstream bug (javi11/altmount#691, fixed in our fork's PR #792,
  not yet merged) — `createConfig()` writes the WebDAV password into rclone's config
  unobscured, rclone then tries to de-obscure the plaintext into garbage credentials. Confirm
  by checking `docker-compose.yml`'s `altmount` service still says `image:
  altmount-local-fix:obscure-pass` — if it's back to `ghcr.io/javi11/altmount:latest`, someone
  (Watchtower?) reverted it, or this is a fresh deploy that skipped the local build.
  → Fix: rebuild the patched image (`docker build -f docker/Dockerfile -t
  altmount-local-fix:obscure-pass <cloned-fork-dir>` — the fork is `WhispersOfJ/altmount`,
  branch `fix/internal-mount-obscure-password`) and redeploy. Check whether PR #792 merged
  upstream first — if so, switch back to the stock tagged image instead of maintaining the
  fork build.
- **`~/Claude/altmount`** is a persistent local clone of the AltMount fork
  (`WhispersOfJ/altmount`). Its `main` is now the definitive, pushed baseline — consolidated
  from the original scoped PRs plus a deeper path-traversal pass, CI-gated
  (`altmount-fixes-ci.yml`: build/vet/lint/test) and kept in sync with upstream
  (`sync-upstream.yml`: daily merge from `javi11/altmount` main, `-X ours` so this fork's fixes
  win any conflicting hunk, validated before push). Treat `main` as current, not the old
  `fix/all-consolidated` branch name or the "kept deliberately local" framing from the first
  audit round — check `main` there before re-auditing AltMount from scratch.
- **Host now has a real Go toolchain** (`go` 1.26, `gopls`) installed directly on this machine
  (not just inside a container) — installed for the AltMount audit above, but usable for any
  Go work in this repo or elsewhere. The `LSP` tool needs `gopls` on the *host* PATH
  specifically; a Docker-container-only `gopls` install won't satisfy it.
- **Files created via `docker run ... golang:...` (or similar) can end up root-owned and/or
  read-only** (e.g. a mounted Go module cache) — a plain `chmod -R u+w` can fail with
  "Operation not permitted" on those files. Use `sudo rm -rf` to clean up scratch directories
  that mixed host and containerized work.
- **Symptom: a Radarr/Sonarr download sits at `status: completed` /
  `trackedDownloadState: importing` (or `importPending`/`importBlocked`) forever, no error, and
  `GET /api/v3/command` shows a `ProcessMonitoredDownloads` entry permanently stuck at
  `"status": "started"` (never reaches `completed`), blocking every other command from even
  starting (they sit at `"status": "queued"` indefinitely).**
  → Cause: a genuinely wedged background command inside Radarr/Sonarr itself — confirmed live
  this session, distinct from a single wedged download. Control-panel's own
  `/api/arr/{app}/unstick-importing` endpoint (see `arr_unstick_importing()` in `app.py`) only
  clears the *queue item*, not this stuck *command* — running it alone is not sufficient here,
  confirmed by it reporting a clean "wedged/cleared" result while the underlying command stayed
  stuck and the next grab hung identically.
  → Fix: restart the affected app's container outright (`docker compose restart radarr` or
  `sonarr`) — this was the only thing that actually cleared it. Check
  `GET /api/v3/command` again afterward to confirm no stuck entries remain before assuming the
  pipeline is healthy.
- **Symptom: a new download client that streams via a separate FUSE/WebDAV mount (a different
  filesystem than the real root folder) fails imports silently, or Radarr/Sonarr logs show
  nothing useful at all about why import never happens.**
  → Cause: `copyUsingHardlinks: true` (the default) — hardlinks cannot cross a filesystem
  boundary, and a FUSE-mounted download client's storage is never the same filesystem as
  `/data/movies`/`/data/shows` on regular disk. This doesn't surface as an obvious error in
  every version — check this setting first, don't wait for a clear failure message.
  → Fix: `PUT /api/v3/config/mediamanagement/1` with `copyUsingHardlinks: false` on both apps.
  **Superseded 2026-07-23**: this stack no longer imports from a cross-filesystem FUSE source
  at all — AltMount's `import.import_strategy` was switched to `SYMLINK` with `import_dir`
  bind-mounted from `./media/altmount-import`, on the *same* filesystem as `/data/movies`/
  `/data/shows` (confirmed via `df`), so `copyUsingHardlinks` was flipped back to `true` on
  both apps and verified live: a real import produces a genuine symlink into `/mnt/altmount`
  (`lrwxrwxrwx`, readable, streams real bytes) with zero bytes copied to local disk, not a
  real file. If this setting is ever `false` again without a new cross-filesystem source
  being introduced, something regressed — the reasoning above (hardlinks can't cross a
  filesystem boundary) is still correct, it just no longer applies to this stack's current
  download-client source.
- **Reserved-shell-variable gotcha, hit multiple times this session and worth remembering
  generally**: this environment's default shell treats `status` as a read-only variable
  (mirrors `$?`, zsh-style) — using it as an ordinary variable name in a Bash-tool script
  fails with `read-only variable: status` and can silently corrupt output if combined with
  `2>&1` redirection into a file (confirmed live: an entire bulk git-recovery loop overwrote
  33 files with error text this way before being caught by a `fish -n` syntax check). Avoid
  `status` as a variable name in ad-hoc scripts; use something like `task_status`/`dl_status`
  instead.
- **Multi-line bash `for...do...done` loops silently break when run via the Bash tool** — the
  default shell here is fish, which doesn't understand that syntax; the failure isn't always a
  clean error (confirmed live: a loop meant to iterate ~187 ids instead ran once against an
  unexpanded/mangled string, e.g. all ids concatenated into one bad request). Wrap any
  multi-line bash-style loop in `bash -c '...'` explicitly rather than trusting it to run as
  typed.
- **Building a JSON body for curl inside a nested `bash -c '...'` wrapper (needed to
  background a long-running loop) silently mangles quoting** — confirmed live twice:
  `python3 -c "...{'ids':[...]}..."` inside `bash -c '...'` inside this tool's own shell
  wrapping corrupted the embedded single/double quotes, so the loop never actually
  authenticated/deleted anything and ran harmlessly forever instead of erroring loudly.
  For any curl+JSON+loop combination, write a standalone `.py` file and run it with a
  plain `python3 script.py` instead of inlining it — avoids the nested-quoting class of
  bug entirely, and is easy to fix/rerun once, rather than debugging escaping live.
- **Radarr's `DELETE /api/v3/queue/bulk` works; Sonarr's real endpoint 404s** (confirmed live,
  same Sonarr version this stack runs) — don't assume a bulk-queue-delete endpoint is shared
  Servarr-family API just because Radarr has it. Fall back to looping individual
  `DELETE /api/v3/queue/{id}?removeFromClient=true&blocklist=false` calls for Sonarr.
  **This is queue-specific, not universal** - `DELETE /api/v3/blocklist/bulk` (body
  `{"ids": [...]}`) works fine on both apps, confirmed live building
  `stack-arr-clear-blocklist`. Don't assume every Sonarr bulk endpoint is broken just because
  the queue one is.
- **`httpx.delete()` (the module-level shortcut) doesn't accept a `json=` kwarg in this
  project's pinned httpx version** — confirmed live building `/api/arr/{app}/blocklist/clear`,
  which needs a body on DELETE (Radarr/Sonarr's `blocklist/bulk` endpoint takes `{"ids": [...]}`).
  Use `httpx.request("DELETE", url, json=...)` instead for any future control-panel route that
  needs a DELETE with a body.

- ~~Radarr's and Sonarr's "Quality Definitions" are one flat, instance-wide list each, not
  scoped per quality profile~~ **Moot as of v11.2.0**: both apps were consolidated down to a
  single "ANY" quality profile each (all other profiles deleted, everything reassigned - see
  [History](README.md#history)), so there's only one profile per instance to share the
  instance-wide size definitions with now. **Recyclarr was reinstalled 2026-07-23** (see
  History) — both apps have multiple profiles again, sharing that same instance-wide list.
- ~~Kometa's `sleep infinity` entrypoint override is load-bearing, not a placeholder~~ **Moot
  as of v11.7.0**: Kometa was removed entirely (no Jellyfin support - see the migration History
  entry), along with its Quickstart companion. No automated collections/overlays/metadata tool
  currently runs in this stack.
- **A direct subpath bind of `/mnt/nzbdav` (`rslave`) does not reliably survive the FUSE
  process underneath it being recreated** (an `nzbdav-rclone` image update, a resource-limit
  change, a plain restart). Confirmed live 2026-07-18 during the torrent/debrid removal:
  recreating `nzbdav-rclone` and its five dependents (Radarr, Sonarr, Plex, Unpackerr,
  Cleanuparr) in the same batch left every dependent unable to start (`transport endpoint is
  not connected`) until `nzbdav-rclone` was restarted alone first and the stale host mount was
  cleared with `sudo umount -l /mnt/nzbdav`. Control Panel's `restart-all` already sequences
  this correctly (`MOUNT_DEPENDENTS` now covers all five, grown from just `{"radarr"}`); the
  failure mode above is only reachable by restarting/recreating containers outside that
  endpoint.
- **Cleanuparr's `arr_configs` table needs a row for all five Servarr types (Sonarr, Radarr,
  Lidarr, Readarr, Whisparr) permanently, even for apps this stack doesn't run.** Confirmed by
  reading Cleanuparr 2.9.16's own source — `GenericHandler.ExecuteAsync` does
  `arr_configs.FirstAsync(x => x.Type == T)` per type, not `FirstOrDefaultAsync`, on every single
  QueueCleaner/MalwareBlocker run. One missing type crashes the whole job. **Never delete an
  `arr_configs` row when removing an app from this stack** — only its `arr_instances` row and
  API key. See README's Known Gaps (was: "stale Readarr reference") for the full incident.
- **Cleanuparr's Blacklist Sync feature was permanently disabled against Decypharr** (its
  qBittorrent-API emulation never implemented `POST /api/v2/app/setPreferences`, confirmed
  live: 404 even with valid login/cookie). Moot now that Decypharr is removed entirely
  (v11.0.0) — whether Blacklist Sync works against NzbDAV's SABnzbd-compatible API is
  untested, not confirmed either way.
- **Cleanuparr's Content Blocker / MalwareBlocker feature can never work in this stack — not a
  config gap, a structural limitation, confirmed 2026-07-23.** `grep -a` across the actual
  Cleanuparr 2.9.16 binary (`/app/Cleanuparr` inside the container) for download-client-type
  strings turns up only `qBittorrent`/`Deluge`/`rTorrent`/`Transmission`/`uTorrent` — no
  `SABnzbd`/`NZBGet` string exists anywhere in the build. MalwareBlocker requires a row in
  Cleanuparr's own `download_clients` table (a *direct* Cleanuparr-to-client connection,
  separate from the `arr_instances` table QueueCleaner uses) to do its blacklist deletion at
  the client level, and there is no client type it could ever register for a 100%-Usenet
  stack. `download_clients` had been empty since at least 2026-07-20 (confirmed via its own
  logs going back that far, i.e. this predates the AltMount cutover — it was already broken
  under NzbDAV too, just never noticed), and every hourly run logged `[MalwareBlocker] No
  download clients configured` the entire time with zero protective effect. **Disabled
  outright** (`content_blocker_configs.enabled` → `0` in `config/cleanuparr/cleanuparr.db`,
  container stopped/backed-up/edited/restarted, same WAL-safety practice as every other live-DB
  edit in this file; verified via the restart log no longer listing a ContentBlocker job
  trigger). **QueueCleaner is unaffected and confirmed still working correctly against
  AltMount** — it operates purely through the `arr_instances`/Sonarr-Radarr queue API (strikes,
  failed-import removal, stall detection), never touches the `download_clients` table, and its
  strike/removal logic was observed firing correctly live on AltMount-sourced downloads the same
  day. A stack-wide audit the same session found no other non-Usenet-friendly feature enabled
  anywhere else (Cleanuparr's own seeding-rule tables and Download Cleaner are empty/disabled;
  Prowlarr/Radarr/Sonarr indexers and download clients are 100% Usenet; Unpackerr has no
  torrent-client env vars) — this was the only live one.
- **Cleanuparr's own filesystem mount tracks whatever path the download client's API reports
  for each queue item** — originally added to fix QueueCleaner/MalwareBlocker crashing with
  `System.InvalidOperationException: Sequence contains no elements` against Decypharr's
  `/app/downloads`/`/app/downloads-ad` paths; updated to `/mnt/nzbdav` when Decypharr was
  removed entirely (v11.0.0), matching the `storage` path NzbDAV's own history API reports
  (`/mnt/nzbdav/completed-symlinks/<category>/...`). If a future download client changes its
  reported path convention, this mount needs to move with it.
- **NzbDAV leaks NNTP connections past its own configured `MaxConnections`, unbounded, from
  at least three independent code paths (download queue workers, `HealthCheckService`'s
  repair job, and ordinary WebDAV file reads/playback) that don't appear to share one
  enforced cap.** Confirmed live 2026-07-22: reproduced identically across the stable
  `v0.6.4` release and the `pre-release` tag (which adds a circuit breaker for multi-provider
  failover — useless here since this stack runs a single Thundernews provider with no
  backup to fail over to), across `MaxConnections` set to 2/4/10/20, and with the repair job
  (`repair.enable`) both on and off. Connection count climbs unbounded in every combination
  (observed peaks of 86, then 40→66 again minutes later after a full `docker compose rm -f
  nzbdav` + recreate — ruling out stale in-memory state, since a brand-new container
  reproduces it within seconds). This exceeds the account's real, provider-confirmed
  50-connection limit and gets the account explicitly rejected by Thundernews
  (`CouldNotLoginToUsenetException: ... 502 Connection failure. Please contact technical
  support.`), not just timed out. **This also breaks playback of already-completed library
  files, not just new downloads** — this stack has no local media disk, so NzbDAV streams
  every byte live from Usenet even for "completed" items; a plain `dd` read of an existing
  movie through `/mnt/nzbdav/completed-symlinks/...` hung and failed with the same exception.
  Filed upstream as
  [nzbdav-dev/nzbdav#477](https://github.com/nzbdav-dev/nzbdav/issues/477). Until fixed,
  restarting the `nzbdav` container (`stack-nzbdav-restart` or `stack-nzbdav-unstick`) only
  buys a small window before the leak catches back up — not a durable fix. As of this
  writing, Radarr, Sonarr, and NeutArr are stopped and both apps' RSS Sync intervals are set
  to `0` (disabled) specifically because of this bug, so automation doesn't keep feeding a
  queue that can't complete; re-enable them (and restart Radarr/Sonarr, `docker compose up -d
  radarr sonarr`, `docker compose up -d neutarr`) once the upstream issue is resolved. The
  Thundernews provider password was also rotated during this investigation (ruled out as the
  cause — the old password authenticated instantly and successfully in every manual test);
  both `.env` and NzbDAV's own `config/nzbdav/db.sqlite` were updated to match.
  **Root cause found and fixed upstream 2026-07-22**, by reading NzbDAV's own source
  (`nzbdav-dev/nzbdav`, cloned to a scratch dir, not part of this repo): two bugs, both in
  `backend/Clients/Usenet/`. (1) `UsenetStreamingClient.CreateNewConnection` opens the real
  TCP/TLS socket via `ConnectAsync` before `AuthenticateAsync`, but never disposes the
  connection if `AuthenticateAsync` throws — the socket is a local variable only returned to
  the caller on success, so a failed login abandons an open connection forever (relying on
  GC finalization, which is neither immediate nor guaranteed under load). This is the actual
  leak. (2) `ProviderCircuitBreaker`'s own doc comment claims "a single probe attempt is
  allowed" once tripped, but nothing enforces that — `MultiProviderNntpClient.
  GetOrderedProviders()` falls back to the tripped provider anyway when it's the only one
  configured, so every concurrent caller (each queued item, each health-check segment check)
  independently probes it at once with zero coordination. Fixing bug (1) alone made bug (2)
  *worse*, not better: once permits stopped leaking, retries fired fast enough to escalate
  from ~90 consecutive failures over several minutes (pre-fix) to 778 consecutive failures
  logged within a single second (fix (1) alone, live against the real account) — confirmed
  live, this is why the connection leak was accidentally throttling the retry storm the whole
  time. Both fixes together (dispose-on-failure + a real single-probe gate in
  `ProviderCircuitBreaker` via `TryEnterProbe`) were verified locally: real connection count
  stayed within the configured `MaxConnections` instead of growing unbounded, and real
  connection attempts against a tripped provider dropped to roughly one every 1-2 seconds
  instead of hundreds per second — tested first against a deliberately unreachable fake
  endpoint (zero risk to the real account), then briefly against the real account once that
  was confirmed safe. Filed as
  [nzbdav-dev/nzbdav PR #478](https://github.com/nzbdav-dev/nzbdav/pull/478) (fork:
  `WhispersOfJ/nzbdav`, branch `fix/connection-leak-and-circuit-breaker-storm`). **Not merged
  upstream yet as of this writing** — `docker-compose.yml` originally kept `nzbdav/nzbdav:latest`
  (the stock, unpatched image) pinned rather than the local patched build, since redeploying an
  unmerged fork build permanently isn't appropriate for this repo's normal image-pinning policy.
  Auth failed against the real account even with both fixes applied on an earlier test the same
  day — most likely the account itself was genuinely rate-limited/degraded from that session's
  heavy testing (a separate, external, time-based condition), not a remaining code bug.
  **Later the same day, the account recovered and the local patched build (`nzbdav-local-fix:pr478`)
  was deployed as a temporary, deliberate exception to the pinning policy** — see the entry below
  for why (recurring hangs during a Movies library scan) and the entry further below for AltMount,
  which superseded this fix entirely once evaluated. Re-check whether PR #478 has merged into a
  real release before assuming this local build is still the right call.
  **Confirmed recurring against Jellyfin directly, 2026-07-22** (separate from the Radarr/
  Sonarr/NeutArr mitigation above, which doesn't cover Jellyfin): a full Movies library scan
  (`RefreshLibrary` scheduled task) hung silently at a fixed progress percentage with zero new
  log lines and near-idle CPU — no exception thrown, since the .NET thread was just parked
  waiting on a blocked FUSE syscall, not faulted. Diagnosed by bypassing Jellyfin entirely: a
  plain `timeout 8 docker exec jellyfin find /mnt/nzbdav/completed-symlinks -maxdepth 3 -type f`
  hit the full 8s timeout with zero output — the mount itself was unresponsive, matching this
  section's own prior note that a raw `dd` read through the same mount had hung identically
  once before. **Recovery confirmed working**: cancel the stuck task first
  (`DELETE /ScheduledTasks/Running/{id}`), then restart strictly in mount-dependency order —
  `docker compose restart nzbdav` (clears leaked NNTP connections) → `docker compose restart
  nzbdav-rclone` (recreates the FUSE mount) → `docker compose restart jellyfin` (Jellyfin holds
  a stale mount reference after `nzbdav-rclone` restarts, same as every other dependent
  documented above) — verifying the same `find` test returns instantly after each restart
  before moving to the next, rather than assuming any single restart alone fixed it. A fresh
  `RefreshLibrary` trigger afterward proceeded normally. This is the same underlying bug as the
  NzbDAV connection leak above (PR #478, unmerged), just a second, previously-undocumented
  failure mode of it (a hung file read during a library scan, not just a rejected new
  connection) — no new root cause, just a new confirmed symptom.
  **The restart-chain fix above is not durable — confirmed live the same session**: the retried
  scan stalled again roughly 7 minutes after the restart, this time with the FUSE mount itself
  still responsive (`find` returned instantly) but `docker logs nzbdav` showing repeated
  `System.InvalidOperationException: Response Content-Length mismatch: too few bytes written`
  (e.g. 73830400 of 134217728 bytes) every 15-60 seconds — partial WebDAV reads dying mid-stream,
  consistent with the same NNTP-connection-leak root cause, not a new bug. This matches this
  section's own existing warning that restarting `nzbdav` "only buys a small window before the
  leak catches back up." **Deliberately left cancelled and unfinished, at the user's explicit
  choice**, rather than cycling the restart chain again expecting a different outcome — a full
  Movies library re-scan should be re-attempted only after PR #478 merges upstream into a real
  release. Don't reflexively re-run the restart-chain recovery above more than once per session
  without flagging this to the user first; it is a temporary reprieve, not a fix.
- **Jellyfin's own `Library/VirtualFolders` `RefreshProgress` field lags badly behind the real
  scan progress and cannot be trusted on its own.** During the hang above, `VirtualFolders`
  reported the Movies library frozen at `RefreshProgress: 5` the entire time, while the
  authoritative source — `GET /ScheduledTasks/{id}`'s own `CurrentProgressPercentage` — showed
  it actually climbing (24% → 35% before the hang). Use the `ScheduledTasks` endpoint, not
  `VirtualFolders`, to judge whether a scan is really moving. This also fully explains a report
  that looked like data loss but wasn't: the Jellyfin web UI's Movies library page showed a
  stale low total (2,739) while `/Items/Counts` and a `ParentId`-scoped query both independently
  confirmed the real count (9,867) twice — the UI page was reading a live, still-climbing
  in-progress count from an active (later found hung) scan, not a final total. No data was
  ever missing; ruled out first by checking `DisplayPreferences` (no stored filter) and the
  user's own `Policy` (`MaxParentalRating: None`, `EnableAllFolders: True`, no restrictions)
  before finding the real cause above.
- **Jellystat's own `Full Jellyfin Sync` task can get stuck in `Running` state in the
  `jf_logging` table forever, with no code path that ever marks it `Failed`.** Root cause,
  confirmed 2026-07-22: Jellystat holds a long-lived HTTP/WebSocket connection to Jellyfin for
  the duration of a sync; if Jellyfin's own container restarts mid-sync, that connection drops
  with `ECONNRESET` (confirmed via `docker logs jellystat`), and Jellystat's sync code has no
  handler for that disconnect that updates the task's own DB row — it just silently stops
  making progress while the row still reads `Running`, indistinguishable from a real stall
  without checking hard evidence (no new log lines for 5+ minutes, `jf_library_episodes` count
  frozen). **Fix applied**: directly `UPDATE jf_logging SET "Result"='Failed' WHERE "Id"=...`
  for the stuck row (container was not stopped first here since this is an `UPDATE` on a
  clearly-abandoned row, not a live-write conflict risk like the Cleanuparr/Lidarr-class edits
  elsewhere in this file), then `docker compose restart jellystat` — necessary because
  Jellystat's in-memory `TaskManager` singleton (confirmed via its own source,
  `backend/routes/sync.js`'s `addTask`) independently tracks whether a sync is "already
  running," so fixing only the DB row would still have blocked a fresh `/sync/beginSync` call
  after this container never crashed (`RestartCount: 0` at the time). **Don't re-run a fresh
  Full Sync in parallel with a Jellyfin library scan** — the two contending for the same
  Jellyfin API is the likely trigger for the original disconnect; wait for one to finish before
  starting the other.
- **`/sync/beginSync` and `/sync/beginPartialSync` (Jellystat's manual-trigger routes) require a
  JWT in `Authorization: Bearer <token>`, verified against `JWT_SECRET`** (the same
  `JELLYSTAT_JWT_SECRET` this stack generated into `.env` during the Plex-to-Jellyfin
  migration) — confirmed by reading `backend/server.js`'s `authenticate()` middleware directly.
  A valid token can be minted without knowing the real `APP_USER`/`APP_PASSWORD` hash (which
  this session didn't have) by signing `{user: {id: 1, username: "<any>"}}` with that same
  secret — easiest done from inside the container itself, where `JWT_SECRET` is already a live
  env var:
  `docker exec jellystat sh -c "cd backend && node -e \"const jwt=require('jsonwebtoken'); console.log(jwt.sign({user:{id:1,username:'bear'}}, process.env.JWT_SECRET))\""`.
  Confirmed working against a real `/sync/beginSync` call.

## Jellyfin reverted back to Plex, 2026-07-22 (same day as the migration)

**Jellyfin was removed entirely, same day it replaced Plex**, after repeated, unresolved
library-scan hangs (the NzbDAV connection-leak bug) made it unusable for a full scan. The user
chose full reversion over continued debugging; Jellyfin's watch history/config was lost with
no archive. `jellyfin`/`jellystat`/`jellystat-db` compose blocks, configs, and env vars were
removed; `scripts/setup_wizard.py` reverted to `PLEX_TOKEN`/`PLEX_URL`.

- **Recovery method, worth reusing for any future migration revert**: git history in both
  `media-stack` (commit `7f9cd27`) and the `~/.dotfiles` bare repo (commit `b406324`) still had
  the exact pre-migration Plex compose blocks, `.env.example` scaffolding, and
  `control-panel/app.py`'s original `/api/plex/*` routes — recovered via `git show
  <commit>~1:<path>` rather than hand-rewriting. **Never a blind `git checkout`** — real
  improvements landed after the original removal (jellystat-db backup step, OMDb/MDBList env
  secrets) that had to be preserved. **Reserved-shell-variable/redirect mistake made during this
  recovery**: a loop restoring ~33 fish functions used a string variable as a literal command
  with `2>&1`, which silently overwrote every target file with error text — caught via `fish -n`,
  recovered by rerunning the git-show loop correctly. If a bulk multi-file git-recovery loop
  "succeeds" but every file looks identical/wrong, suspect this class of bug first.
- **Fresh Plex install, not a restore** (`config/plex/` had been deleted with no archive) —
  claimed via a live `plex.tv/claim` token. Real gotchas hit: `POST /library/sections` requires
  every parameter in the URL query string, not the body; language codes are locale-specific
  (`en-US` not `en`); the VAAPI `HardwareDevicePath` must be the exact raw URL-encoded enum
  string from `/:/prefs`, not the human-decoded version.
- **Bazarr auto-repointed** via its own stored Plex OAuth grant; only needed
  `use_plex=true`/`use_jellyfin=false` plus library mapping. **Seerr could not auto-repoint** —
  its admin user was Jellyfin-local with no Plex token, and Seerr's plex-settings test route
  needs the admin's own live OAuth token, not fabricable — left pending a real browser
  "Sign in with Plex".
- **The NzbDAV connection-leak bug hit Plex within minutes of the fresh scan** — same
  account-wide bug as the Jellyfin hangs, not media-server-specific. Directly motivated
  evaluating AltMount below.

## AltMount evaluated as NzbDAV's replacement, 2026-07-22

**javi11/altmount** was researched as a replacement for NzbDAV's unfixed connection-leak bug
(PR #478, see above) — chosen over a from-scratch Rust rewrite (`nzbdav-rs`, architecturally
immune to the bug class but only 22 stars, stale) for being actively developed with no reported
matching issues. Deployed standalone first (own `altmount-eval` compose profile, not wired to
Radarr/Sonarr initially), own internal rclone/FUSE mount (no separate sidecar needed).

- **Two real first-boot config bugs, worth remembering for BearMount (same codebase lineage)**:
  (1) `rclone.path: ''` does not actually resolve to the config directory despite the sample
  comment claiming it does — fixed by setting it explicitly to `/config`. (2) An
  undocumented top-level `mount_type` field overrides `rclone.mount_enabled` entirely — omitting
  it forces `MountEnabled = false` regardless of the nested setting. Also needed `sudo chown
  1000:1000` on the config dir and a pre-created `/mnt/altmount` (`/mnt` itself is root-owned).
- **Real end-to-end streaming confirmed, not just "container healthy"**: a minimal single-segment
  NZB hand-built from a real message-id in NzbDAV's own blob store retrieved exactly the
  segment's declared byte count via AltMount's SABnzbd-compatible endpoint — genuine proof of
  article fetch, not just auth.
- **A real category-name mismatch**: AltMount's `sabnzbd.categories` needs to match Radarr's/
  Sonarr's actual configured `movieCategory`/`tvCategory` values exactly (in this stack,
  `radarr`/`sonarr`, not the more obvious `movies`/`tv` guess) or the connection test fails with
  "Category does not exist".
- **Scale of a full NzbDAV replacement**: ~42,885 unique already-imported releases, each
  symlinked into NzbDAV's own path scheme that AltMount doesn't reproduce — a full cutover means
  bulk re-submitting every real NZB, a genuinely long-running (hours) operation, not a quick
  command.

## Bulk re-link run, memory incident, and full NzbDAV removal, 2026-07-22/23

The evaluation above led directly to a same-session full cutover, executed while the user was
away for 8+ hours with instructions to log non-critical issues and only interrupt for real ones.

- **Bulk re-link executed via `scripts/altmount-bulk-relink.sh`** (resumable — tracks attempted
  blob ids in `scripts/.altmount-relink-progress.log`, skips already-processed ones on a rerun).
  Extracted 38,972 unique NZBs (12,285 Radarr + 26,687 Sonarr, explicitly excluding 3,170
  Whisparr/adult-content blobs — that library was deleted by policy years earlier, re-importing
  it would have silently undone that removal) from NzbDAV's own blob store
  (`config/nzbdav/blobs/<id[:2]>/<id[2:4]>/<id>`, confirmed to retain the full original NZB XML
  including real message-ids for every release ever imported) and submitted each via AltMount's
  SABnzbd-compatible `/sabnzbd?mode=addfile` endpoint. Completed 38,972/38,972 with 38,929 real
  successes.
- **Real incident during the run, handled without waking the user**: AltMount's memory hit
  99.87% of a 2GiB limit, coinciding with two huge multi-part RAR archives being analyzed
  concurrently — per-archive memory cost scales with part count. Fixed by raising `mem_limit`
  to 4g and reducing `import.max_processor_workers` 2→1. Also fixed a broken healthcheck
  (`/api/health` requires an authenticated session — switched to a plain port-liveness check).
- **The root incident, recurring three separate times (2026-07-22/23), that produced this
  file's hard rule below**: AltMount stages an uploaded NZB in `/tmp/altmount-uploads` before
  moving it to the persistent store, and `/tmp` was never mounted to a volume. Any container
  recreate/restart — even ones that looked unrelated, like a plain `mem_limit` bump or adding a
  category to `config.yaml` — silently wiped every NZB still queued, each time triggering
  Radarr/Sonarr's `unmonitor + blocklist without re-search` for whatever was in flight (first
  occurrence: ~28,460-item backlog gutted, only 748/1,748 processed items actually succeeded;
  second: 237 queued NZBs wiped, 40 items unmonitored/blocklisted; third: ~778 rows wiped, 6
  items affected). Each time recovered the same way: stop `altmount` immediately, drop the dead
  `import_queue` rows (container stopped, DB backed up first), restart `altmount` + the five
  mount-dependent containers per the FUSE cascade rule, clear the resulting blocklist entries
  and re-monitor the affected items so a regrab isn't silently skipped.
  **Hard rule, no exceptions, carried forward unchanged to BearMount** (see the Commands section
  at the top of this file): before running `docker compose up -d altmount`, `--force-recreate
  altmount`, `docker restart altmount`, or `docker stop`/`kill altmount` for *any* reason — a
  memory tweak, a config one-liner, anything — first run `sqlite3 config/altmount/altmount.db
  "SELECT status, COUNT(*) FROM import_queue GROUP BY status;"` and confirm `pending`/
  `processing` is 0, or drain/wait it out first. The reason for the recreate does not matter —
  "it's just a memory bump" is exactly the reasoning that caused this to happen three times.
- **User's response on return: abandon the old library entirely rather than repair the
  re-link.** Explicit instructions, executed in this order:
  1. AltMount's queue backlog (39,168 rows) killed directly via
     `DELETE FROM import_queue` in `config/altmount/altmount.db` (container stopped first,
     WAL-safety, same practice as every other live-DB edit in this file) rather than the
     one-nzo-id-per-call SABnzbd delete endpoint, which has no bulk form.
  2. **Radarr's and Sonarr's databases fully wiped** (confirmed scope via explicit
     clarification: "only API key/download client/indexer config survives" — everything else,
     including quality profiles and root folders, was expected gone). Full `config/radarr`/
     `config/sonarr` backed up first to `~/backups/pre-wipe-<timestamp>/`. `radarr.db`/
     `sonarr.db` (+ `-wal`/`-shm`) deleted outright and let the app recreate a fresh schema on
     restart, rather than hand-editing tables — safer given foreign-key relationships an
     unfamiliar schema could break. `config.xml` (real API key) was never touched. Download
     client re-added via API (**stripping the leftover `id` field before POST** — Radarr/Sonarr
     reject creating a new row with an explicit existing id, "Can't insert model with existing
     ID 1"). Indexers were **not** successfully hand-recreated via API (400s — these are
     Prowlarr-owned definitions, not meant to be manually reconstructed); instead, re-saving
     Prowlarr's own Application entry with `?forceSync=true` on `PUT /api/v1/applications/{id}`
     triggered a real, immediate sync that recreated all 3 indexers on both apps correctly.
     Quality profiles came back automatically (Radarr/Sonarr create defaults on any fresh DB
     init); root folders (`/data/movies`, `/data/shows`) had to be re-added manually via
     `POST /api/v3/rootfolder`.
  3. **NzbDAV removed entirely** — `nzbdav`/`nzbdav-rclone` compose blocks deleted; `/mnt/nzbdav`
     unmounted on the host (`sudo umount -l`) and every remaining `/mnt/nzbdav` bind mount
     (Plex, Radarr, Sonarr, Unpackerr, Cleanuparr) repointed to `/mnt/altmount`; `config/nzbdav`
     (51GB) and `config/nzbdav-rclone` deleted; `NZBDAV_*` `.env`/`.env.example` vars renamed to
     `ALTMOUNT_*` where the same real credentials still apply (the Thundernews provider
     host/user/password, now consumed by AltMount's `config.yaml` instead); `control-panel/app.py`
     reworked (`nzbdav_api()`→`altmount_api()`, `/api/nzbdav/*`→`/api/altmount/*`, `CONTAINER_LABELS`,
     `MOUNT_PREREQS`/`MOUNT_PROVIDERS` simplified to reflect AltMount owning its own mount
     directly with no separate rclone sidecar) — `set-connections`/`unstick` routes were **not**
     ported, both were workarounds for NzbDAV-specific bugs (its non-REST settings API; its
     history-query-hang-causing-Sonarr-unavailable chain) that don't apply to AltMount, dropped
     outright rather than guessed-and-carried-forward; `scripts/nzbdav-prune-history.py` →
     `scripts/altmount-prune-history.py` (same logic, real endpoint path difference:
     `/sabnzbd` not `/api`), its systemd timer/service swapped the same way (old symlinks in
     `~/.config/systemd/user/` were live and enabled — disabling/removing/relinking done in
     one pass, not left dangling); the `.claude/skills/` project skills
     (`secret-injector`, `usenet-orchestrator`, `docker-compose-manager`) also referenced NzbDAV
     and were updated — `usenet-orchestrator`'s `diagnose-stuck-file` command was **not** ported
     (built around NzbDAV/nzbdav-rclone's specific `.ids/<uuid>` log pattern, no confirmed
     AltMount equivalent exists yet) and now refuses to run rather than search logs that likely
     don't match; every `stack-nzbdav-*` fish function reworked to `stack-altmount-*` or deleted
     outright (`set-connections`/`unstick` had no port target, matching the backend routes).
  4. **Plex's own library was left holding ~9,867 movies/424 shows worth of now-permanently-broken
     symlinks** (Plex's own DB was never wiped, only Radarr/Sonarr's) — flagged to the user as a
     real, non-obvious consequence of steps 2-3 rather than silently left broken. The user chose
     to mass-delete Plex's library manually rather than have it done programmatically.
- **Resolved 2026-07-23, see the dedicated entry below**: this bullet used to say AltMount's
  `import_strategy: NONE` direct-import pipeline was unverified end-to-end. It was verified,
  found to be silently writing real files to local disk instead of symlinks (`import_strategy:
  NONE` + `copyUsingHardlinks: false` together mean every import is a real byte copy), and
  fixed by switching to `import_strategy: SYMLINK`. See "Local media eliminated, AltMount
  switched to SYMLINK import strategy, 2026-07-23" below for the full incident.

## Local media eliminated, AltMount switched to SYMLINK import strategy, 2026-07-23

A routine disk-usage question ("how full is my root disk") surfaced a real architecture
regression: **318.7GB across 150 real (non-symlink) files** were sitting under
`media/movies`/`media/shows`, contradicting this file's own long-standing "root folders are
100% symlinks" invariant. Root cause: AltMount's `import.import_strategy` was `NONE` (a direct
copy/hardlink import, unlike NzbDAV's old symlink-into-FUSE-mount model), combined with
Radarr's/Sonarr's `copyUsingHardlinks: false` (a deliberate earlier fix for when the download-
client source was the cross-filesystem `/mnt/altmount` FUSE mount, see the landmine above) —
together these guaranteed every import since the AltMount cutover wrote a real byte-for-byte
copy to local disk. The other ~34,809 items in the library turned out to be symlinks, but
**every single one sampled was broken**, pointing at `/mnt/nzbdav/.ids/...` — dead since NzbDAV
was removed entirely. The real, working library was 100% those 150 real files; the pre-cutover
library was 100% non-functional.

**Fix, at the user's explicit direction ("I want no media on the disk, make the config match
that")**:
1. Added a new host directory, `./media/altmount-import`, confirmed via `df` to be on the
   *same filesystem* as `./media/movies`/`./media/shows` (both under `/`, `nvme0n1p2`) — bind-
   mounted identically as `/mnt/altmount-import` into `altmount`, `radarr`, and `sonarr`
   (`docker-compose.yml`).
2. AltMount's `config.yaml`: `import.import_strategy` → `SYMLINK`, `import.import_dir` →
   `/mnt/altmount-import`. AltMount now creates a symlink there pointing into `/mnt/altmount`
   (the real FUSE-streamed content) instead of writing bytes.
3. Radarr's and Sonarr's `copyUsingHardlinks` flipped back to `true` via
   `PUT /api/v3/config/mediamanagement/1` on both — now safe because the symlink source and
   the root folder share a filesystem, so a "hardlink" of a symlink just creates another
   symlink, never a real copy. See the landmine above for the historical reasoning this
   supersedes.
4. Recreated `altmount` first (mount-cascade ordering, see the existing landmine on this),
   confirmed healthy, then `radarr`/`sonarr` — all three confirmed to see the new shared mount
   correctly before touching anything else.
5. **All 318.7GB of real files and all ~34,809 broken symlinks were deleted** (`find
   media/movies -mindepth 1 -delete`, same for `media/shows`) — root disk went from 92% to 20%
   used. Radarr/Sonarr's own `RescanMovie`/`RescanSeries` commands **refused to update anything**
   (`"Movie's root folder (/data/movies) is empty. Rescan will not update movies as a failsafe"`,
   HTTP 409 on `DELETE /api/v3/moviefile/{id}` too) — a deliberate app-level protection against
   mistaking a disconnected mount for real deletion, and neither app exposes an API override for
   it. Worked around the same way this file already documents for other app-level DB blocks:
   stopped each container, directly edited `radarr.db`/`sonarr.db` (`UPDATE Movies SET
   MovieFileId = 0`, `DELETE FROM MovieFiles`; same pattern for `Episodes`/`EpisodeFiles`),
   backed up both DBs first, restarted.
6. `MissingMoviesSearch`/`SeriesSearch` triggered for the 3 tracked movies and the 2 series that
   actually had files (WWE: Unreal, The West Wing) — **narrower scope was a deliberate user
   choice**, not a default: rebuilding the entire former ~35,000-item library was explicitly
   ruled out as a separate option (tens of thousands of real grabs over hours/days) versus just
   proving the new pipeline on what's currently tracked.
7. **Verified live, not just configured**: the first completed import (The Dark Knight) landed
   as a real `lrwxrwxrwx` symlink into `/mnt/altmount/movies/...` — confirmed via `stat` from
   both the host and inside the `radarr` container, and confirmed it actually streams (`head -c
   1024` returned real bytes through the symlink, not a dangling-link error).
- **A real, separate download-client-side incident surfaced during this same reimport**: Sonarr
  had **Law & Order: Special Victims Unit** (594 episodes across 28 seasons, monitored, 0 files)
  independently backfilling its entire catalog through AltMount's single-worker queue at the
  same time, ballooning it to 544GB / 100+ items and delaying the actual reimport target items
  behind it. Not a bug — a real, legitimate (if enormous) missing-episode search running
  concurrently with unrelated work. Fixed by unmonitoring the series in Sonarr (stops *future*
  searches only) and separately clearing its ~120 already-queued AltMount items. **Found a real
  AltMount API bug doing this**: `mode=queue&name=delete` only accepts one `value` (a single
  `nzo_id`) per call despite normal SABnzbd convention supporting a comma-separated list — passing
  a joined list silently deletes nothing beyond whatever the string coincidentally parses as, and
  the endpoint **always returns `{"status": true}` regardless of whether anything was actually
  deleted** (confirmed by reading `internal/api/sabnzbd_handlers.go`'s
  `handleSABnzbdQueueDelete` directly — the final fallback literally always returns success).
  Worked around by looping one DELETE call per `nzo_id`; verified against the real queue
  afterward rather than trusting the reported status.
- **A second real mount-cascade recurrence, same session**: recreating `altmount` for the
  `SYMLINK` config change (step 4 above) was done via a direct `docker compose up -d
  --force-recreate altmount` rather than Control Panel's own `restart-all` endpoint, which
  already encodes the correct `MOUNT_DEPENDENTS` ordering — `radarr`/`sonarr` were manually
  restarted afterward, but **`plex`, `unpackerr`, and `cleanuparr` were forgotten**, all three
  confirmed holding stale FUSE references (`Transport endpoint is not connected` / `Socket not
  connected`) when checked later. Fixed by restarting all three; confirmed Plex could stream a
  real symlinked file afterward. Lesson reinforced, not new: manually recreating a mount owner
  outside `restart-all` means manually remembering *every* entry in `MOUNT_DEPENDENTS`, not
  just the ones actively being worked on.
- **Plex's library section paths reconfirmed correct** during the same check: `Movies` → real
  path `/data/movies`, `Shows` → real path `/data/shows` (via `/library/sections`), matching
  Radarr's/Sonarr's root folders exactly, and Plex's own compose block does mount
  `/mnt/altmount:/mnt/altmount:rslave` — the Stash/Jellyfin-class "root folder consumer missing
  the FUSE mount" bug this file already documents does not apply to Plex's current config.

## Control Panel redesigned entirely: no boxes, no tabs, permanent log console, 2026-07-23

Full rebuild of `control-panel/static/{index.html,style.css,app.js}` plus one new backend route
(`GET /api/docs/readme`), at the user's explicit request to remove the box/card and sidebar-tab
paradigm entirely. A plan artifact with three labeled options per category (log console, source
selection, PC operations, navigation, visual system, interaction model) was produced and
approved before any code changed — see that artifact for the full option/tradeoff writeup this
summarizes.

- **Navigation**: the old sidebar-button + hidden-`<section>` pattern (functionally a tab strip
  despite not looking like one) is gone entirely, replaced by a fixed two-column split-pane
  workspace — a scrollable left column of rule-divided rails (Overview, Fleet, Host, Reference)
  and a permanently pinned right-hand log console. There is no "page" concept and no
  `showPage()`/`wireSidebarNav()` left in `app.js`.
- **Log console**: single-focus, always-visible in the right column, fed either by a
  grouped-by-subsystem source `<select>` or automatically when a palette command targets a
  container (`resolveLogContainer` → `selectLogSource`). `/api/container/{name}/logs/stream`
  now requests `timestamps=True` from the Docker SDK and the client reformats Docker's own
  RFC3339Nano prefix into a compact local clock (`formatLogLine`/`formatLogText` in `app.js`) —
  real per-line record time, not client receipt time. Applied to both the pinned console and
  the arr apps' one-shot log view (`/api/arr/{app}/logs`, also now `timestamps=True`).
- **Fleet**: every container from `/api/containers` grouped by subsystem (a static, display-only
  map mirroring `CONTAINER_LABELS`' own non-gating precedent — an unmapped service just falls
  into "Other", never hidden), collapsible per group (state persisted in `localStorage`).
  Clicking a row's tail-log icon sets it as the active log source.
- **Host**: two lanes, deliberately separated by risk class — a read-only "Vitals" lane wired
  to routes that are genuinely host-backed given this container's actual mounts
  (`mount-health`, `oom-check`, `resource-check`, `disk-usage`, `backup-verify`), and a
  "Fleet-wide actions" lane for destructive/long-running ops (`restart-all`, poster sync,
  backup-integrity-check). **Real host package-update/reboot-needed/mem-pressure/zombie-check
  checks were deliberately NOT built as live panels** — confirmed this container has no
  `pacman`, no `pid: host`, and no real host `/proc` (its own `/proc/pressure` reflects the
  container's own cgroup, not the host), so building those as live tiles would present fake or
  container-scoped data as if it were the host's. They're listed in Reference as terminal-only
  fish commands instead.
- **Reference**: quicklinks (Tautulli dropped — see the "still present but not installed" entry
  above), a "Documentation" group linking each of the 13 third-party apps' real upstream docs
  (every URL verified against `docker-compose.yml`'s actual pinned image via `gh repo view`/
  `gh search repos` before being hardcoded — not guessed from the app's common name; notably
  Seerr's real org is `seerr-team`, Watchtower's real maintained fork is `nicholas-fedor`,
  NeutArr's real repo is `I-am-PUID-0/NeutArr`, none of which match an obvious guess), plus
  this stack's own README.md served locally via the new `/api/docs/readme` route since **this
  repo has no public downstream mirror to link to** (see the `AGENTS.md` note elsewhere in this
  file). A separate, explicitly read-only list of the 14 Claude Code skills this project uses
  is shown too, clearly labeled as dev-time-only (this app has no mechanism to invoke them).
  **Correction, 2026-07-24**: this bullet used to claim Tautulli and Kometa's doc-link rows
  carried a "not installed" badge (`installed: false` in `DOC_LINKS`) — never true; `DOC_LINKS`
  never had entries for either app at any point. The `installed: false` UI branch, its
  `not-installed-tag` CSS class, and this now-incorrect comment were all removed outright as
  dead code with zero live callers (see the tautulli/kometa/quickstart removal correction near
  the top of this file).
- **Visual system**: cool slate + one steel-teal accent (`#1f6f6b` light / `#4fb3ad` dark), IBM
  Plex Sans/Mono, zero border-radius anywhere, hairline 1px borders instead of shadows/cards.
  Muted red kept for status semantics only (errors/destructive), per explicit user direction —
  not a decorative color.
- **Interaction model**: panels for passively viewing state, a command palette (`Ctrl/Cmd+K`,
  overlay not a page) for triggering any of the 146 `commands.json` operations — same
  fuzzy-match/confirm-arm engine as before, just rendered as a transient overlay instead of a
  dedicated "Console" page, and a running command's log now streams into the persistent
  right-column console instead of its own embedded pane.
- **Kometa's "Run Kometa now" rapid action was removed from Overview**, along with its now-
  unused library-picker helpers — it would always fail (`Kometa container not found`) given
  Kometa has no running container, matching the "present but dormant" correction above.
- **No headless browser was available to screenshot this in this environment** (no system
  Chrome; Playwright's installer refuses to install on CachyOS, only Ubuntu/Debian are
  supported) — verified instead via a full static cross-check (every `getElementById`/
  `querySelector` target in `app.js` confirmed to exist in `index.html`, no stale references to
  deleted classes), live endpoint checks, and the user's own live browser session confirming it
  visually (their own traffic was visible in `docker logs control-panel` polling the new
  endpoints throughout).

## Seerr and Bazarr reconnection fixes, 2026-07-23

Two separate real leftovers found from the Jellyfin-to-Plex reversion, neither caught at the
time:

- **Seerr's `mediaServerType` was still `2` (JELLYFIN)** even after Plex came back — confirmed
  via `seerr-team/seerr`'s own compiled `dist/constants/server.js` (`PLEX = 1, JELLYFIN = 2,
  EMBY = 3, NOT_CONFIGURED = 4`, not guessed). Its Plex library entries were present with the
  right real IDs but `enabled: false`. Fixed: `main.mediaServerType` → `1`, both Plex libraries
  re-enabled via `GET /api/v1/settings/plex/library?enable=1,2&sync=true` (the real endpoint,
  found by reading `internal`... rather, `dist/routes/settings/index.js` directly — the
  library-enable state isn't settable through the documented `POST /settings/plex` body, which
  rejects `libraries` as read-only), then a real full scan triggered and confirmed complete in
  logs (`Plex Scan: Full Scan Complete`).
- **The "bear" Seerr user account was still Jellyfin-linked** (`userType: 3`, real
  `jellyfinUsername`, no `plexId`/`plexToken`) despite `permissions: 2` (admin) already being
  correct. Fixed using the account's own real, already-valid Plex token (`.env`'s `PLEX_TOKEN`)
  against `plex.tv/api/v2/user` to get the genuine linked identity (`TheDaddyBear`, id
  `277265765`, real email) rather than fabricating one — `userType` → `1`, `plexId`/
  `plexUsername`/`plexToken` populated for real, Jellyfin fields cleared. DB stopped/backed-up/
  edited/restarted, same practice as every other live-DB edit in this file.
- **Seerr's request history (144 `media_request` rows, cascaded 1,208 `season_request` rows)
  and its entire local media cache (19,021 `media` rows, cascaded 2,871 `season` rows) were
  both cleared at explicit user request**, in two separate passes (`DELETE FROM media_request`
  then, later, `DELETE FROM media` — both with `PRAGMA foreign_keys = ON` so the cascades
  actually fired, container stopped/backed-up first each time). Verified the media cache
  rebuilds cleanly from a fresh `/settings/plex/sync` trigger afterward — landed at 4 real
  titles, not the stale 19,021, confirming the rebuild reflects only what's actually in Plex.
- **Bazarr's SignalR connections to Radarr and Sonarr were silently dead for 4+ hours** —
  Radarr/Sonarr had both been recreated (unrelated mount-fix work earlier the same day) but
  Bazarr's own container hadn't restarted since the previous day, so its long-lived SignalR
  feeds never noticed the peer restart and never logged a reconnect attempt (unlike earlier
  drop/reconnect cycles the same day, which *did* self-heal). Config (API keys, Plex OAuth
  link) was already entirely correct — this was purely a stale-connection issue. Fixed with a
  plain `docker compose restart bazarr`; confirmed both SignalR feeds reconnected cleanly with
  zero errors afterward, and `/api/system/status` reported live real versions from both apps.

## Recyclarr reinstalled, trash-guides-applier skill found broken, 2026-07-23

User asked to sync custom formats/quality profiles with TRaSH-Guides, explicitly ruling out
Recyclarr at first. `trash-guides-applier` skill was tried instead — its bundled JSON turned
out mostly unusable: 9 of 11 custom formats (`profiles/{radarr,sonarr}-profiles.json`) are
placeholder stubs (`{"type": ..., "value": ...}`, not real Radarr/Sonarr `implementation`/
`fields` shape — one 400'd immediately with "Condition name(s) cannot be empty"), and
`applier.py`'s `apply` command creates quality profiles with `"items": []` and no `cutoff`,
which both apps' real API rejects outright (500, `ArgumentNullException: source`) rather than
accepting as a fillable skeleton. Only the one custom format with a real API shape ("Blocklist:
Unwanted Groups/Sources, RU-CN Audio, Blu-ray") applied successfully via this skill — quality
profiles never got created through it at all. **Don't trust this skill's bundled profile JSON
or its `apply` quality-profile path without re-verifying against a live `/qualityprofile/schema`
first** — the custom-format diff/apply path for a real-shaped entry does work correctly.
User then explicitly reversed the "no Recyclarr" instruction and asked for it reinstalled.
Recovered verbatim from the v11.2.0 removal commit (`ead5f04~1` / `4f6f9f4~1`): compose
service block, `config/recyclarr/recyclarr.yml` (real TRaSH profile/CF trash_ids for both
apps), control-panel's `/api/recyclarr/status` route + `CONTAINER_LABELS` entry, and the
`stack-recyclarr-status` palette command in `commands.json` — not rebuilt from scratch.
A manual `docker exec recyclarr recyclarr sync` was run to verify immediately rather than
waiting for the 6am cron — confirmed live: 62 CFs/3 profiles on Radarr, 42 CFs/3 profiles on
Sonarr, matching `recyclarr.yml`'s own trash_ids. Existing "Any" profile assignments were
left untouched on both apps — this only recreated the tiered profiles, it didn't reassign
any movie/series to them.

## Sportarr removed entirely, 2026-07-24

Added 2026-07-23 (see the Sports PVR entry this file used to carry), removed less than 24
hours later after its Plex integration turned out to be structurally broken, and the user
chose full removal over continued debugging.

- **Root cause of the Plex problem**: the Wrestling library had two root locations,
  `/data/wrestling/WWE` and `/data/wrestling/WCW` — both one directory too deep. Since
  Sportarr's own naming convention is `{Series}/Season {year}/`, pointing the library root
  directly at the league folder made Plex treat each `Season 2021`/`Season 2023`/`Season
  2024`/`Season 2025` folder as its own top-level show (`guid="local://..."`, Plex's
  unmatched-item placeholder) instead of a season under one real "WWE" show. Confirmed via
  `section_locations` in Plex's own SQLite DB and Plex's scanner log (`"There were 1
  top-level paths for Season 2023"`, match requests for `'Season 2023'` etc. all returning
  "no metadata"). Consolidating to a single `/data/wrestling` root and forcing a rescan fixed
  it for WWE (73 real episodes, 5 real seasons, real TMDb-backed metadata) — but one WCW file
  (`Bash At The Beach 1999`) never got picked up by Plex's scanner even after empty-trash,
  repeated forced rescans, and touching the file plus both parent directories to force an
  mtime change; Plex kept reporting the `WCW` directory as unchanged and never created an
  item for it. This remained unresolved when the user decided to remove Sportarr rather than
  debug further — not a symlink/mount problem (AltMount/FUSE were confirmed healthy and
  streaming correctly throughout), a Plex scanner-cache quirk specific to that one file.
- **Everything removed, verified physically gone, not just stopped**: `sportarr` container
  stopped and `rm -f`'d; `sportarr/sportarr:latest` image `docker rmi`'d; `config/sportarr`
  (41MB) and `media/wrestling` (372KB, 100% symlinks per this stack's usual policy — no real
  bytes were ever stored) deleted with `rm -rf`; Plex's "Wrestling" library section deleted
  via `DELETE /library/sections/5` (not just emptied); Prowlarr's Sportarr Application entry
  (id 5, the second Sonarr-type sync target) deleted via `DELETE /api/v1/applications/5`.
  `docker-compose.yml`'s service block, its `SPORTARR_API_KEY` env line into control-panel,
  and Plex's now-dangling `./media/wrestling:/data/wrestling` volume mount all removed;
  `SPORTARR_API_KEY` dropped from `.env`/`.env.example`; `control-panel/app.py`'s
  `SPORTARR_URL`/`SPORTARR_API_KEY` vars, the `sportarr_api()` helper, all six
  `/api/sportarr/*` routes, and its `CONTAINER_LABELS`/`MOUNT_DEPENDENTS`/
  `ARR_LOG_CONTAINERS` entries all deleted outright (no dead-route/degrade-gracefully
  treatment — this wasn't a removed-but-still-reachable dependency like the old Plex routes,
  it never needs to respond again). No frontend (`static/*.js`/`*.html`) or `commands.json`
  entries existed for Sportarr at all — the redesigned Control Panel UI (see its own History
  entry above) never wired these routes into any panel, so there was nothing to unwire there.
  109 unit tests pass, ruff clean, `docker compose config` validates clean for both the core
  and `extras` profiles after the edits.
- **Queue cleanup done the documented-safe way, not a raw DB wipe**: AltMount's own SABnzbd
  bulk-delete (`mode=queue&name=delete` with a comma-joined value list) is the already-known-
  buggy endpoint that silently no-ops beyond the first id and always reports
  `{"status": true}` regardless (see the earlier AltMount API bug entry above) — so all 11
  `category='sportarr'` queue items were deleted with one API call per `nzo_id` instead, then
  verified against both the live SABnzbd-compatible queue (0 remaining `sportarr` slots) and
  `import_queue`'s own `category='sportarr'` row count, not just trusted from the response.
  **AltMount's `config.yaml` still needs a container restart to actually drop the `sportarr`
  SABnzbd category and stop advertising `sportarr_instances: []`** — both were removed from
  the file, but the queue had 246 pending / 1 processing items for *other* categories
  (Radarr/Sonarr) at the time, so per this file's own hard rule (see the repeat
  altmount-recreate-wipes-the-queue incidents above) the restart was deliberately deferred
  rather than risking another blocklist-fallout cascade. Restart `altmount` once
  `SELECT status, COUNT(*) FROM import_queue GROUP BY status;` shows 0 pending/processing, to
  make the category removal take effect.
- **Cleanuparr, NeutArr, and Bazarr needed no cleanup** — confirmed live: Cleanuparr's
  `arr_instances` table never had a Sportarr row (only Sonarr and Radarr), NeutArr has no
  `sportarr.json` placeholder file, and Bazarr was never wired to it at all (single-Sonarr-
  instance limitation, already a documented accepted gap before this removal). No `~/.dotfiles`
  fish functions referenced Sportarr either — Control Panel's dedicated `/api/sportarr/*`
  routes were apparently never given their own `stack-sportarr-*` CLI wrapper.
- **Full stack health swept after every change** — all remaining containers healthy, all HTTP
  endpoints reachable (Tautulli's expected failure aside — it has no container, see the
  "present but dormant" correction elsewhere in this file), confirming the removal didn't
  regress anything else.

## Backup/DR details beyond "restic + a Dropbox tarball"

- **restic was fully removed from this stack twice: 2026-07-23 (repos deleted, systemd units
  stopped/unlinked but source files kept for later relinking) and again 2026-08-12 (this time
  total — code, scripts, systemd units, control-panel wiring, and the actual repo data all
  deleted, no relinking path left).** Between those two dates restic was apparently redeployed
  and back in production use, since it was fully wired live going into the 2026-08-12 removal —
  if a future session finds restic wiring again, that means a third setup happened after this
  entry was written; check `git log --all -- 'scripts/backup-config.sh'` for the real history
  before assuming this note is current. `scripts/arr-app-backup.py` (Radarr/Sonarr's own native
  Backup command) was never restic-based and was not touched by either removal.
  Everything below this bullet describes the backup system as it existed before the 2026-08-12
  deletion - read it as design/history, not as "this is currently running."
- **No Postgres-backed service ran in this stack from v11.0.0 (when `zilean-postgres` was
  removed with the rest of the debrid layer, along with `scripts/backup-config.sh`'s
  logical-`pg_dump` step for it) until 2026-07-22, when `jellystat-db` (`postgres:18.1`)
  reintroduced one** as part of the Plex-to-Jellyfin migration (Jellystat, Tautulli's
  Jellyfin-equivalent, needs its own Postgres). **This is exactly the gap this section already
  warned about — `jellystat-db` currently has zero backup coverage**, since it has no logical
  `pg_dump` step of its own yet and restic's raw-datadir exclusion (see below) doesn't cover a
  live Postgres datadir safely. Not yet fixed as of this writing; treat this as a known,
  outstanding gap, not something already handled. Any other new DB-backed service added later
  gets the same zero-coverage default unless it gets its own logical-dump step added.
- **restic exit code 3 (some files unreadable/locked) is treated as a soft warning that still
  lets pruning proceed**, not a hard failure. Discord alerting keyed only on "error"-level restic
  output will miss a *recurring* partial-backup problem that never escalates past exit code 3.
- **`scripts/backup-claude-dir.sh` overwrites a single Dropbox tarball in place every run — there
  is no retained history for that leg at all**, unlike the restic repo's normal snapshot
  retention. Already established this script isn't the real DR mechanism; this is the specific
  reason why (one bad run can silently replace the only copy).
- **A from-scratch host restore needs `/mnt/nzbdav` created manually before `docker compose up`,
  or `nzbdav-rclone` crash-loops.** Confirmed live during the 2026-07-20 full restore onto a
  fresh CachyOS install: the host bind-mount target for the FUSE mount (`/mnt/nzbdav:/mnt/nzbdav`
  in `docker-compose.yml`) doesn't exist on a truly fresh disk the way it silently persisted
  across the old install's reinstalls, so rclone fails with `mountpoint does not exist:
  /mnt/nzbdav` in a tight restart loop until `sudo mkdir -p /mnt/nzbdav` is run first. Not
  covered by any backup/restore script since it's host filesystem state outside `~/Claude`
  entirely — add this as a manual pre-step to any future from-scratch restore runbook.

## Historical incidents worth knowing before touching related code

- **All four rotatable API keys (Radarr, Sonarr, Prowlarr, NzbDAV) were rotated 2026-07-22**,
  triggered by a live Sonarr key found hardcoded in `.claude/settings.local.json` (an
  untracked, personal-override file — see its own `.gitignore` entry added the same day).
  Radarr's and Sonarr's `apiKey` field in `config/host` silently ignores changes via a plain
  API PUT — the actual key lives in `config/<app>/config.xml`'s `<ApiKey>` element and only
  takes effect after a container restart; there is no REST-only way to rotate it. Doing so
  also required setting `AuthenticationMethod` from `Forms` (with blank, already-unusable
  username/password — GET always returns empty for these fields even when populated, and PUT
  validation demands them non-empty for `Forms`) to `None`, since the real credentials were
  never known and re-supplying them wasn't an option — a deliberate, approved security
  tradeoff, not an oversight. Every consumer of the old Radarr/Sonarr keys was updated and
  live-tested afterward: Prowlarr's Applications sync entries (`/api/v1/applications/{id}`,
  needs the read-only `id` field stripped before a PUT to Seerr's equivalent endpoint, and
  before that field, before the PUT will validate), Seerr's `/api/v1/settings/radarr|sonarr`,
  Bazarr's own `/api/system/settings` form-encoded endpoint (see
  [Bazarr](README.md#bazarr-subtitle-management) for its gotchas), Cleanuparr's `arr_instances`
  SQLite table (edited with the container stopped first, same WAL-safety practice as the
  Lidarr/Whisparr removals), and NeutArr's `radarr.json`/`sonarr.json` (NeutArr itself stays
  stopped regardless, per the NzbDAV connection-leak landmine above). NzbDAV's own SABnzbd-
  compatible key lives at config key `api.key` (rotatable via the same login+update-config
  pattern as `usenet.providers`) and also needed updating in Radarr's and Sonarr's own NzbDAV
  download-client entries (`/api/v3/downloadclient/1`). Plex's token was deliberately left
  alone — it's a sign-in session token, not a simple regenerate-via-API key, and carries a
  real risk of disrupting connected clients.
- **NeutArr was getting OOM-killed roughly every 30 minutes inside its 512MB `mem_limit`, fixed
  2026-07-18 by raising it to 1g.** Invisible from any dashboard because `restart: unless-stopped`
  just quietly restarted it — `docker stats`/`docker inspect` (OOMKilled flag / restart count) was
  the only way it was ever caught, container "looked up" the whole time. Found during a
  stack-wide `mem_limit` audit prompted by the anime/DMM/adult-content removals — every other
  service's limit turned out to already be deliberately tuned with documented rationale in its
  own compose comment (Zilean's 4g tied to `DOTNET_GCHeapHardLimit`, Decypharr's 1.5g to an
  observed 540-580MB steady state, Byparr's 2g to concurrent Camoufox headroom, Kometa's 2g to a
  642MB observed real-run footprint); NeutArr's 512m was the one outlier with no such comment.
  If a service ever looks "up" on every dashboard but behaves erratically, check `OOMKilled`
  before assuming an app-level bug.
- **An unexplained mass Radarr/Sonarr library deletion happened once, with zero trail in either
  app's API or logs** — root cause was never found. The Recycle Bin setting was turned on
  afterward purely as forward-looking mitigation, not because the mechanism was identified. If a
  similar report ever comes in, don't assume Recycle Bin retroactively explains or prevents every
  case — it wasn't proven to be the actual cause the first time. **Partial follow-up found
  2026-07-22, during the Plex-to-Jellyfin migration (see below)**: while auditing Plex's Movies
  library before decommissioning it, it turned out to only have 59-63 items indexed against
  ~10,004 real files on disk. Plex's own `Plex Media Scanner.log` showed a single event on
  2026-07-13 (9 days earlier) where the scanner removed 661 of 794 tracked items in one pass
  ("Taking 661 items out of the map... for being unavailable"), with `autoEmptyTrash` confirmed
  `true` via Plex's own `/:/prefs`. This is very likely the missing Plex-side half of this same
  incident: real files vanished from disk (the Radarr/Sonarr side above), Plex's next scan found
  the symlinks broken, and `autoEmptyTrash` silently deleted the corresponding library items.
  Confirmed *not* caused by the NzbDAV connection-leak bug (also dated 2026-07-22, same day) —
  no Plex log activity from today shows any removal events, only normal scan/analysis noise.
  Since Plex is now removed entirely, this can never be root-caused further. **This closes the
  loop on what was learned, not the underlying uncertainty**: the original Radarr/Sonarr-side
  file loss still has no confirmed cause, only this newly-found Plex-side symptom of it.
- **Sonarr has a pagination-safe `missing-aired` endpoint that exists but has zero UI wiring and
  has never been tested against this library's real scale (~300k episode records).** Don't assume
  it's a validated, ready-to-use path without treating that first real invocation as a genuine
  test, not a known-safe operation.
- **Recyclarr's custom-format/quality-profile sync was completely broken since the day it was
  added, not a regression** — its compose service block never passed `RADARR_API_KEY`/
  `SONARR_API_KEY` into the container despite `config/recyclarr/recyclarr.yml`'s `!env_var`
  directives requiring them; every scheduled run failed at the config-parse stage with an
  undefined-variable error, confirmed live via its own logs going back to at least 2026-07-14.
  Separately, both apps' sole quality profile had drifted to being named "Any" at some point
  while `recyclarr.yml` (and this file, until fixed alongside it) still assumed "Unlimited" -
  Recyclarr was silently unable to find a profile to score into even after the env-var fix,
  until the live profile was renamed back via API. Fixed together; if a similar "sync completes
  with a Config Diagnostics warning" symptom ever recurs, check both layers (env vars actually
  reaching the container, and the profile name Recyclarr expects actually existing) rather than
  assuming just one explains it.
- **Torrent and debrid support was removed entirely in v11.0.0, by explicit request** — six
  services gone (`decypharr`, `decypharr-alldebrid`, `zurg`, `rclone-alldebrid`, `zilean`,
  `zilean-postgres`), plus `byparr` once confirmed no remaining Usenet indexer referenced it.
  All 49 enabled torrent indexers plus the `Zilean` Torznab entry disabled then deleted from
  Prowlarr, in that order. **A real, live consequence found mid-execution, not anticipated in
  planning**: Zurg and Decypharr never downloaded real bytes, they symlinked into a FUSE mount
  streaming directly from Real-Debrid/AllDebrid, so stopping those containers immediately
  broke playback for the 616 files (3.65% of the library) sourced through them — surfaced and
  confirmed with the user mid-removal rather than assumed safe, then accepted as a known
  consequence. Recreating `nzbdav-rclone` and its now-five mount-dependent containers in the
  same batch reproduced the FUSE stale-mount bug this file already documents for a single
  dependent — confirmed live, not just theorized; `MOUNT_DEPENDENTS` grew from `{"radarr"}` to
  all five to match. See README's History `[11.0.0]` for the full removal, including every
  file/endpoint/CLI-command touched.
- **Plex was removed entirely 2026-07-22, replaced by Jellyfin** (later reverted the same day,
  see the dedicated section above — Jellyfin no longer exists in this stack at all, so the
  API-route/plugin/fish-function specifics of that migration are omitted here as dead detail).
  A few things worth remembering regardless of Jellyfin's removal: **Kometa cannot talk to
  Jellyfin at all** — confirmed against `kometa-team/kometa`'s own `config-schema.json` (no
  `jellyfin`/`emby` property, only `plex`); several blog posts claiming otherwise are wrong,
  real support is an open unimplemented Jellyfin feature request. Jellyfin's compose block was
  initially deployed missing the `/mnt/nzbdav` mount, reproducing the same "root folder is
  100% symlinks, dangling inside a container missing the FUSE mount" bug class documented
  elsewhere in this file (Stash's original deploy hit the identical bug). Jellyfin was briefly
  moved to `network_mode: host` for UDP client-discovery broadcast (bridge-mode port-mapping
  doesn't carry broadcast traffic), then deliberately reverted back to bridge + published port
  at the user's request, accepting that mobile-app LAN auto-discovery doesn't work.
  **`jellystat`/`jellystat-db` (`postgres:18.1`) crash-looped on first start** because
  `postgres:18+` manages its own version subdirectory under a single `/var/lib/postgresql`
  mount now, not the older `.../data` convention — fixed by mounting the parent directly.
  **NzbDAV's STRM import mode was evaluated and deliberately rejected**: a real, working
  Emby/Jellyfin-only feature (writes a `.strm` text file pointing back at NzbDAV's own `/view/`
  endpoint instead of a symlink), not adopted because it's a global NzbDAV setting that would
  also change what Radarr/Sonarr's import pipeline receives, and Radarr has a documented,
  unresolved grab-import-delete loop specific to `.strm` files from a SABnzbd-compatible client
  (`Radarr/Radarr#11435`) plus a broken `ffprobe`-based media-info read against the `.strm`
  text file itself. Revisit only if that Radarr issue is confirmed fixed in a real release.

## Control-panel gotchas beyond restart ordering and CSRF

- **Cleanuparr's instance-check in `control-panel/app.py` bypasses Cleanuparr's own HTTP API
  entirely and reads its SQLite DB file directly** — `/api/instances` on Cleanuparr itself
  returns an HTML shell, not JSON, so there was no API-level way to get this data.
- **`/api/version` depends on an exact regex match against a specific line format in
  `README.md`.** This compounds the single-file bind-mount staleness issue already noted above —
  reformatting that line in README *or* editing README without a `--force-recreate` on
  `control-panel` can both silently break version reporting.
- **`claude-review` CI (`.github/workflows/claude-code-review.yml`) failed on every real
  (non-Dependabot) PR from at least 2026-07-15 through 2026-07-23 — fixed same day.** Root
  cause: `401 Invalid bearer token` — the `CLAUDE_CODE_OAUTH_TOKEN` repo secret itself was
  expired/invalid (`gh secret list` showed it last set 2026-07-09), not a permissions or
  prompt problem. Confirmed by temporarily adding `show_full_output: true` to the workflow
  (past the SDK's default output redaction) and running it via a genuine trigger PR — a
  workflow-file change on the *same* PR gets skipped outright by GitHub's own "must match
  default branch" validation, so seeing the real error needed the flag merged to `main` first,
  then a separate PR to trigger a real run; flag reverted after use. **Fixed by running
  `/install-github-app` from a local `claude` session**, which re-authorized against the
  user's own Claude account and rewrote `CLAUDE_CODE_OAUTH_TOKEN` (`gh secret list` timestamp
  moved to the moment the command completed) — this step needs the account owner's own OAuth
  authorization, it isn't fixable by editing files in this repo. **Verified working, not just
  configured**: an empty-commit throwaway PR (#28, closed after use, no branch left behind)
  completed a real `claude-review` run post-refresh (~1 minute runtime, matching a genuine
  Claude Code SDK invocation, not the ~15s instant-skip pattern the validation-guard produces)
  with no `is_error`. One retry was needed — the very first post-refresh attempt still hit the
  same "must match default branch" skip, apparently a brief propagation lag right after the
  workflow file's own most recent change landed on `main`; a second empty-commit push a minute
  later ran for real. No branch protection is configured on this repo, so none of this ever
  blocked a merge — it was a broken CI signal, now a working one.
- **`/install-github-app` doesn't just refresh `CLAUDE_CODE_OAUTH_TOKEN` — it also silently
  overwrites both `.github/workflows/claude-code-review.yml` and `claude.yml` with its own
  current upstream template, auto-committing and auto-merging the diff (PR #27, same session
  as the token refresh above) without asking.** Confirmed real, not hypothetical: that sync
  deleted the Dependabot-skip guard (`if: github.actor != 'dependabot[bot]'` plus
  `allowed_bots: 'dependabot[bot]'`) from `claude-code-review.yml` — the exact fix already in
  place for a previously-documented, real bug (GitHub withholds repo secrets from
  Dependabot-triggered `pull_request` runs, so this job fails every time without the skip) —
  and downgraded `actions/checkout@v7` → `v4` in both files. Both restored by hand the same
  session. **Any future run of `/install-github-app` needs its resulting diff reviewed before
  trusting it**, not just the secret's refreshed timestamp — it will silently re-strip this
  guard again if the upstream template hasn't changed to include an equivalent by then.

## Deliberate architecture decisions with non-obvious reasons

- **A full Traefik + Authelia + CrowdSec stack (real 2FA, real CrowdSec ban behavior) was built
  and verified working, then deliberately reverted** in favor of the current LAN-only,
  CSRF/Origin-validated model — the full recipe is preserved in README's History section if this
  is ever revisited, so don't rebuild it from scratch without checking there first.
- **Sonarr's Remote Path Mapping for the AllDebrid `decypharr-alldebrid` instance (the one
  deliberate exception to this stack's normal "no Remote Path Mappings" convention) was
  removed along with Decypharr itself in v11.0.0** — this stack has no Remote Path Mappings
  at all now, no exceptions.

## Recurring BearMount FUSE read hangs during import-time ffprobe, 2026-07-26

**UPDATE, same day, later in the session: root-caused and a local fix deployed — see the
"Root cause found and fixed" subsection below before reading the rest of this section, which
records the investigation that led there.**

**Not fully root-caused — recurred 8+ times in one ~3hr session, always a different file.**
A read against `/mnt/bearmount-import/...` (Radarr/Sonarr's own `ffprobe -probesize 50000000`
validation call, not the Plex-facing `/mnt/bearmount` playback path) permanently wedges in
D-state. Zero NNTP connections open during the hang (`ss -tn` on the bearmount container),
zero log output from bearmount for the affected file, bearmount's own CPU is idle — ruled out
provider contention, worker saturation, and health-check locking. BearMount's own dashboard
shows the download as `STALLED`, `0 B/s`, stuck at a fixed ~960KB offset regardless of file
size. The file's own BearMount health record shows `healthy` from its last *sampled* check —
only the full/large sequential read hangs, not small reads. No fix applied this session beyond
the standing per-incident recipe below; this is a live, open problem, not resolved.

**Recovery** (same every time): blocklist the specific queue item in Radarr/Sonarr
(`DELETE /api/v3/queue/{id}?removeFromClient=true&blocklist=true`), then `docker compose
restart <radarr|sonarr>`. If the container's own PID1 gets wedged waiting on the D-state child
(`docker restart`/`docker kill` both fail with "did not receive an exit event") — confirmed
happened 2x this session — bearmount itself needs `--force-recreate` to release the handle,
followed by the full dependent cascade + verification (see
[[feedback_bearmount_recreate_verification]]). A `--force-recreate` of bearmount right after a
lazy host unmount can itself transiently fail with `"user has no write access to mountpoint"`
— retry the recreate once, don't assume a real permissions regression from a single failure.

**Investigated, not confirmed as root cause**: upstream `javi11/altmount` has two closed issues
with near-identical symptoms — #647 ("FUSE multi-segment sequential reads deadlock... single
reads OK"), fixed 2026-06-03 by commit `347f0e7c19414e3d9191e5d75fa7e18e4d01aea5`; #426
("Goroutine leak in UsenetReader.Close()... accumulates as files are opened and closed, e.g.
Sonarr importing files that then fail"), fixed 2026-03-22. Our running image was built
2026-07-24 (fork revision `682e224b18...`), well after both fix dates, so both *should* already
be included. `git merge-base --is-ancestor 347f0e7c19... HEAD` reported **not an ancestor** of
either the fork's HEAD or `upstream/main` — but this check is not fully trusted (GitHub's
"referenced" timeline event doesn't reliably map to the real merge commit if it landed via
squash-merge), so treat as a lead to verify manually, not a confirmed finding. Fork
(`WhispersOfJ/bearmount`) has issues disabled, so nothing was filed anywhere — this section is
the only record. If this recurs again, re-check whether `347f0e7c19...` / equivalent fix is
actually present before re-doing this whole investigation from scratch.

### Root cause found and fixed, same day

Read the fork's own source directly (`internal/usenet/usenet_reader.go`) rather than continuing
to guess from symptoms. Real bug, independent of the two upstream issues above (neither's fix
commit touches this code path):

`UsenetReader`'s download-scheduling loop (`downloadManager`) throttles how far ahead it
prefetches using a `sync.Cond` (`b.cond`, tied to `b.mu`) — it holds `b.mu`, checks
`ahead := b.nextToDownload - b.rg.GetCurrentIndex()`, and calls `b.cond.Wait()` if over the
prefetch limit. The wakeup call sites — `Read()`'s post-`rg.Next()` signal, and each download
goroutine's completion signal — both called `b.cond.Signal()` **without holding `b.mu`**.
Critically, `segmentRange` (`b.rg`) has its **own separate `sync.RWMutex`**, so the state
`downloadManager` checks isn't actually guarded by the same lock the condition variable is tied
to. Race: `downloadManager` reads a stale `currentRead`, decides to wait, and is about to call
`Wait()` — but `Read()` concurrently advances the index and signals in that exact gap.
`sync.Cond` does not queue signals; with no goroutine yet parked in `Wait()`, the signal is
silently lost. `downloadManager` then calls `Wait()` a moment later and blocks forever — no more
segments get scheduled, `Read()`'s next call blocks on data that will never arrive. Zero logs,
zero new NNTP connections, permanent hang — matches every symptom logged above exactly. Same
*class* of bug as upstream's already-fixed #426 (`sync.Cond` lost-wakeup), different, still-live
call site. Timing-dependent, which is why it only ever surfaced under sustained concurrent read
load, never at light usage.

**Fix**: wrap both `Signal()` calls in `b.mu.Lock()/Unlock()`. Verified: builds clean
(`go build ./internal/usenet/...`), full package test suite passes with `-race`
(`go test -race ./internal/usenet/...`, including the pre-existing sequential/prefetch/storm
tests written for this exact area).

**Deployed same session** as a temporary local image, per explicit instruction to skip the
normal queue-empty check for this one recreate: `bearmount-local-fix:cond-signal-lock` (built
from the fork's `rebrand/bearmount` branch, commit `a02afbd8...`, plus this one-file patch).
`docker-compose.yml`'s `bearmount` service is pinned to it with a dated comment — **revert to
`ghcr.io/whispersofj/bearmount:dev` once this lands upstream in a real tagged release**, don't
leave this pinned forever (same policy as the earlier playback-repair local-fix image). No PR
opened against the fork (issues/discussions are disabled there) — if the user wants a paper
trail, the patch needs to go up as a PR against `upstream/main`/`javi11/altmount` directly, not
filed as an issue.

**Post-deploy validation: the fix did NOT resolve the hang.** Confirmed by direct observation —
the same D-state `ffprobe` hang recurred (`The Legend Of Ochi` REMUX) on `bearmount:
bearmount-local-fix:cond-signal-lock` itself, ~6 minutes after deploy, `docker inspect`-confirmed
running that exact image. The `b.cond` lost-wakeup race in `downloadManager`/`Read()` is a real,
verified bug (compiles, passes `-race`) and worth fixing regardless, but **it is not the sole
cause of the recurring hangs — treat as one contributing bug, not the fix.** Checked
`segment.go`'s own data-readiness signaling (`dataReady chan struct{}`, closed exactly-once via
`sync.Once`) as the other half of the wait chain — that mechanism is channel-close-based, not
`sync.Cond`-based, so it's structurally immune to the same lost-wakeup class of bug; ruled out.
Remaining candidates, not yet investigated: something in the FUSE layer itself (`hanwen`
backend) upstream of `UsenetReader`, or a different lock/wait pattern elsewhere in the read
path not yet read. Don't claim this is solved next time it's touched — it isn't.

### Second fix: unbounded import-connection-budget wait, deployed as `budget-timeout`

Continued digging per explicit request past the first fix. Read `internal/fuse/backend/hanwen/handle.go`
and `internal/fuse/backend/asyncbuffer.go` (the FUSE-facing read-ahead buffer) — both are
well-engineered; every `cond.Signal()`/`Broadcast()` in `asyncbuffer.go` is correctly called
under its own lock, unlike the bug in `usenet_reader.go`. Not the second cause, but it pointed
at the real one: `AsyncReadBuffer.fill()`'s blocking source read has no timeout of its own — if
`UsenetReader.Read()` never returns, nothing here can rescue it.

Traced further into the vendored `github.com/javi11/nntppool` client (`nntp.go`). Found a real
bug there too: `tryGroup`'s per-attempt timer is a one-shot `time.Timer` — once it fires it can
never fire again (the code's own comment says so), but the "reader already committed" branch
falls through and keeps looping past that point with no working timeout for a stream that stalls
*after* starting. Traced whether `usenet_reader.go`'s own 15s `attemptCtx` still rescues this via
context propagation (`reqCtx.Done()` is one of `tryGroup`'s select cases) — it does, so this
alone doesn't explain multi-*minute* hangs; a genuine defense-in-depth gap, but not deployed as
a fix this session (would require instrumenting the vendored library's actual socket-read loop,
never located — larger, riskier surgery than the time available justified; noted for later).

**The actual confirmed mechanism**: `UsenetReader.downloadSegmentWithRetry`'s
`b.budget.AcquireImportConnection(ctx)` call (the global import-connection semaphore) runs
*before* any per-attempt timeout exists, using the reader's own long-lived context — genuinely
unbounded. Under heavy concurrent import load (both apps running large ffprobe batches
simultaneously — exactly this stack's conditions), if any current budget-holder is itself slow
(amplified by the nntppool timer gap above), waiters queue behind it with no cap, and a waiter
near the back can legitimately wait minutes — indistinguishable from a permanent hang, and why a
container restart "fixes" it (discards the queue rather than waiting it out).

**Fix**: wrapped the `Acquire` call in a bounded 5-minute `context.WithTimeout`, plus a warning
log on timeout (this path previously logged nothing at all, which is why the whole investigation
took hours). 5 minutes is deliberately generous — the original unbounded design was intentional
("queue wait never burns the fetch deadline"), so this preserves normal heavy-contention
behavior and only fires for genuinely pathological queueing.

Verified: clean build, full `internal/usenet` suite passes with `-race`. Deployed as
`bearmount-local-fix:budget-timeout`, then held clean for 12+ consecutive 1-minute health checks
under continued real concurrent import load — meaningfully more validation than fix #1 alone
ever got (that one failed within one check-in cycle under the same conditions).

### PR + issue filed upstream, repo renamed back to AltMount, 2026-07-26

Both write-ups updated with the complete, honest history (including that fix #1 alone didn't
work) and filed for real:
- Issue: https://github.com/javi11/altmount/issues/805
- PR: https://github.com/javi11/altmount/pull/806 (from `WhispersOfJ:debrand/altmount-clean`)

Then, per explicit user request, went further than just a side-branch de-brand:

1. Confirmed the rebrand really was one isolated commit (`a02afbd8`, 367 files) at the tip of
   `rebrand/bearmount`, nothing built on top — branched from the commit before it
   (`debrand/altmount-clean`), reapplied both fixes (clean auto-merge, the rebrand never touched
   `usenet_reader.go`), verified zero leftover branding and a full clean `go build ./...`.
2. **Renamed the GitHub repo**: `WhispersOfJ/bearmount` → `WhispersOfJ/altmount`
   (`gh repo rename altmount --repo WhispersOfJ/bearmount -y`). GitHub redirects the old URL.
   Confirmed via API this repo genuinely is a real GitHub-level fork of `javi11/altmount`
   (`fork: true, parent: javi11/altmount`) — an earlier check in this same session had wrongly
   concluded it wasn't; that was a mistake, corrected here.
3. **Set `debrand/altmount-clean` as the repo's new default branch** (`gh api -X PATCH
   repos/WhispersOfJ/altmount --field default_branch=...`) rather than force-pushing over the
   existing `main`/former-`rebrand/bearmount` history — non-destructive, the old branded history
   still exists as a non-default branch if ever needed again.
4. Built a fresh image from this de-branded+fixed state: `altmount-local-fix:budget-timeout`
   (binary itself is now literally named `altmount`, confirmed via the Dockerfile's `chmod +x
   /app/altmount` build step). `docker-compose.yml`'s `bearmount` service `image:` updated to
   point at it — **this stack's own service/container name stays `bearmount`**, that's this
   repo's own internal naming convention, unrelated to and unaffected by the upstream project's
   identity.
5. Deployed, full cascade + verification per the standing rule, confirmed clean.

**Local scratch clone note**: the local `rebrand/bearmount` git branch was deleted from the
scratch clone (not from GitHub — the remote branch still exists under whatever it's called post
default-branch-change) once its content was confirmed carried forward into
`debrand/altmount-clean`. If a future session needs the pre-fix branded history, it's still on
GitHub, just no longer the default branch.

### Third fix: unbounded poolGetter wait, deployed as `poolgetter-timeout`, 2026-07-26

Same-day recurrence on `budget-timeout`: `radarr` PID 1080 (`ffprobe` on the Inception 2010
REMUX) hung in D-state 18+ minutes, well past the deployed 5-minute budget-Acquire bound, with
`bearmount` logs showing zero warning/error for that file (only Debug-level activity, actively
serving other files fine) and zero active NNTP connections (`ss -tn | grep :563` → 0). Confirmed
the budget-Acquire and cond-signal fixes were genuinely still in the running image
(`debrand/altmount-clean` at `7d6e113c`) before looking further, so this was a third, distinct
gap, not a regression of either earlier fix.

Traced every wait in `downloadSegmentWithRetry` (`internal/usenet/usenet_reader.go`): each fetch
attempt is bounded (15s `attemptCtx`, `retry.Attempts(2)`), the budget Acquire is bounded (5min),
and the per-segment data-ready wait in `segment.go` is `select`-guarded on `ctx.Done()`. The one
remaining unbounded call is `b.poolGetter()` (→ `pool.manager.GetPool()`), which takes the pool
manager's `RWMutex` read-side — normally fast, but can block for as long as a concurrent
`SetProviders` call holds the write lock (provider health-checks and pool teardown/setup run
under that lock with no timeout of their own). **Not fully confirmed as this specific hang's
mechanism** — other files continued processing throughout the window, which argues against a
global writer-lock stall (that would block every `GetPool()` caller, not just one file) — but it
was the one structurally unbounded piece left, so patched defensively per explicit instruction
rather than left as a known gap like the `nntppool` `tryGroup` one-shot-timer issue above still
is.

**Fix**: wrapped `b.poolGetter()` in a goroutine + `select` with a 30s timeout (the function
takes no `context.Context` parameter, so it can't be bounded directly) and a warning log on
timeout. Verified: `go build ./...` clean after `go mod vendor` (this checkout's vendor dir was
stale — same "inconsistent vendoring" issue seen earlier this session on a different worktree),
`go vet` clean, `go test -race ./internal/usenet/...` passing. Committed to
`debrand/altmount-clean` (`120b20a2`). Built and deployed as `altmount-local-fix:poolgetter-timeout`.

**Deploy hit the documented stale-bind-mount landmine** (see "Plex stale bind-mount" entry): the
recreate cascade used `docker compose restart` for the dependents first, which reuses the
existing container's mount namespace and does *not* pick up bearmount's fresh FUSE mount —
confirmed via `docker exec <dependent> ls /mnt/bearmount` → `Transport endpoint is not
connected`/`Socket not connected` on every one of radarr/sonarr/plex/unpackerr/cleanuparr despite
all showing Docker-healthy. Also made one mistake fixing it: ran `sudo umount -l /mnt/bearmount`
on the host to clear what looked like a stale reference, but bearmount's *own* recreate had
already succeeded by that point — the lazy unmount tore down bearmount's brand-new working mount
too (rshared propagation is bidirectional), which then made the *next* recreate attempt fail with
`fusermount3: user has no write access to mountpoint` (a transient state right after an unmount,
not a real permissions problem — `/mnt/bearmount` was correctly `1000:1000` throughout). Recovered
by force-recreating bearmount once more (clean "FUSE filesystem mounted and ready" log line) and
then using `docker compose up -d --force-recreate` (not `restart`) for all five dependents.
**Lesson: prefer `--force-recreate` over `restart` for the whole cascade by default** — `restart`
looking sufficient here was the initial mistake that triggered the unnecessary `umount -l`
detour. Post-recreate verification (mount readable from inside each dependent, zero D-state, zero
`bearmount-import` mount-table leak) passed clean on the second attempt.

`docker-compose.yml`'s `bearmount` service now points at `altmount-local-fix:poolgetter-timeout`.
Same revert-once-upstream-lands caveat as the two fixes before it.

**Recurred same day, ~10 minutes after this deploy, on a different file** (`Minions.2015` REMUX,
~53GB, `radarr` PID 284) — confirms the third fix did not resolve the underlying class either.
Same fingerprint as every prior occurrence: zero NNTP connections, zero log activity, but this
time got harder evidence before restarting:

- Host-side `/proc/<pid>/io` sampled twice 10s apart showed **identical** `rchar`/`syscr` —
  confirmed genuinely stalled, not just slow.
- Host-side kernel stack (`sudo cat /proc/<pid>/stack`): `filemap_read` → `folio_wait_bit_common`
  → blocked in the `read()` syscall on a page-cache lock. For a FUSE mount this means the kernel
  is still waiting on bearmount's userspace daemon to answer the read request — consistent with
  everything assumed so far, now confirmed at the kernel level rather than inferred from symptoms.
  Distinguishes it from a real disk/network stall: this is a userspace FUSE-response hang.
- Ran well past all three now-bounded timeouts (30s poolGetter, 5min budget, 15s×2 fetch
  attempts) with no warning logged for any of them — the stuck point is upstream of
  `downloadSegmentWithRetry` entirely (most likely `downloadManager`'s prefetch-scheduling loop,
  or the FUSE `hanwen` backend layer — both still flagged "not yet investigated" above).
- `bearmount` at 0.03% CPU throughout — not spin-looping, genuinely parked.
- **Root cause of the "zero log activity" mystery, resolved**: `config/bearmount/config.yaml`'s
  `log.level` was `info` the whole time; every per-segment/per-fetch log line added by all three
  fixes today (`slog.DebugContext`) is `Debug`-level, so none of them were ever visible — this
  wasn't evidence the hang bypassed the instrumented code, it was evidence the logs were filtered
  out. **Set `log.level: debug`** and redeployed so the *next* occurrence produces real per-segment
  timing instead of requiring kernel-level forensics again. Revert to `info` once the actual root
  cause is found and fixed — debug logging at this volume isn't meant to run long-term.
- Redeploy hit the stale-bind-mount landmine a second time, worse: `--force-recreate bearmount`
  alone (before touching any dependent) somehow resulted in bearmount itself being torn down and
  recreated *twice* within ~10 seconds (`docker inspect .State.StartedAt` confirmed two distinct
  container-create timestamps from one `--force-recreate bearmount` command plus one
  `--force-recreate` of the five dependents run right after) — the second internal recreate's own
  FUSE auto-mount failed (`fusermount3: user has no write access to mountpoint`, the same
  transient-post-unmount state as the first `poolgetter-timeout` deploy above), leaving both the
  host mount and the container itself broken (`docker compose up -d --force-recreate bearmount`
  then failed outright with `invalid mount config for type "bind": stat /mnt/bearmount: transport
  endpoint is not connected`). Exact trigger for the double-recreate not fully diagnosed — worth
  watching for on the next deploy. Recovered with the same `sudo umount -l /mnt/bearmount` +
  recreate recipe, this time adding an explicit settle/verify pause (host `ls /mnt/bearmount`
  succeeding) between recreating bearmount and recreating any dependent, which is what finally
  held clean. **Add this pause to the standard recreate procedure going forward, not just the
  five-dependent cascade order already documented.**

### Fourth round: pure diagnostics, deployed as `diag-instrumentation`, 2026-07-26

Same hang recurred a third time within the hour, same file (`Minions.2015` REMUX, retried by
radarr after the earlier kill), this time with `log.level: debug` live — and still zero
segment-level log output, even at Debug. Root cause of that silence: the stuck goroutine never
reaches `downloadSegmentWithRetry` at all (none of today's three fixes live inside functions this
hang ever calls), and the two layers upstream of it — `UsenetReader.downloadManager`'s
prefetch-throttle `cond.Wait()` (`internal/usenet/usenet_reader.go`) and `AsyncReadBuffer.fill()`'s
blocking source read plus `ReadAtContext`'s two frontier-wait loops
(`internal/fuse/backend/asyncbuffer.go`) — had essentially no logging at all. Both are genuinely
unbounded `sync.Cond.Wait()` calls with no context-cancellation escape while parked (`ctx.Err()`
is only rechecked *after* a wakeup, never interrupts a `Wait()` itself) — same underlying hazard
class as the already-fixed `cond.Signal()` lost-wakeup bug, just not yet confirmed as this
specific hang's mechanism.

**Deployed as pure diagnostics, no behavior change**: warn-on-slow (>10s) + debug logging at all
four candidate points — the prefetch wait, the fill goroutine's source read, and both
`ReadAtContext` frontier waits — committed to `debrand/altmount-clean` (`73840e40`), built and
deployed as `altmount-local-fix:diag-instrumentation`. Verified: `go build ./...`,
`go vet ./...`, `go test -race ./...` all clean repo-wide. Recreate cascade held clean this time
(mount-settle pause + `--force-recreate` throughout, no `restart`, no incidental host
`umount -l` needed).

**Next occurrence should finally pinpoint the actual stuck line** via one of these four new log
lines. Do not add a fifth speculative timeout fix without that evidence — three blind fixes today
already missed the real mechanism each time.

**Occurrence #4, same session, root cause finally captured live** — same file (`Minions.2015`
REMUX) hung a second time under the `diag-instrumentation` image. The new logs caught it exactly:

```
next_to_download=46 current_read=1 in_flight=45 → ... → in_flight=0 (all scheduled downloads
completed) → current_read never advances past 1 → downloadManager stops logging entirely
(no more Wait() wakeups — nothing left in flight to ever Signal() it again)
```

All 45 prefetched segments downloaded successfully (`in_flight` drained cleanly to 0), but the
**reader's own consumption position (`b.rg.GetCurrentIndex()`) never advanced past segment 1**,
despite segments 1-45 being fully downloaded and sitting ready. `downloadManager` then blocks
forever on `b.cond.Wait()` waiting for `current_read` to advance — but nothing is left in flight
to ever call `Signal()` again, and even if something did, `ctx.Err()` is only rechecked *after* a
wakeup (the known `sync.Cond` limitation flagged in the diagnostic commit). This means the actual
stall is **downstream of the download layer entirely** — the reader consuming already-available
segment 1 never happens, which points at the FUSE-facing `AsyncReadBuffer`/`Handle.Read` chain,
or `segment.Reader()`'s hand-off from a completed download to a waiting reader. Not yet fixed —
this is the first real, non-speculative lead of the day and should be the actual starting point
for the next fix, not another guess.

**Operational resolution for this occurrence**: per explicit request, captured the above evidence
from the live logs, then removed+blocklisted the release via Radarr's queue API
(`DELETE /api/v3/queue/{id}?removeFromClient=true&blocklist=true&skipRedownload=false`) so Radarr
grabs a different release instead of retrying the same stuck one. The already-open FUSE handle
(D-state `ffprobe`) did not clear on its own after the blocklist — removing a download-client
reference doesn't touch an already-issued FUSE read — so one more `--force-recreate bearmount` +
full dependent cascade was needed to actually release it. **The double-recreate mystery recurred
a third time** on the first attempt (bearmount tore itself down and remounted twice within ~12s
of one `--force-recreate bearmount` call, second attempt's auto-mount failing with the same
transient `fusermount3: user has no write access` state) — still not diagnosed (a `docker events`
capture attempt during the repro hung/timed out rather than yielding an answer). Recovered with
the by-now-standard `sudo umount -l /mnt/bearmount` + recreate + settle-pause-before-dependents
recipe; held clean on the second attempt with a longer (15s) settle pause. **This double-recreate
behavior is real and reproducible on `--force-recreate bearmount` alone — worth a dedicated
investigation next time there's headroom, independent of the read-hang bug above.**

**Occurrence #5, ~15 minutes later, different file — confirms the pattern is reproducible, not a
one-off.** `The.Creator.2023` REMUX (~56.5GB, also in the tens-of-GB REMUX class like Minions and
the original Inception hang), `radarr` PID 869, hit during a large concurrent bulk manual-import
run (`stack-arr-import-all radarr` / `POST /api/arr/radarr/manual-import-all`, ~59 queue items).
Identical log signature to occurrence #4: `current_read` stalls at 6 while `next_to_download`
reaches 51 and `in_flight` drains cleanly to 0, then `downloadManager` stops logging entirely —
same "all segments downloaded, reader consumption position never advances, nothing left to
Signal()" deadlock. Two independent files, same exact mechanism — treat this as confirmed
reproducible, not coincidental. Strengthens the lead from occurrence #4: the bug is in the
reader-side hand-off (`AsyncReadBuffer`/`Handle.Read`/`segment.Reader()`), not anywhere in the
download-scheduling or NNTP-fetch code three fixes were already spent on today.

**Occurrence #6, ~10 minutes later — the original file from this morning, `Inception.2010`
REMUX, hung again**, `radarr` PID 940. Now 3-for-3 with the identical signature:
`current_read` stalls (this time at 0 — never advances even once, vs. 1 for Minions and 6 for
The Creator) while `next_to_download=45` and `in_flight` drains cleanly to 0. The varying stall
point (0, 1, 6) rules out any specific segment index being special — this is a structural hazard
in the reader-consumption hand-off that can trigger at essentially any point once it fires, not
tied to one segment's content. Common thread across all three: every file is a 50+GB REMUX, and
every hang was triggered by an `ffprobe -probesize 50000000` invocation specifically — worth
checking whether the large `probesize` read pattern (likely a big non-sequential seek early in
the file) is what demotes/promotes `AsyncReadBuffer` in a way that exposes this hazard, versus
Plex's more sequential streaming reads never triggering it in this session's observations.

### Fifth fix attempt, `readerctx-timeout` — real improvement, not a full fix, 2026-07-26

Traced the exact stuck call: `UsenetReader.Read()`'s `s.GetReaderContext(b.ctx)` for the segment
at `current_read`. `GetReaderContext`'s wait is a `select` on the segment's `dataReady` channel
close (immune to the `sync.Cond` lost-wakeup class already fixed elsewhere), but `b.ctx` is the
file handle's long-lived context — never cancels in practice, making its `ctx.Done()` escape
hatch useless here. Bounded it to 2 minutes via a derived `context.WithTimeout`. Verified safe: a
context-timeout return doesn't poison the segment (`readerReady` stays false), so a later retry
can still succeed. Committed (`eb491cf5` on `debrand/altmount-clean`, after a rebase to strip an
accidentally-vendored Slack webhook secret that GitHub's push protection caught — see commit
history, nothing of ours was exposed, the secret belonged to a vendored dependency's own CI
config), pushed upstream, deployed as `altmount-local-fix:readerctx-timeout`.

**Post-deploy: real but partial improvement, not a fix.** `Death.on.the.Nile.2022` REMUX hung
~10 minutes after deploy. First time ever, `current_read` actually advanced (0→1) before
stalling — every prior occurrence froze at its very first segment. But once stalled at segment 1,
it stayed D-state for 7+ minutes with **zero** `GetReaderContext took unusually long` warnings —
meaning the 2-minute bound never fired because this stall isn't inside `GetReaderContext` at all
for this occurrence. `downloadManager` logs confirm it's behaving correctly (parked in
`cond.Wait()`, throttled since `current_read` isn't advancing — not itself stuck). Confirmed via
log absence of any remux/nested/encryption path, so `mvf.reader` is the plain `UsenetReader`
directly. **The real conclusion: whatever is supposed to call `UsenetReader.Read()` again after
segment 0 completed never does** — the block is upstream of everywhere fixed today, most likely
`MetadataVirtualFile.mu` contention or something in the FUSE dispatch layer above
`ReadAtContext`, neither instrumented yet. **Do not treat `readerctx-timeout` as resolving this
hang class** — it's a real, verified improvement (one confirmed case of progress that wouldn't
have happened before), but a fifth fix/instrumentation round targeting `mvf.mu` acquisition and
the FUSE-level read dispatch is still needed.

### Sixth and seventh instrumentation rounds — four independent points all ruled out, 2026-07-26

Added `mvf-lock-diag` (measures the `mvf.mu.Lock()` acquisition wait itself in `ReadAtContext`,
not just work done after acquiring it — `Close()`'s own comment already documents this lock "can
be held for the full segment-download latency") and, after that also stayed silent through a
`Death.on.the.Nile` hang, `ephemeral-diag` (instruments `readFullContext`, which backs a
completely separate "ephemeral" reader branch — `createReaderAtOffset` + a fresh one-off reader
per call — that `ffprobe`'s non-sequential probing very plausibly hits instead of the "shared"
sequential-offset branch every earlier fix targeted).

**Result: a fourth confirmed occurrence (`The.Creator.2023`, new release) stayed D-state 6+
minutes with *zero* warnings from all four independently-instrumented points**
(`GetReaderContext`, the shared-reader `Read` loop, `mvf.mu` acquisition, `readFullContext`'s
ephemeral wait) — while `downloadManager`'s own logs confirm the same signature as every prior
occurrence (`current_read` frozen, `in_flight` drained to 0). This is a strong negative result:
the actual stuck code is not in any of the four candidate waits examined across five rounds of
instrumentation today. Remaining unexamined territory: the `hanwen/go-fuse` library's own request
dispatch/goroutine-pool layer (upstream of `Handle.Read`, never touched today), or something at
the kernel/FUSE-protocol boundary itself. Getting further needs either a real Go goroutine dump
(no pprof endpoint currently wired up — see the 2026-07-26 poolgetter-timeout entry above for why
that wasn't done live) or reading `go-fuse`'s own source, neither attempted yet.

**Operationally, the blocklist + recreate playbook (documented per-occurrence above) remains the
reliable mitigation** regardless of root cause: identify the file via `cmdline`, confirm the
50GB+ REMUX / `ffprobe -probesize` pattern, blocklist via Radarr's queue API, then the standard
bearmount recreate + cascade + verification procedure. Six same-day occurrences all cleared this
way with zero data loss or lasting stack damage.

## BearMount replaced entirely by nzbdav/nzbdav, 2026-07-28

**This was a "nuclear option" decision, not a bug found in BearMount itself.** While diagnosing
a live issue that same evening (every RuPaul's Drag Race grab failing bearmount's fast-fail
segment check identically - "no regular files were successfully processed (all files failed
validation)" - regardless of release/uploader, which pointed at something systemic rather than
individually-bad releases), the user chose to fully replace the download client with
`nzbdav/nzbdav` rather than keep debugging BearMount. The actual root cause of that original
issue turned out to be provider-side (the ThunderNews account was mid-resync at the time,
causing an intermittent NNTP login hang - confirmed independently via a raw NNTP
`AUTHINFO USER`/`PASS` test from the host, no app in the loop at all) - this migration doesn't
fix or relate to that; the same single ThunderNews provider carries over unchanged.

**What `nzbdav/nzbdav` actually is**: a maintained "super-fork" of `nzbdav-dev/nzbdav` (confirmed
via `gh api` - `fork: true`, description literally says "a super-fork of related projects to the
OG nzbdav-dev version"). Not the same codebase as BearMount's lineage (`javi11/altmount`) at
all - a completely different implementation (.NET/C# backend + React frontend, vs. BearMount's
single Go binary).

**Key architectural difference, surfaced during planning and accepted knowingly**: NzbDAV has
**no built-in mount at all** - it's a pure WebDAV server. Getting real files to Plex/Sonarr/
Radarr requires an external `rclone/rclone` sidecar container (`nzbdav_rclone`) doing
`rclone mount` against NzbDAV's WebDAV endpoint. This is a **net increase in moving parts**
versus BearMount (one container owning its own embedded FUSE mount, vs. two now) - the same
architecture (`rclone.mount_enabled`) BearMount itself had explicitly disabled in favor of
native FUSE. Accepted as a known tradeoff, not an oversight - the alternative (STRM files, no
FUSE/rclone needed at all) was also considered and rejected in favor of staying closer to the
existing symlink-based Plex/Sonarr/Radarr integration.

### New topology

- `nzbdav` (image `ghcr.io/nzbdav/nzbdav:latest`, port 3000) - WebDAV + SABnzbd-compatible API +
  admin API. Fully headless-configured via `NZBDAV_CONFIG__...` environment variables (available
  since its v0.9.0 release) - providers, arr instances, import strategy, WebDAV creds, rclone RC
  notification settings, all declarative in `docker-compose.yml`/`.env`, matching this stack's
  existing infrastructure-as-code style. No manual Settings-UI setup was done or is needed.
- `nzbdav_rclone` (image `rclone/rclone:latest`) - the actual FUSE mount owner now, replacing
  BearMount in that role. Mounts NzbDAV's WebDAV tree at `/mnt/remote/nzbdav`.
- Radarr, Sonarr, Plex, Unpackerr, Cleanuparr all bind `/mnt/remote/nzbdav:rslave` (was
  `/mnt/bearmount:rslave`) - same cascade-restart requirement as always after a mount-owner
  recreate, just a new mount-owner name.
- Radarr/Sonarr's SABnzbd download-client entry updated in place (same ids, renamed
  "BearMount" -> "NzbDAV"): host `nzbdav`, port `3000`, no `urlBase` (NzbDAV's SAB API is at
  root `/api`, unlike BearMount's `/sabnzbd` prefix). Both connection tests pass.
- Stale "BearMount Webhook"/"AltMount Webhook" notification entries (pointing at long-dead
  hostnames) found and deleted from both Radarr and Sonarr during this cutover - leftover cruft
  from the two earlier cutovers that had never been cleaned up.

### Real bug found and fixed during setup: rclone "already mounted" false-positive

Binding the exact FUSE target path into the container (`/mnt/remote/nzbdav:/mnt/remote/nzbdav`)
made rclone's own pre-mount safety check see that path as *already a mount boundary* (trivially
true - a bind mount is itself a distinct mount from its parent's perspective) and refuse to
mount ("directory already mounted, use --allow-non-empty to mount anyway"), failing identically
on every attempt, not just a race with a prior crashed instance. Fixed by binding the **parent**
directory (`/mnt/remote:/mnt/remote:rshared`) instead, letting rclone create the `nzbdav`
subdirectory and mount fresh underneath - an ordinary subdirectory of an already-mounted parent
isn't its own mount boundary, so the false-positive goes away. Confirmed live: mount succeeds
and stays up.

### Config audit performed same day (after the cutover, on request)

Verified every piece via NzbDAV's own real admin API (not assumed from the env vars alone):
`GET /api/get-config` (form param `config-keys`, repeatable) confirmed every
`NZBDAV_CONFIG__...` value loaded as the effective config - **despite the route name, this must
be called as a form-encoded POST** (`curl --data-urlencode config-keys=... --data-urlencode
config-keys=...`, no `-X GET`); a real GET with `?config-keys=...` query params 500s with "This
request does not have a Content-Type header." Confirmed live 2026-07-29. Build repeated
`--data-urlencode` flags as a bash array, not string concatenation, when passing many keys.
`POST /api/test-arr-connection`
(form params `host`/`apiKey`) confirmed live Radarr and Sonarr connectivity; `POST
/api/test-usenet-connection` (form params `host`/`user`/`pass`/`port`/`use-ssl`) confirmed live
provider login; `POST /api/test-rclone-connection` (form param `host`, optional `user`/`pass`)
confirmed the rclone RC link once RC notifications were added (see below). All these routes
require `x-api-key` header or `apikey` query/form param - same key as the SAB API
(`FRONTEND_BACKEND_API_KEY`), no separate JWT-login flow the way BearMount's admin API needed.

Rclone RC notifications (`vfs/forget` on file add/remove, avoids relying purely on
`--dir-cache-time` for fresh directory listings) were not configured in the initial cutover and
came back "Connection refused" on first test - added `--rc --rc-addr=:5572 --rc-user=rclone
--rc-pass=...` to the `nzbdav_rclone` command plus `NZBDAV_CONFIG__RCLONE__RC_ENABLED/HOST/USER/
PASS` on the `nzbdav` side, recreated both containers (regardless of queue state, per explicit
request), recreated the 5 dependents, and reconfirmed the mount and all four connection tests
pass.

### What was NOT ported from BearMount, and why

- **`/api/bearmount/fuse/status`, `/start`, `/stop`** (JWT-authenticated FUSE mount control) -
  NzbDAV owns no FUSE mount itself; `nzbdav_rclone` is a stock rclone container with no
  app-specific admin API to control it this way.
- **`/api/bearmount/health/stats`, `/health/corrupted`** - no equivalent admin endpoint confirmed
  in NzbDAV's own docs; dropped rather than guessed at (see CLAUDE.md's "don't guess APIs" rule).
- **The entire ffprobe/D-state read-hang cascade-restart subsystem**
  (`_host_lazy_umount`, `_wait_for_bearmount_content`, `_restart_bearmount_cascade`,
  `/api/plex/restart-cascade`, `/api/plex/unstick`, `/api/bearmount/unstick-ffprobe-hang`) - built
  and confirmed against BearMount's own Go FUSE implementation's specific bug signature (see the
  section above). `nzbdav_rclone` is stock, separately-maintained rclone - a different codebase
  with no confirmed equivalent bug. Removed rather than fabricating an equivalent for a problem
  never observed here; `FIXES.md` is marked closed/moot rather than deleted. Revisit if
  `nzbdav_rclone` ever shows a real hang class of its own - the general
  `MOUNT_PREREQS`/`MOUNT_PROVIDERS`/`MOUNT_DEPENDENTS`-ordered restart mechanism (unaffected by
  this removal) still covers the ordinary case.
- **BearMount's direct-SQLite pre-recreate safety check** (`_bearmount_queue_counts` reading
  `bearmount.db`'s `import_queue` table) - NzbDAV's own `db.sqlite` schema is unconfirmed/unread,
  so the replacement (`_nzbdav_queue_counts`) goes through the SAB API's `queue` mode instead of
  guessing at raw SQL.
- **Fish function names** (`stack-bearmount-queue.fish` etc., under `~/.config/fish/functions/`,
  outside this repo) - **correction, 2026-07-28**: the claim above that these "still work since
  they call the underlying API by URL, not by name" was wrong, confirmed live - the function
  bodies themselves still hardcoded the removed `/api/bearmount/*` routes (404 on every call),
  not just a stale name. Renamed to `stack-nzbdav-queue`/`-history`/`-stats`/`-delete-failures`
  with bodies updated to the real `/api/nzbdav/*` routes. `stack-bearmount-restart` and
  `stack-bearmount-unstick-ffprobe-hang` were deleted outright rather than renamed (see below and
  the entry above on what wasn't ported) - the former is redundant with `stack-container restart
  <name>` plus `docker-compose-manager`'s cascade-aware restart, the latter has no nzbdav
  equivalent. `stack-plex-unstick`/`stack-plex-restart-cascade` were also deleted - their backend
  routes are gone (see above), the cascade-restart functionality they wrapped now lives in the
  `docker-compose-manager` skill.
- **`config/bearmount/`** (BearMount's own SQLite DB, ~368M metadata, ~51G VFS cache) - none of
  it reusable by NzbDAV's completely different data model. Renamed aside to
  `config/bearmount.removed-<timestamp>/` rather than deleted, for a rollback window. Deleted for
  real 2026-07-28 (~81G by then) after the cutover's live verification above was confirmed
  working and the user explicitly signed off on ending the rollback window.

### Verification performed live, not just configured

Triggered a real `EpisodeSearch` for RuPaul's Drag Race S01E01 end-to-end: grabbed via NzbDAV,
imported by Sonarr as a **real symlink** (`.../Season 1/... .mp4 -> /mnt/remote/nzbdav/.ids/...`),
confirmed `hasFile: true` with a real `episodeFileId` and file size, and `dd`-read 4MB through
the symlink at 466 MB/s - genuinely streaming, not a dangling reference. Plex reads the same
mount so picks up new content on its next scan without further changes.

## MDBList toplists import + two real import-list bugs found, 2026-07-28

Built to bulk-import every list on `mdblist.com/toplists/` into Radarr/Sonarr as native,
unmonitored, no-search import lists (`scripts/mdblist_toplists_import.py`) - no new container,
no MDBListarr. MDBList's own docs confirm both Radarr's "Custom Lists" (`RadarrListImport`) and
Sonarr's "Custom List" (`CustomImport`) accept a plain `mdblist.com/lists/<user>/<slug>` URL
directly; MDBListarr is a different tool (syncs an existing library's watched-state back to
MDBList) and doesn't apply here. Each list is classified by MDBList's own `/lists/<user>/<slug>`
metadata endpoint (real `movies`/`shows` counts, not guessed) before being routed - confirmed live
that handing a show-only list to `RadarrListImport` (or the reverse to `CustomImport`) fails
validation outright ("no results were returned"), it does not silently skip mismatched items.
`mdblist.com/toplists/` itself is a single static page (no pagination) of ordinary `/lists/`
links; `api.mdblist.com` is a Django REST Framework API that returns its browsable HTML page
instead of JSON if the request's `Accept` header prefers `text/html` (confirmed live) - needs a
separate `Accept: application/json` header from the browser-shaped one used for the HTML scrape.
Two different toplists.html entries can share a display name (e.g. two different users' "Latest
TV Shows") - Radarr/Sonarr both reject a duplicate import-list name, so the registered name
includes the MDBList username/slug for guaranteed uniqueness.

**Two real bugs found in `control-panel/app.py`'s existing generic import-list endpoint**
(`/api/arr/{app}/import-list/add`, already used by `stack-radarr-import-list`,
`stack-sonarr-import-custom-list`, `stack-tmdb-*-import`, `stack-trakt-import-list` before this):
- Sonarr's importlist schema uses different field names than Radarr's
  (`enableAutomaticAdd`/`searchForMissingEpisodes`/`shouldMonitor` vs. Radarr's
  `enableAuto`/`searchOnAdd`/`monitor`) - the endpoint was unconditionally writing Radarr's field
  names onto the Sonarr body too, so none of the three ever actually reached Sonarr; every
  Sonarr import list created through it silently kept the live schema's own defaults instead.
- **`enableAuto` (Radarr) / `enableAutomaticAdd` (Sonarr) is not a search toggle - it's the
  master "add anything from this list at all" switch**, confirmed by a live probe: created a
  real `RadarrListImport` test entry (id 8, a 250-movie MDBList list) with `enableAuto: false`,
  `monitor: none`, `searchOnAdd: false`, ran `ImportListSync` - 0 movies added. Flipped only
  `enableAuto` to `true`, ran the same sync again - 246 added (unmonitored, no search triggered,
  exactly as configured). The old code tied `enableAuto` to the caller's `search_on_add` flag, so
  **every existing `--no-search` invocation of this stack's list-import commands added zero
  items to Radarr**, not just skipped the search. Test artifacts (the id-8 import list, all 246
  movies) were deleted immediately after confirming the result - not a lasting change to the
  library. Fixed: `enableAuto`/`enableAutomaticAdd` now always `true`; only
  `searchOnAdd`/`searchForMissingEpisodes` follows the caller's flag.

Deployed via the normal `docker compose build control-panel && up -d --force-recreate` path, spot
health-checked (`/healthz`) before use.

## Fish function cleanup: bearmount->nzbdav rename, dead functions removed, 2026-07-28

Continuation of the BearMount->nzbdav/nzbdav cutover above, on the fish-function side (outside
this repo, under `~/.config/fish/functions/`) - see the "What was NOT ported from BearMount"
section's fish-function entry, corrected in place above once this work confirmed the original
claim wrong. Also removed, same session: `Stack/` (empty dir), `.ruff_cache/` (regenerable lint
cache), `status.txt`/`prompt` (stale artifacts from a pre-BearMount, even pre-AltMount stack
architecture - mentioned services and sibling repos that no longer exist), a bare plaintext
secret (`decypharpass`) sitting outside any repo, and orphaned `config/` directories for services
confirmed absent from `docker-compose.yml` (`nzbget` 25G, `traefik`, `authelia`, `readarr`,
`calibre-web` - Traefik/Authelia were the reverted security-stack experiment, see README's
Security section; Readarr/Calibre-Web were retired in v10.9.8, no ebook app in this stack since).
All confirmed via `mount`/`docker inspect`/`docker-compose.yml` grep before deletion, not assumed.

Also deleted, orphaned from earlier feature removals unrelated to this cutover: `media/
bearmount-import/` (184K, no mount, no compose reference - a leftover BearMount-era import path;
current nzbdav symlinks land under `/mnt/remote/nzbdav` directly, no `media/*-import` subfolder
in this architecture) and `media/wrestling/` (4K, dangling since the Sportarr removal, see
below). `config/bearmount.removed-20260728_145530/` (~81G, the rollback-window copy from the
cutover section above) was also deleted for real this same session, after live verification and
explicit user sign-off - see that section's updated note.

**Real live bug found while checking for test/script staleness after this cleanup**:
`scripts/plex-health-monitor.py` (a long-running systemd service, confirmed actively running)
had a Tier 2 auto-remediation path - on a confirmed FUSE/D-state hard hang, it called
`/api/plex/restart-cascade` to auto-trigger the mount-cascade restart. That endpoint was removed
in the BearMount->nzbdav cutover above (superseded by the `docker-compose-manager` Claude Code
skill) but this script was never updated - it would have silently 404'd on every real hard-hang
detection, alerting "failed" but never actually attempting the intended remediation, since first
deployed after the cutover. Fixed by removing the Tier 2 auto-restart call entirely (per explicit
user choice) - a hard hang now only alerts; there is no headless equivalent to trigger, since the
cascade-restart logic now lives in an interactive Claude Code skill a systemd script can't invoke.
Tier 1 (plain restart, for `busy_db`/sustained `scan_lag`) is unaffected. The matching
`tests/scripts/test_plex_health_monitor.py` cases used the same dead path string as an arbitrary
example (fully mocked, asserted nothing endpoint-specific) - updated to a live path for clarity,
not because the old assertions were wrong. `systemd/stack-plex-health-monitor.service`'s
`Description=` updated to match, service reloaded and restarted live to pick up the fix.

Also found and fixed during the same pass: 19 pre-existing failing tests in
`tests/control_panel/test_helpers.py` and `test_plex_health.py`, all exercising BearMount-only
functions/routes removed in the cutover above (`_bucket_bearmount_item` -> renamed
`_bucket_nzbdav_item`, drop-in signature; `_bearmount_queue_counts` -> `_nzbdav_queue_counts`,
a real reimplementation via the SAB API rather than direct sqlite, test rewritten against that;
`/api/plex/restart-cascade`, `/api/plex/unstick`, `_restart_bearmount_cascade` - tests deleted
outright, no equivalent feature exists to test). These had been failing since the cutover was
first made (uncommitted, predating this session) - would have broken CI on the first push.

## NzbDAV's own content store is separate from Arr-side symlinks, and its native deletion API, 2026-07-31

Sonarr's `DELETE /api/v3/series/{id}?deleteFiles=true` only removes the Arr-side symlink
under `/data/shows/...` - it does **not** touch NzbDAV's own WebDAV-backed content store
(`/mnt/remote/nzbdav/content/tv/...`, distinct from `/mnt/remote/nzbdav/completed-symlinks/`
which Cleanuparr does sweep on its own). Found by deleting all Star Trek series via Sonarr,
then noticing 268 Star Trek entries still present in `content/tv` afterward - real leftover
data, not a display artifact. `completed-symlinks/tv` was already clean by the time this was
checked, apparently auto-swept by Cleanuparr independently.

## Versioning switched to release-please, 2026-07-31

Version tracking for this repo was fully manual before this: README's top-line "Current
version" string and its "## History" section were both hand-edited on every notable change,
and `publish-installer.yml` regex-extracted that top line to tag the installer image. The two
had already drifted out of sync by this point (top line said v11.9.0 while History's last
entry was v11.12.0) - nothing was enforcing they matched.

Replaced with [release-please](https://github.com/googleapis/release-please)
(`release-please-config.json`, `.release-please-manifest.json`,
`.github/workflows/release-please.yml`): it watches conventional-commit messages
(`feat:`/`fix:`/`chore:`/etc.) pushed to `main`, maintains a standing release PR that
accumulates them into `CHANGELOG.md`, and bumps README's version line itself via the
`extra-files` generic-replacer mechanism - the version number in README.md:3 is now wrapped in
`<!-- x-release-please-version -->` sentinel comments release-please rewrites in place, so
don't hand-edit that number or the comments around it.

`publish-installer.yml` was switched from `push`-with-path-filters to trigger on `release:
published` (the event release-please's merge produces), pulling the version straight from
`github.event.release.tag_name` instead of grepping README - the grep still would have worked
since release-please keeps that line in sync, but the tag is the more direct source now that a
real GitHub Release/tag exists for every version. Manual re-runs need an explicit
`workflow_dispatch` `tag` input now, since there's no push event to infer a version from.

README's "## History" section is frozen as of v11.12.0 (the manifest's seed value) - past
entries are kept as a condensed record, but nothing gets appended there going forward.
`CHANGELOG.md` is the authoritative changelog from this point on.

**Bootstrap gotchas hit on the first real run, both now fixed:**
1. Repo-owned Actions can't open PRs by default - `release-please` failed with "GitHub Actions
   is not permitted to create or approve pull requests" until `Settings → Actions → General →
   Workflow permissions → Allow GitHub Actions to create and approve pull requests` was enabled
   (`gh api -X PUT repos/OWNER/REPO/actions/permissions/workflow -f
   default_workflow_permissions=write -F can_approve_pull_request_reviews=true`).
2. With that fixed, the very next run walked all 325 historical commits (no existing tag
   matched release-please's bookkeeping) and produced a misleading v11.13.0 PR mixing
   months-old BearMount-era work into a "new" release - closed unmerged. Fixed by tagging the
   seed commit itself as `v11.12.0` (matching the manifest exactly), which made release-please
   correctly report "Considering: 0 commits" on the next run. Any future re-bootstrap of
   release-please on this repo (or a fork) needs that same tag-the-seed-commit step first.

NzbDAV exposes its own native (non-SABnzbd-compatible) API for managing this content store,
undocumented anywhere public-facing - found by reading the compiled frontend JS bundle
(`/app/frontend/build/server/assets/*.js` inside the `nzbdav` container, searched via
Node's own `fs`/string search since the container has no `grep`/`python3`, only `node`):

- `POST /api/delete-webdav-item` - form-encoded body, single field `path` (WebDAV-relative,
  e.g. `/content/tv/Show.Name.S01E01/Show.Name.S01E01.mkv`), auth via `X-Api-Key` header
  using the same key as `FRONTEND_BACKEND_API_KEY`/the SAB API. Returns
  `{"status":true,"error":null}` on success.
- This 403s by default: `{"status":false,"error":"WebDAV is read-only. Disable 'Enforce
  Read-Only' in Settings → WebDAV."}` - a deliberate safety setting
  (`webdav.enforce-readonly`, default `"true"`) that also explains why a raw `rm -rf`
  through the `nzbdav_rclone` FUSE mount fails with a generic `I/O error` (the mount is
  WebDAV-backed - see `config/nzbdav-rclone/rclone.conf` - so a filesystem `rm` becomes a
  WebDAV `DELETE` under the hood, which NzbDAV's own backend then rejects the same way).
- `POST /api/update-config` toggles it - form-encoded `configName`/`configValue` pairs
  (confirmed via the same JS bundle: `body: form(...configItems.map(item =>
  [item.configName, item.configValue]))`), e.g. `webdav.enforce-readonly=false`. Same
  pattern as the already-documented `POST /api/get-config` gotcha in CLAUDE.md (form-encoded
  POST, not a GET with query params) - both use the identical `configName`/`configValue`
  (or `config-keys`, for reads) form-field convention.
- **Always toggle it back to `true` after the deletion pass** - it's a deliberate guard, not
  an oversight, and this stack has a documented history of mass-deletion incidents from
  exactly this class of safety toggle being left off (Plex's `autoEmptyTrash`, same idea).
  Verify the restore worked *behaviorally*, not just by checking the API returned 200 -
  `GET /api/get-config` returned an empty `configItems` array for this key when tested
  (cause not fully diagnosed - possibly a param-encoding mismatch on the read side
  specifically), so the only confirmed-reliable check is a real follow-up delete attempt
  correctly 403'ing again.

Separately: `rclone reveal <obscured-string>` (not `rclone obscure --reveal`, which doesn't
exist as a flag in this rclone build) decodes an rclone-obscured password from
`rclone.conf` back to plaintext - needed once to get WebDAV Basic-Auth credentials working
directly against `nzbdav`'s own port, before the `X-Api-Key` header path was found and
made that unnecessary.

## Sonarr/Radarr silently drop a freshly-added series/movie's first import, 2026-07-31

**Root cause**: `createEmptySeriesFolders` (Sonarr) and `createEmptyMovieFolders` (Radarr) -
`/api/v3/config/mediamanagement` - both defaulted to `false`. A series/movie's own destination
folder (`/data/shows/<Series> (Year) {tmdb-N}` / `/data/movies/<Movie> (Year) {tmdb-N}`) is
never created at add-time, only implicitly by the first successful import. When that first
download completes before the folder exists, Sonarr's own scan code throws
`System.IO.DirectoryNotFoundException: Could not find a part of the path '...'` - both from
`ManualImportService.GetMediaFiles` (when a `seriesId`/`movieId` is passed - scan without one
instead, letting Sonarr identify the release from the filename, and it works even without the
folder existing) and from the background `ProcessMonitoredDownloads` command, which does NOT
fail cleanly on this - it hangs in `started` state indefinitely (`DELETE
/api/v3/command/{id}` then 409s with "Unable to cancel task"), and Sonarr's command executor
has limited concurrency, so every other queued command (searches, further imports, RSS sync)
backs up behind it. Same root cause as the earlier MasterChef Australia incident this repo's
history references, just now root-caused precisely and fixed at the source instead of worked
around per-item.

**Fix applied** (both retroactive and forward-looking):
1. `PUT /api/v3/config/mediamanagement/1` with `createEmptySeriesFolders`/
   `createEmptyMovieFolders` set `true` on both Sonarr and Radarr - every future add now gets
   its folder immediately, before any download can complete.
2. Swept every currently-monitored series/movie's `path` for existence
   (`docker exec sonarr|radarr sh -c 'while read p; do [ -d "$p" ] || echo "$p"; done'`) -
   found **1045 of 1152** monitored Sonarr series and **414 of 1949** monitored Radarr movies
   missing their folder. All were latent copies of this same bug, waiting for their first
   completed download to trigger it. Bulk-created every missing one
   (`mkdir -p && chown hotio:hotio && chmod 775`, matching this stack's existing folder
   convention - confirmed via `stat` on a real existing folder before assuming ownership,
   not guessed) via the same batched shell-loop approach, verified zero missing afterward.
3. **The only-if-stuck recovery, if this pattern recurs from some other cause**: creating the
   missing folder does not unstick a command already hung in `started` state (confirmed - it
   was already past the failure point) and it can't be cancelled via the API. `docker restart
   sonarr` (or `radarr`) clears the deadlocked command queue - this is a plain app-process
   restart, not touching the FUSE mount, so none of the nzbdav_rclone cascade rules apply; a
   normal `docker restart` is safe here, unlike for `nzbdav`/`nzbdav_rclone` themselves.

Neither of these Sonarr/Radarr settings nor the folder creation went through any tracked file
in this repo - both apps store `createEmptySeriesFolders`/`createEmptyMovieFolders` in their
own internal SQLite config, and the folders themselves live on the `/data` bind mount, not in
git. Nothing to commit for this fix; this section is the only record of it.

## Workflow playbook: recurring task types

Add to this section as new recurring task shapes come up. Goal: the next session facing
the same *kind* of problem starts from the playbook, not from scratch.

**A bundled/off-the-shelf dependency has a bug** (first hit 2026-07-22, NzbDAV's connection
leak — see the landmine above):
1. Rule out our own config first with a raw, protocol-level test that bypasses the app
   entirely (e.g. a manual `openssl s_client` NNTP auth) before concluding upstream is
   broken — this is what actually distinguished "our MaxConnections setting" from "NzbDAV
   itself" here.
2. Clone the upstream repo to a scratch dir (never into this repo) and read the real source
   before guessing at a fix from logs alone.
3. **Test any patch against a fake/unreachable endpoint first, never straight to the real
   live third-party service** — a connection/retry-logic fix can turn into a rapid-fire
   storm against a real account the moment it works correctly. Confirmed live: fixing
   NzbDAV's socket leak let retries fire fast enough to escalate a real account's failure
   count from ~90 over several minutes to 778 within one second. Only test against the real
   service briefly, after the fake-endpoint test confirms the retry rate is sane.
4. Fork the upstream repo (`gh repo fork <owner>/<repo> --clone=false`), push a branch, open
   a real PR referencing the filed issue — don't just comment with a diff.
5. For a broader security/leak audit of the dependency's source, reach for the
   `fullstack-dev-skills:security-reviewer` plugin skill (SAST/dependency-audit/secrets-scan
   focus) rather than this repo's own `/security-review` (scoped to git-diff PR review,
   explicitly excludes whole-codebase resource-leak findings — confirmed by a subagent that
   tried it and bounced off) or an unstructured general-purpose-agent prompt.
   `fullstack-dev-skills:debugging-wizard` is worth trying for the initial stack-trace/log
   correlation phase too, ahead of manual log reading.
6. Don't pin this stack's `docker-compose.yml` to a local/fork build permanently — leave the
   stock image pinned until the fix actually merges upstream into a real release, and record
   the PR/issue link plus the revert-when-merged condition here instead.

**Rotating a credential that multiple apps consume** (first hit 2026-07-22, Radarr/Sonarr/
Prowlarr/NzbDAV keys, after one turned up hardcoded in `.claude/settings.local.json`):
1. Start with the `secret-injector` skill (`rotate the radarr api key` is a listed trigger
   phrase) instead of hand-rolling this with raw `curl`/`sed` — it writes `.env` safely
   (value via stdin only, never echoed to a log or shell history) and can leak-scan the
   working tree for the old value still hardcoded somewhere.
2. Every consumer needs updating separately — nothing here shares one source of truth:
   - The issuing app's own key: Radarr/Sonarr live in `config/<app>/config.xml`'s
     `<ApiKey>` — a plain API `PUT /api/v3/config/host` silently ignores changes to
     `apiKey`, it has to be edited in the XML directly and the container restarted.
     Prowlarr: same pattern, `config/prowlarr/config.xml`. NzbDAV: config key `api.key`,
     rotatable through its login+get-config/update-config pattern (see the provider-config
     gotcha above for that pattern's shape).
   - Prowlarr's Applications sync entries (`/api/v1/applications/{id}`) — strip the
     read-only `id` field before PUTting back, or it 400s.
   - Seerr's `/api/v1/settings/radarr|sonarr/{id}` — same read-only `id`-field gotcha.
   - Bazarr's `/api/system/settings` form-encoded endpoint (see
     [Bazarr](README.md#bazarr-subtitle-management) for its own gotchas).
   - Cleanuparr's `arr_instances` SQLite row — stop the container first (WAL-safety, same
     practice as the Lidarr/Whisparr removals), edit directly; no REST endpoint exists for
     this table.
   - NeutArr's `config/neutarr/<app>.json` `api_key` field — plain JSON edit, safe whenever
     NeutArr's own container is stopped.
   - Radarr/Sonarr's own NzbDAV download-client entry (`/api/v3/downloadclient/1`) needs
     NzbDAV's key too — separate from Radarr/Sonarr's own issuing-app key above.
   - `control-panel` needs `--force-recreate` afterward — it only reads `.env` at
     container-*create* time (see the Commands section above).
3. Test each consumer's connection afterward via its own `/test`-style endpoint rather than
   assuming the write took — most of the endpoints above have one.

## WebTools-NG added as a local (non-Dockerized) Plex maintenance tool, 2026-08-01

`WebTools-NG` (https://github.com/WebTools-NG/WebTools-NG) is an Electron desktop GUI for
Plex maintenance (export/import playlists, poster management, collections, etc.) — not a
headless service. It ships only as a Windows/Linux/Mac desktop app (AppImage on Linux), so
it doesn't belong in `docker-compose.yml`; user explicitly asked for it at the local level
instead.

- Installed to `~/Applications/WebTools-NG-1.2.1.f962812.AppImage` (executable bit set).
- Required `fuse2` (`sudo pacman -S fuse2`) to be installed system-wide first — AppImages
  built with the older appimage-runtime need libfuse.so.2, which CachyOS doesn't ship by
  default. Installed 2026-08-01.
- Launch via the AppImage directly (double-click in KDE Plasma's file manager, or
  `~/Applications/WebTools-NG-*.AppImage &` from a terminal) — it's a GUI app, not something
  Claude Code can drive headlessly.
- On first launch, point it at this stack's Plex server: URL `http://192.168.4.20:32400`,
  token from `.env`'s `PLEX_TOKEN`. Both come from the same `.env` Plex already uses — no
  separate credential needed.
- No update automation exists for this — it's a manually-downloaded release binary, not
  pulled by any compose/watchtower mechanism. Re-download from GitHub Releases to upgrade.

## `stack-queue-autofix` added: queue-autofix promoted from ad hoc curl to a real endpoint, 2026-08-01

A recurring 5-minute cron loop had been running the same curl sequence by hand each cycle:
blocklist `failedPending` Radarr/Sonarr queue items, explicitly trigger a per-item search
after blocklisting, blocklist+research Radarr's `importBlocked` items every cycle (no
manual-import attempt first — user explicitly chose this over trying
`/api/arr/radarr/manual-import-all` first, even though some `importBlocked` items are good
completed downloads that just need a manual import trigger), and check NzbDAV queue health.
Promoted to `POST /api/arr/queue-autofix` (`control-panel/app.py`) plus a
`stack-queue-autofix` fish function wrapping it, so the loop (and any manual check) is one
call instead of a multi-step curl script.

- **Why not just extend `/api/arr/{app}/unstick`**: `unstick`'s `stuck_queue_items()` filters
  on `trackedDownloadStatus in (warning, error)`. `failedPending` items keep
  `trackedDownloadStatus: "ok"` — only `trackedDownloadState` flips — so `unstick` never
  touches them; confirmed live, a queue of 128 dead-article `failedPending` releases sat
  untouched through repeated `unstick` calls. `importBlocked` items *do* set
  `trackedDownloadStatus: "warning"`, so `unstick` would have caught those, but not the
  `failedPending` half of the problem — hence a separate endpoint rather than widening
  `unstick`'s filter (which is also used by other callers expecting its narrower scope).
- **Explicit per-item search, not just `skipRedownload=false`**: user asked for a
  belt-and-suspenders `EpisodeSearch`/`MoviesSearch` command per blocklisted item's
  episodeId/movieId, not relying solely on the delete call's implicit search.
- **`FAILED_PENDING_STORM_THRESHOLD = 15`**: arbitrary but grounded in a real incident
  (2026-08-01, Sonarr queue hit 128 simultaneous `failedPending` items in one pass — a
  genuine storm, not noise). Below the threshold, `autoRedownloadFailed` is left alone even
  if `true`, since a handful of dead articles isn't evidence of a storm.
- **Known limitation, confirmed live**: a movie stuck in `importBlocked` because the release
  is mistyped (e.g. "City Of Angles" vs "City of Angels" — Radarr can't string-match to the
  title/alternate-titles table, only via grab-history ID, which always trips
  `importBlocked`) will loop forever if the movie is monitored — every cycle re-downloads a
  multi-GB file for nothing. `queue-autofix` does not detect or break this; the actual fix is
  unmonitoring the movie (confirmed: movie 14374, The Crow: City of Angels 1996, unmonitored
  2026-08-01 after 3 consecutive cycles). A user-added `alternateTitles` entry does **not**
  persist via `PUT /api/v3/movie/{id}` — Radarr silently drops non-`tmdb`-sourced entries on
  save, so that's not a working fix either.

## NzbDAV `(2)`-suffix dedup bug — real root cause of most `importBlocked` loops, fixed 2026-08-01

What looked like ~10 separate "bad title match" cases in one `queue-autofix` session (POTC:
Dead Man's Chest, Naked Gun 2½, TMZ Diddy specials x3, Hell House LLC II, plus earlier
Fellowship of the Ring, Return of the Jedi, SpongeBob SquarePants Movie, Space Chimps 2, Land
Before Time VII/XIII, Hey Arnold: The Jungle Movie, High Strung Free Dance) was actually one
systemic bug, not per-movie bad releases:

- NzbDAV's config key `api.duplicate-nzb-behavior` (frontend: Settings → SABnzbd → "Behavior
  for Duplicate NZBs") defaults to `increment`. When an NZB's destination folder name has ever
  been used before — even if that folder was since deleted/cleaned up, NzbDAV's registry of
  assigned names is independent of the current filesystem contents — it appends ` (2)`, ` (3)`,
  etc. to the new symlink folder/file name instead of reusing the name or failing outright.
- That ` (2)` suffix in the actual filename breaks Radarr's release-name parser during import.
  Confirmed via `POST /api/v3/manualimport?folder=...`: the scan returned `"movie": null`,
  rejection `"Unknown Movie"` — Radarr can't parse the title at all from a name ending in
  ` (2).mkv`/`.mp4`. This forces Radarr's "matched by ID via grab history" fallback path,
  which requires manual import confirmation and reports as `importBlocked`.
  `queue-autofix`'s blocklist+research response can never fix this — every re-search just
  grabs a new release that lands with yet another incrementing suffix, so the movie loops
  forever regardless of how many different releases actually exist.
- **The file itself is fine** — confirmed by manually running `ManualImport` with an explicit
  `movieId` against the ` (2)`-suffixed path (bypassing Radarr's broken auto-parse): Naked Gun
  2½ imported successfully, `hasFile` flipped to `true`. Every movie that hit this pattern
  before the fix was NOT bad content — the earlier round of "unmonitor after 2 cycles" fixes
  applied to some of these (Fellowship of the Ring, Return of the Jedi, SpongeBob SquarePants
  Movie, Space Chimps 2, Land Before Time VII/XIII, Hey Arnold: The Jungle Movie, High Strung
  Free Dance) were masking this bug, not fixing bad releases — all 7 were remonitored after
  the real fix went in (Crow: City of Angels, movie 14374, stayed unmonitored — that one's
  root cause was a genuine mistyped-release/alternate-title mismatch, unrelated to this bug,
  and it already has a satisfied file so re-monitoring would just resume needless upgrade
  churn).
- **Fix applied**: `POST /api/update-config` with form field `api.duplicate-nzb-behavior=mark-failed`
  (only two values exist in the NzbDAV UI: `increment` or `mark-failed`). Now a name collision
  fails the download cleanly (`failedPending`, not a broken `importBlocked` import) instead of
  producing an unparseable suffixed file — `queue-autofix`'s existing failedPending
  blocklist+research handles that correctly, so a colliding re-grab just moves on to a
  genuinely different release instead of hitting the parser wall every time.
- **Signature to watch for** if this class of loop recurs despite the fix: `importBlocked`
  item whose queue `outputPath` ends in ` (2)`, ` (3)`, etc. — check that before assuming it's
  a title-mismatch case needing unmonitor; verify with `docker exec radarr ls` on the actual
  completed-symlinks path and a manual `POST /api/v3/manualimport?folder=...` scan for
  `"movie": null` / `"Unknown Movie"` before concluding anything.

## Radarr import lists silently re-monitor manually-unmonitored movies, 2026-08-02

Unmonitoring a movie to stop the `stack-queue-autofix` loop's blocklist/re-search churn
(title-mismatch class, see above) is **not permanent** if that movie is a member of an
enabled Radarr import list. Confirmed live: "Urban Legends: Final Cut" and "Mannequin Two:
On the Move" were manually unmonitored, then found `monitored: true` again hours later
(with a fresh grab already in flight) — several enabled import lists (`Horror`, `IMDb Top
250`, `IMDb Popular Movies`, `A24`, `Mindfuck`, `StevenLu`) have `monitor:
movieOnly`/`movieAndCollection`, so their periodic sync silently re-adds/re-monitors any
movie still present in the list.

**Fix**: add the movie to Radarr's Exclusions list, not just unmonitor it —
`POST /api/v3/exclusions` with `{"tmdbId":..., "movieTitle":..., "movieYear":...}` (get
`tmdbId` from `GET /api/v3/movie/{id}`). Exclusions make list syncs skip the title
entirely, which survives re-monitoring attempts that a plain unmonitor doesn't.

Given how many movies got unmonitored for this loop across 2026-08-01/02 (~60), expect
more of them to resurface the same way over time as list syncs run — when one does,
exclude it rather than just re-unmonitoring.

## Loop remediation toolkit added to the Control Panel, 2026-08-02

`stack-queue-autofix`'s automated loop only blocklists + re-searches `failedPending`/
`importBlocked` queue items — it deliberately never unmonitors or excludes, since telling
a genuine loop (scarcity, title mismatch, scene-number mismatch, a REMUX/quality-profile
rejection affecting a whole series) from an in-progress scan burst is a judgment call, not
something safe to automate. Across 2026-08-01/02 that judgment call was made by hand, over
and over, using `history?movieId=`/`episodeId=` on a suspected title, checking for the
NzbDAV `(2)`/`(3)` dedup-suffix bug signature, checking Sonarr's `sceneEpisodeNumber` vs
`episodeNumber`, and applying the resulting fix through raw `curl` calls — see
`feedback_blocklist_failed_pending.md` in Claude's memory for the full decision tree and
~60 individually-diagnosed cases. None of that was available to click through in the
dashboard itself.

Added a "Loop remediation" panel (`control-panel/static/js/loop-remediation.js`) under the
existing Radarr/Sonarr fleet section, backed by new `app.py` endpoints:

- `GET /api/arr/{app}/loop-candidates` — the detector. Pulls
  `GET /api/v3/history?eventType=downloadFailed&pageSize=500` (one bulk call, not one per
  title — confirmed this returns everything needed), groups by movieId/episodeId, keeps
  groups with 2+ occurrences in the lookback window (default 6h), and classifies each
  against the same decision tree used by hand: dedup-suffix signature found → flag as
  `suffix-bug` (no action — means the NzbDAV `mark-failed` config reverted, see above);
  Sonarr scene-number mismatch → suggest `unmonitor`; 8+ episodes of the same series
  looping together → `review-profile` (the Batwoman/Billions/Jack Ryan REMUX-batch shape,
  no safe one-click fix); otherwise → suggest `unmonitor`. No new persistence — Radarr/
  Sonarr's own history already has everything needed.
- `POST /api/arr/{app}/unmonitor` — batched unmonitor. Radarr uses
  `PUT /api/v3/movie/editor` with a `movieIds` array (confirmed live 2026-08-02 via a
  deliberate 500 on a fake id — the call got past body validation before failing on the
  DB lookup, proving the shape); Sonarr uses the already-battle-tested
  `PUT /api/v3/episode/monitor`.
- `POST /api/arr/radarr/exclude` — the durable fix from the section above, now one click
  instead of a manual `tmdbId` lookup + curl. Radarr-only; no Sonarr Exclusions equivalent
  exists, and the UI doesn't fake one.
- `GET /api/nzbdav/dedup-config-check` — confirms `api.duplicate-nzb-behavior` is still
  `mark-failed`. Uses its own form-encoded POST to `get-config` directly rather than
  `nzbdav_api()`'s helper, since that helper only wraps the SAB-compatible `mode=` GET
  surface and a GET with query params against `get-config` 500s (see CLAUDE.md).

Also fixed in the same pass: `_blocklist_and_research()` (the function behind
`queue-autofix` itself) used `raise_for_status()` unconditionally on its blocklist DELETE
call, so a benign race — Radarr/Sonarr's own concurrent import processing clearing the
queue item first — landed in `errors[]` same as a real failure. Confirmed live: two items
timed out mid-batch on 2026-08-02 (13:03 cycle) and needed a hand retry before clearing.
Now retries once on timeout and tolerates a 404 on the delete, matching the pattern
`arr_unstick_importing` already used for its shared-`downloadId` case.

No auto-polling — the panel is on-demand (`Rescan` button) like Manual Import, not another
cron loop layered on top of the hourly `queue-autofix` one.

## Control Panel: stale-reference cleanup + crimson/brown retheme, 2026-08-02

Audit found three real stale-reference bugs in the frontend, none catastrophic (the app
degrades gracefully — an unmatched `FLEET_GROUPS`/`CONTAINER_LABELS` key just falls into
"Other", per app.py's own documented staleness tolerance) but all worth fixing:

- `static/commands.json` still named four live NzbDAV commands `stack-bearmount-*`
  (`delete-failures`/`history`/`queue`/`stats`) even though their `PathTemplate`s correctly
  point at `/api/nzbdav/*` and the matching fish functions were already renamed to
  `stack-nzbdav-*` back when BearMount was cut over (2026-07-28) — only the palette manifest
  entry was missed. Renamed to match.
- **Notifiarr was never real.** `reference.js` (quicklink + doc-link), `fleet.js`
  (`FLEET_GROUPS`), and `commands.json` (4 `stack-notifiarr-*` entries hitting
  `/api/notifiarr/*`) all referenced it, but no `notifiarr` service exists in
  `docker-compose.yml`, no `/api/notifiarr/*` route exists in `app.py`, and no mention of it
  exists anywhere in README/STACK.md history — not a removed app, a phantom one that was
  apparently wired into the frontend without ever being backed by a real container or route.
  Removed from all three files.
- `fleet.js`'s `FLEET_GROUPS` also still had a `recyclarr: "Arr apps"` entry — Recyclarr was
  confirmed removed entirely in v11.12.0 (README's History), and its `CONTAINER_LABELS`/
  `commands.json`/`/api/recyclarr/status` entries were removed at the time per that entry,
  but this one `fleet.js` key was missed. Removed.

Also retextured the entire dashboard from the original steel-teal/cool-neutral palette to a
crimson-accent/warm-espresso-and-parchment one, by request. The whole app is built on CSS
custom properties (`--bg`/`--surface`/`--ink*`/`--accent*`/`--good`/`--warn`/`--bad`/
`--unknown`, defined once each for light `:root` and dark `@media (prefers-color-scheme:
dark)` + `:root[data-theme="dark"]`) — retheming was a matter of swapping those two variable
blocks, not touching per-component CSS. Only a handful of hardcoded (non-`var()`) colors
existed outside that system and needed separate fixes: `.btn-danger:hover`'s hardcoded dark
red, a `var(--accent, #hex)` fallback value, the favicon's inline SVG `data:` URI, and a
`<select>` dropdown-arrow SVG `data:` URI in `style.css` — both `data:` URIs hardcode their
fill color since they're not real CSS and can't reference custom properties. Verified live in
both themes (toggled `data-theme` directly via devtools) after a `docker compose build
control-panel && up -d --force-recreate` — a stale served-CSS symptom during verification
turned out to be the browser tab's cached `<link>` stylesheet object, not a deployment bug
(confirmed by fetching `/style.css` with `cache: 'no-store'` and diffing against the
container's on-disk file, then forcing a real re-parse by swapping the `<link>` element).

## Plex Health `stalled_suspected` false-positive on large-show section refreshes, 2026-08-02

`/api/plex/scan-health`'s `stalled_suspected` branch (`app.py:3259`) trusts
`_plex_scanner_processes()` — a `ps aux` grep for the literal `Plex Media Scanner` child
process — to tell a genuine stall from a healthy-but-slow scan. Confirmed live: a
`library.update.section` refresh walking a 38+ season show ("Ridiculousness") ran entirely
in-process (no `Plex Media Scanner` subprocess spawned), with progress climbing normally
(98.4% → 98.5% within one poll), zero D-state threads, `mount_ok: true` — but still got
labeled `stalled_suspected` on every single poll, same blind spot the `analysis_active`
check (line 3252) was already added for on the Media Analyzer's batch cycles.

**Fix, frontend-side (`static/js/plex-health.js`)**: rather than widen the backend's
fragile process-name check further, confirm the trend client-side using the one signal
that's reliable regardless of which code path is scanning — whether the activity's own
`progress` value is advancing between polls. The badge only escalates to `stalled_suspected`
styling after `PLEX_STALL_CONFIRM_POLLS` (3, ~45s at the 15s poll cadence) consecutive polls
where the backend says `stalled_suspected` *and* progress hasn't moved; any poll where
progress ticks forward resets the streak and displays `scanning` instead. `hung_confirmed`
(D-state/mount failure) bypasses this smoothing entirely and stays trustworthy on a single
poll, matching how these two states already differ in urgency.

This also fixes a documentation/implementation gap: the module's own header comment claimed
"the frontend keeps its own ring buffer for 'stuck for N polls' trend detection", but no such
smoothing actually existed before this — the state badge was just the raw single-poll
backend value, redisplayed as-is every 15s. Verified the reducer logic directly (progress
climbing across 5 polls → always `scanning`; progress frozen for 3 consecutive polls →
correctly escalates to `stalled_suspected` on the 3rd) before deploying.

## New landmine: nzbdav's own EF Core/SQLite connection can deadlock, distinct from FUSE hangs, 2026-08-03

Sonarr's queue showed all 94 tracked items as `downloadClientUnavailable`, Radarr's/Sonarr's
health both reported "All download clients are unavailable due to failures". Looked like the
usual FUSE-hang landmine at first, but it wasn't: `ls /mnt/remote/nzbdav` returned instantly,
mount count was 1 (no leak), no D-state processes blocked on the mount itself (two `ffprobe`
D-state threads were present but scanning unrelated already-imported files, not evidence of a
wedged mount).

The actual fault was nzbdav's own SAB-compatible API: `curl` to `/api?mode=queue` hung past an
8s timeout, and `docker logs nzbdav` showed a `System.Threading.Tasks.TaskCanceledException`
on every single `GetQueueController` call — EF Core's `RelationalConnection.OpenAsync` never
completing, i.e. nzbdav's own SQLite connection was deadlocked. Docker's healthcheck still
reported `healthy` throughout (its healthcheck doesn't exercise the same DB-backed queue path).

**Fix:** plain `docker restart nzbdav` (not `docker compose restart`, same rule as always —
avoid re-staling `nzbdav_rclone`'s dependents) cleared it immediately; SAB API responded
normally afterward and nzbdav's own queue showed 0 slots (it had dropped whatever was
in-flight when the DB deadlocked).

**Sonarr/Radarr both needed manual nudges afterward — the health flag and queue don't
self-heal just because the client recovers:**
- `POST /api/v3/downloadclient/test` on the client config clears nothing by itself.
- Radarr's stale "download clients unavailable" health entry only cleared after an explicit
  `POST /api/v3/command {"name":"CheckHealth"}`.
- Sonarr's cleared after `POST /api/v3/command {"name":"RefreshMonitoredDownloads"}`.
- Sonarr's queue still listed all 94 original items as `downloadClientUnavailable` ghosts
  (trackedDownloadState: null) even after the client was healthy again, since nzbdav's queue
  was empty post-restart — these don't correspond to anything nzbdav still knows about.
  Removing them via `DELETE /api/v3/queue/bulk` in one batch 500'd with `System.
  InvalidOperationException: Sequence contains no matching element` (Sonarr's
  `PendingReleaseService.FindPendingRelease` chokes if any id in the batch isn't a real
  pending release) — worked fine deleting one-by-one via `DELETE /api/v3/queue/{id}` instead.
  Removed with `blocklist=false` (they're not real failures, just orphaned by the restart,
  so let them redownload) vs. the 23 genuinely `failedPending` items in the same sweep, which
  were blocklisted per the existing standing practice.

**Takeaway:** don't assume "all download clients unavailable" + a stuck Sonarr/Radarr queue
is automatically the FUSE/mount landmine — check the mount independently first (it's a cheap
check), then check nzbdav's own SAB API responsiveness with a short curl timeout and its logs
before restarting anything. Docker's `healthy` status does not cover this failure mode.

## Pi-hole added as network-wide DNS, 2026-08-03 - REMOVED same day, see end of section

**REMOVED 2026-08-03, same day it was added** - user's explicit request ("reverse all
pi-hole changes and delete it from everywhere, I will take care of network level"). Every
change below was reverted: `pihole` service block deleted from `docker-compose.yml`,
`PIHOLE_WEBPASSWORD` removed from `.env`, `config/pihole/` deleted entirely, the
`CONTAINER_LABELS` dashboard entry removed from `control-panel/app.py` (rebuilt+redeployed),
and all three host-level DNS changes below undone in reverse order (NetworkManager
`dns=none` line removed → `/etc/resolv.conf` symlink removed → NetworkManager restarted to
regenerate the original NM-managed file → the `disable-stub-for-pihole.conf` drop-in deleted
→ `systemd-resolved` restarted to re-enable the stub listener). Confirmed `ss` shows the
stub back on `127.0.0.53`/`127.0.0.54`, `/etc/resolv.conf` matches its original pre-Pi-hole
content, host resolution works, and the whole stack was recreated again (`docker compose up
-d --force-recreate`, no service name) so every container's baked-in `resolv.conf` matches
the reverted host file too - same requirement as the original rollout, see below. Mount
verified clean afterward (1 mount, instant `ls`, no real D-state) since this recreate
cascade included `nzbdav`/`nzbdav_rclone` again. Router-side revert (whatever DNS setting
change the user made in Eero, if any) is the user's own responsibility, not done by this
session - the user was in the middle of that when they decided to reverse course, and
this repo has no visibility into what state the Eero was actually left in.

**Kept for history, everything below describes the now-removed setup:**

New `pihole` service (`pihole/pihole:latest`), `network_mode: host` - **not** `stacknet` +
published ports. Bridge mode was tried first and failed for a real, documented reason: every
query (even from a real LAN client, not just container-to-container traffic) gets NAT'd through
`docker-proxy` before reaching the container, so Pi-hole's FTL only ever sees the docker bridge
gateway IP as the source and logs `dnsmasq: ignoring query from non-local network` and drops it.
Host networking is Pi-hole's own documented recommendation for exactly this reason - confirmed
live, DNS resolution failed in bridge mode and worked immediately after switching.

**Two host-level changes were required, not just a compose service add** - this is the
part that makes this addition different from every other service in this stack, which only
ever needed docker-side changes:

1. `systemd-resolved`'s DNS stub listener had to be disabled
   (`/etc/systemd/resolved.conf.d/disable-stub-for-pihole.conf`, `DNSStubListener=no`) - it
   binds `127.0.0.53:53`/`127.0.0.54:53`, and despite `ss` only ever showing those specific
   loopback addresses (never `0.0.0.0:53`), a real bind attempt to `0.0.0.0:53` failed anyway
   confirmed via a raw Python socket test. A wildcard bind can't coexist with an existing
   specific-address bind on the same port - `ss`'s output was technically accurate and still
   misleading about whether `0.0.0.0:53` was actually free.
2. `/etc/resolv.conf` (a real file written by NetworkManager, not a symlink) pointed at the
   now-dead `127.0.0.53` stub. Fixed by setting `dns=none` in `/etc/NetworkManager/NetworkManager.conf`
   (stops NM from rewriting the file) and symlinking `/etc/resolv.conf` →
   `/run/systemd/resolve/resolv.conf` (systemd's own non-stub file with the real upstream
   nameservers, `74.40.74.40`/`74.40.74.41`).

**Real incident caused and fixed in the same session, worth knowing about if this ever needs
touching again:** disabling the stub broke DNS resolution for every container that bakes in
`/etc/resolv.conf` from the host at creation time - `plex` (`network_mode: host`, so it reads
the host file almost directly) and, more broadly, **every bridge-network container**, because
Docker's embedded resolver (`127.0.0.11` inside each container) bakes in `ExtServers` from the
host's `/etc/resolv.conf` *at that container's creation time*, not dynamically. Confirmed live:
`radarr` returned `SERVFAIL` on every external lookup until recreated. The host's own CLI tools
were never affected because `nsswitch.conf` uses the `resolve` NSS module (talks to
systemd-resolved directly, bypassing `/etc/resolv.conf` entirely) - so a check that only
confirms the *host* can still resolve DNS proves nothing about container-side resolution.
**Fix: `docker compose up -d --force-recreate` (no service name = every service) once the host
file is corrected**, not just the container being changed. Verified the FUSE mount came back
clean afterward (1 mount, instant `ls`, no D-state) since this cascade included
`nzbdav`/`nzbdav_rclone` - see this file's FUSE landmines sections before assuming a full-stack
recreate is safe to repeat casually.

**Password gotcha:** `WEBPASSWORD`/env-var password seeding only applies on a genuinely fresh
`/etc/pihole` - a first `up -d` attempt that fails after Pi-hole's first-run setup already
wrote `pihole.toml` (e.g. the port-bind failure above) leaves a persisted config that silently
ignores the env var on every later recreate (log: `Password already set in config file`). Fix
via `docker exec pihole pihole setpassword '<value>'` instead of trusting the env var once any
config has ever been written to the volume.

**Router-side work still required and NOT done by this session** - see README/AGENTS for the
end-user Eero steps: this host's IP (`192.168.4.20`, currently DHCP-assigned) needs a DHCP
reservation, and the router's handed-out DNS server needs to change from its default to this
host's IP. Until that happens, Pi-hole is fully functional but nothing on the network is
actually using it yet.

## ntfy added: shared push-notification sink for the Arr-family apps, 2026-08-09

Phase 1 of `PLANS.md`'s 7-service integration batch. Everything else in that plan (Speedtest
Tracker, Organizr, Scrutiny, GAPS-2, WatchState, PlexAniSync) is deliberately **not** built yet
- Bear asked for Phase 1 only this round.

**What it is:** `binwiederhier/ntfy`, container `ntfy`, host port 8700 (container 80). One
topic per app (`radarr-alerts`, `sonarr-alerts`, `radarr-anime-alerts`, `sonarr-anime-alerts`,
`prowlarr-alerts`), wired via each app's native Ntfy notification implementation (Radarr/
Sonarr/Prowlarr all ship one - confirmed against `/api/v3/notification/schema` /
`/api/v1/notification/schema` on the running instances, not assumed).

**Anonymous access is deliberate, not an oversight:** no auth-file configured. The stack isn't
exposed publicly, so open publish/subscribe was judged acceptable for this batch. Revisit if
that changes (port-forwarding, Tailscale exposure, etc).

**Config:** `./config/ntfy/etc/server.yml` (mounted, not baked into the image) sets
`cache-duration: 72h` - the unbounded default would grow `./config/ntfy/cache/cache.db`
forever. `./config/ntfy/cache` is the message cache; nothing here needs backing up (it's
disposable notification history, not state).

**Control Panel wiring:** `control-panel/services/ntfy/router.py` - `POST /api/ntfy/publish`,
`GET /api/ntfy/topics` (returns this stack's own known topics, not a live ntfy query - ntfy has
no server-side "list all topics" API by design, since that would leak every topic to anyone
with server access), `GET /api/ntfy/health`, and `POST /api/ntfy/setup-connections` (the
one-time - but safe to re-run, skips apps that already have a connection - wiring of all 5
Arr-family apps' Ntfy notification, done via each app's REST API rather than five rounds of
manual UI clicking).

**Real bug found and fixed during live verification, not just configured:** Radarr's
`/api/v3/notification` schema lists `accessToken`/`userName`/`password`/`tags`/`clickUrl` as
optional fields, but POSTing without them 400s with a misleading `Value cannot be null.
(Parameter 'source')` instead of naming the actually-missing field. Fix: send every field from
the schema, empty string/list for the unused optional ones. Also caught and fixed:
`setup-connections`'s "already configured?" check was hardcoded to `/api/v3/notification` for
every app, which 404'd against Prowlarr (it's `/api/v1/`) - now reads each app's real API
version from `ARR_APPS`/`PROWLARR_CFG` instead of assuming v3 everywhere.

**`stack-notify-test` updated, not duplicated:** it previously fired only the Discord webhook;
now `/api/notify/test` fires both Discord and ntfy (topic `media-stack-test`) and reports each
sink's result independently, so one sink being down doesn't hide whether the other still works.

**Live-verified, not just deployed:** published/subscribed a real message over ntfy's HTTP API;
triggered a real Radarr test notification and confirmed it landed on topic `radarr-alerts`
(payload had `title`/`message`/`priority` as expected); ran `setup-connections` against the
live stack and confirmed 5/5 apps connected; confirmed `stack-notify-test` reports
`{"discord": "sent", "ntfy": "sent"}` against the real webhook and the real ntfy container;
confirmed `health-monitor` reports ntfy green alongside every other service, zero regressions.

**Fish functions:** `stack-ntfy-publish <topic> <message>`, `stack-ntfy-topics`. Deployed as
plain copies to `~/.config/fish/functions/` (this host's actual deployment mechanism - no
symlink), confirmed callable from a real fish shell against the running stack.

**GAPS-2 scope decision, recorded ahead of Phase 5 actually being built:** when GAPS-2 (Phase 5)
is implemented, it scans **both** the general Radarr library and the anime Radarr (`radarr_anime`)
library for gaps - Bear confirmed this explicitly, overriding PLANS.md's stated default of
general-only. See `PLANS.md`'s Phase 5.2 for the full context this decision sits inside.

## Speedtest Tracker added: hourly ISP link monitoring, 2026-08-11

Phase 2 of `PLANS.md`'s 7-service integration batch. Phases 3-7 (Organizr, Scrutiny, GAPS-2,
WatchState, PlexAniSync) remain not built.

**What it is:** `lscr.io/linuxserver/speedtest-tracker` (pinned `v1.14.7-ls166` at deploy time,
tracked via `:latest`), container `speedtest-tracker`, host port 8701 (container 80). Runs an
Ookla speedtest hourly (`SPEEDTEST_SCHEDULE: "0 * * * *"`) - deliberately not upstream's 15-min
default, since a full speedtest saturates the link and 4x/hour is unnecessary noise for a
monitoring signal, not a benchmark tool.

**Admin bootstrap, not the manual "change default login" step PLANS.md originally called for:**
the image supports `ADMIN_NAME`/`ADMIN_EMAIL`/`ADMIN_PASSWORD` env vars, "only effective during
initial setup" per upstream docs (docs.speedtest-tracker.dev/getting-started/environment-variables).
Set via `SPEEDTEST_TRACKER_ADMIN_EMAIL`/`SPEEDTEST_TRACKER_ADMIN_PASSWORD` in `.env`, so there's
no default `admin@example.com`/`password` login sitting open even briefly.

**APP_KEY:** Laravel encryption key, generated once via `echo "base64:$(openssl rand -base64 32)"`
per upstream's own docker install docs, stored in `.env` as `SPEEDTEST_TRACKER_APP_KEY`. Losing
or rotating it after first boot breaks decryption of anything already encrypted with the old key
- treat it like any other irreplaceable secret, not a rotatable credential.

**API token provisioning - real deviation from PLANS.md 2.5's assumption:** the plan assumed the
Sanctum API token could be read back out of Speedtest Tracker's sqlite DB the same way Tautulli's
flat-file `config.ini` works. Confirmed false during implementation: Sanctum only ever stores a
SHA-256 *hash* of the token (`personal_access_tokens.token`), and the image ships without
`laravel/tinker` (`php artisan tinker` errors `Command "tinker" is not defined`), so there's no
in-container CLI path to mint one either. What actually worked: replicated Sanctum's own
`HasApiTokens::createToken()` algorithm from `vendor/laravel/sanctum/src/HasApiTokens.php` (40
random alnum chars + `hash('crc32b', ...)` of those 40 chars appended, sha256 of the full string
stored as the DB row's `token`, plaintext returned to the caller as `"{id}|{40chars}{crc}"`) and
inserted the row directly into `./config/speedtest-tracker/database.sqlite` from the host via
Python's stdlib `sqlite3` (the bind mount makes this reachable without needing a `sqlite3` binary
inside the container, which isn't present either). Abilities set to `["results:read",
"speedtests:run"]` - the exact ability strings the app's own controllers check via
`$request->user()->tokenCant('results:read')` /
`app/Http/Controllers/Api/V1/{Results,Stats,Speedtest}Controller.php`, confirmed by reading those
controllers directly rather than guessing from the docs. The resulting plaintext token is stored
in `.env` as `SPEEDTEST_TRACKER_API_TOKEN` - this is the only copy; if it's ever lost, the same
script needs re-running (or a new token minted via the web UI's own `/admin/api-tokens` page,
Sanctum tokens are cheap to create, there's no reason to guard this like the APP_KEY).

**Control Panel wiring:** `control-panel/services/speedtest_tracker/router.py` - `GET
/api/speedtest-tracker/latest` (most recent result), `GET /api/speedtest-tracker/history?days=N`
(client-side date filter - Speedtest Tracker's own `/api/v1/results` has no date-range query
param), `POST /api/speedtest-tracker/run` (out-of-schedule trigger). All three proxy Speedtest
Tracker's real `/api/v1/*` REST API with a `Bearer` token, confirmed against the live container's
own `app/Http/Controllers/Api/V1/*` source and `app/OpenApi/OpenApiDefinition.php`, not assumed
from third-party docs alone.

**Two real bugs found and fixed during live verification, not just configured:**

1. **Ookla CLI socket failure, every scheduled/manual run failed 100% of the time until fixed.**
   The image's bundled `speedtest` binary (1.2.0.84) opens an IPv6 socket as part of its
   candidate-server probe even though `stacknet`'s bridge network has no IPv6 route configured,
   and aborts with `{"error":"Cannot open socket"}` instead of falling back to IPv4. Fixed by
   adding `sysctls: [net.ipv6.conf.all.disable_ipv6=1, net.ipv6.conf.default.disable_ipv6=1]` to
   the container (its own netns only, not the host's) so the binary never attempts `AF_INET6`.
   Confirmed via `docker exec speedtest-tracker /usr/bin/speedtest --accept-license --accept-gdpr
   -f json` failing identically outside the app entirely, ruling out an app-layer bug.
2. **Residual flakiness after the IPv6 fix, root-caused to the CLI's own multi-server
   `--selection-details` probe, not this stack's network.** With IPv6 disabled, un-pinned runs
   still failed roughly half the time (`Connection refused` / `Cannot open socket` against
   whichever of ~10 candidate mirror servers answered slowest first). Pinning to two known-good
   nearby servers via `SPEEDTEST_SERVERS: "45389,49674"` (University of Rochester / GoNetspeed,
   both confirmed fast and reliable from this host) made every run succeed - 3/3 clean manual
   runs, then a clean scheduled-path run through the real app queue (343 Mbps down / 667 Mbps up,
   24.7ms ping). Revisit the pinned server IDs if either one degrades - `speedtest --servers`
   lists current candidates.

Also found and fixed: the router's `/history` route 500'd in production
(`TypeError: can't compare offset-naive and offset-aware datetimes`) because the *live* API
returns `created_at` as `"2026-08-12 02:15:00"` (space-separated, no offset - Laravel's default
cast) rather than the docs' `"2024-01-15T10:30:00Z"` example. Fixed by normalizing the separator
and treating a naive parse result as UTC; a regression test using the real live format was added
(`tests/control_panel/test_speedtest_tracker_router.py::test_history_filters_by_days`).

**Live-verified, not just deployed:** container came up healthy immediately (`start_period: 30s`
was generous - actual boot was under 20s); confirmed admin user bootstrapped correctly (real
`SELECT * FROM users` against the bind-mounted DB showed the configured email, not the upstream
default); provisioned the API token per above and confirmed it authenticates; after the two fixes
above, triggered a real speedtest through the app's own `POST /api/v1/speedtests/run` queue path
and confirmed it reached `status: "completed"` with real bandwidth numbers, readable through this
stack's own `GET /api/speedtest-tracker/latest` and `/history`; confirmed `health-monitor` reports
`speedtest-tracker` green alongside every other service, full 526/526 control-panel test suite
still green after both router changes.

**Fish functions:** `stack-speedtest-latest`, `stack-speedtest-history [days]`,
`stack-speedtest-run-now`. Deployed as plain copies to `~/.config/fish/functions/` (this host's
actual deployment mechanism), confirmed callable against the real running stack.

## Organizr added: single landing dashboard, fully script-provisioned, 2026-08-12

Phase 3 of `PLANS.md`'s 7-service integration batch. Phases 4-7 (Scrutiny, GAPS-2, WatchState,
PlexAniSync) remain not built.

**What it is:** `ghcr.io/organizr/organizr` (branch `v2-master`, upstream 2.1.5000), container
`organizr`, host port 8702 (container 80). One landing page with a tab per service, so the
stack has a front door that isn't a bookmark folder of 18 port numbers.

### Four things PLANS.md 3.x got wrong, all found by reading upstream source rather than docs

**1. "Manual by design" was wrong - tab provisioning is a full REST API.** PLANS.md 3.4 said
"Organizr has no tab-provisioning API; all tab state lives in its own SQLite DB. Do not attempt
to script this." `api/v2/routes/tabs.php` defines `GET/POST/PUT/DELETE /api/v2/tabs`.
`isApprovedRequest` (`api/classes/organizr.class.php:4596-4623`) accepts a `Token:` header equal
to the configured API key, treats that caller as admin, and short-circuits the CSRF formKey
check that would otherwise reject any non-browser POST. No SQLite poking needed.

**2. The first-boot wizard is scriptable too.** `POST /api/v2/wizard` is in `$GLOBALS['bypass']`
(`api/v2/index.php:41-52`), so it needs no auth at all, and `wizardConfig()` self-disables once
config and DB exist (`organizr.class.php:3016`). Critically, the wizard takes the API key as an
*input* - we choose it, Organizr doesn't generate it - which is what makes every later step
scriptable. So there is no manual setup step anywhere in this phase, and Organizr rebuilds from
a bare volume with one command.

**3. "No secrets required" was wrong.** PLANS.md 3.2 claimed none needed for base operation.
The wizard mandates an admin account and every route past `/ping` runs through
`qualifyRequest()`. Six new `.env` keys: `ORGANIZR_API_KEY`, `ORGANIZR_HASH_KEY`,
`ORGANIZR_ADMIN_USERNAME`, `ORGANIZR_ADMIN_EMAIL`, `ORGANIZR_ADMIN_PASSWORD`,
`ORGANIZR_REGISTRATION_PASSWORD`.

**4. Wrong image name, and a dead env var.** PLANS.md 3.1 specified `organizr/organizr:latest`;
the `docker-organizr` README lists that Docker Hub path (and `organizrtools/organizr-v2` before
it) as the legacy name `ghcr.io/organizr/organizr` replaced. Its `fpm: "false"` is also inert -
the base image is "now set up to use the unix socket exclusively". Dropped, `branch: v2-master`
kept because that one is real.

### Landmine: the API key must be exactly 20 characters

`isApprovedRequest` gates on `strlen($requesterToken) == 20` **before** it compares the value
(`organizr.class.php:4609`). A 19- or 21-char key doesn't produce a "bad key" error, it 401s
every write route with `Not authorized for current Route`, which reads like a permissions
problem and is not. Both `scripts/organizr-provision.py` and the control-panel router check the
length up front and fail with that explanation rather than letting Organizr mislead a future
session. `.env.example` carries the same warning plus a generator one-liner.

### Healthcheck uses /api/v2/ping, not /

`/api/v2/ping` is unauthenticated and hard-200s both before and after the wizard has run
(`api/v2/routes/ping.php`). `/` serves the setup wizard pre-setup and 302s to login after, so it
changes meaning at exactly the moment you'd want a healthcheck to be stable. Both the container
healthcheck and `health-monitor`'s probe use ping.

### The framing sweep, and why exactly one tab is New Window

PLANS.md 3.4 asked for a per-service `X-Frame-Options`/CSP check before enabling iframe mode.
That sweep ran against every live service on 2026-08-12, following redirects (several services
only reveal their real headers on the post-redirect 200):

| Result | Services |
|---|---|
| No framing headers - iframe fine | Plex (`/web`), Seerr, Radarr, Radarr Anime, Sonarr, Sonarr Anime, Prowlarr, Bazarr, Cleanuparr, Maintainerr, Lingarr, Tautulli, Wrapperr, ntfy, Speedtest Tracker, Control Panel |
| `X-Frame-Options: SAMEORIGIN` - refuses framing | **NzbDAV only** |

So NzbDAV is the single `type=2` (New Window) tab; the other 17 are `type=1` (iFrame). Organizr's
own values are 0=Organizr-internal, 1=iFrame, 2=New Window (`js/functions.js:4628-4641`).
`test_organizr_router.py::test_nzbdav_is_the_only_new_window_tab` asserts exactly this, so the
sweep result is encoded in the test suite rather than surviving as folklore in this document.

### Tab URLs use HOST_IP, never container names

Tab URLs are fetched by the *browser*, not by Organizr's PHP, so `http://radarr:7878` would
resolve inside stacknet and nowhere else. Every tab is `http://${HOST_IP}:<port>`. The sync
route refuses to run at all if `HOST_IP` is unset rather than emitting 18 broken tabs.

### Icons

Organizr's `image` column accepts either a path into its bundled icon set or a `<pack>::<name>`
token that `iconPrefix()` (`js/functions.js:555`) expands. The bundled set covers radarr,
sonarr, prowlarr, bazarr, plex, overseerr, tautulli and speedtest-icon; it has nothing for
nzbdav, cleanuparr, maintainerr, lingarr, wrapperr, ntfy or control-panel, so those use
FontAwesome 4 names (`fontawesome::bell` etc) rather than shipping image files into its volume.

### Layout

- `scripts/organizr-provision.py` - idempotent bootstrap: wizard, then tabs. Re-running reports
  "already configured" and "18 already present". Has `--dry-run`.
- `control-panel/services/organizr/tabs.py` - the canonical tab table, imported by both the
  provisioning script and the router, so there is exactly one definition. Adding a service to
  the stack means adding one row here and running `stack-organizr-sync`.
- `control-panel/services/organizr/router.py` - `GET /api/organizr/tabs`,
  `POST /api/organizr/tabs/sync`, `GET /api/organizr/health`.

`tabs/sync` is **additive only** by design: it never edits or deletes an existing tab, so a tab
hand-tweaked in Organizr's UI survives a sync and a deliberately-added stray tab isn't silently
reaped. A 409 (name taken) counts as a skip, not a failure.

**Tabs provisioned (18):** Plex, Seerr, Radarr, Radarr Anime, Sonarr, Sonarr Anime, Prowlarr,
Bazarr, NzbDAV, Cleanuparr, Maintainerr, Lingarr, Tautulli, Wrapperr, ntfy, Speedtest
Tracker, Control Panel. Plus Organizr's own two built-in `type=0` pages (Settings, Homepage),
which this stack does not manage. Deliberately absent, so a future session doesn't "notice the
gap": kometa, unpackerr, watchtower, prefetcharr and nzbdav_rclone publish no port and have no
web UI, and Organizr gets no tab pointing at itself.

All tabs are `group_id: 0` (admin-only). Organizr group levels count *down* to more privilege -
`qualifyRequest` passes when `userLevel <= needed` - and this is a single-operator stack with no
guest accounts.

**Tests:** `tests/control_panel/test_organizr_router.py`, 15 cases - auth gating on all three
routes, the 20-char key constraint, tab-list shaping and missing-tab reporting, additive sync,
409-as-skip, unset `HOST_IP`, and the three table-integrity tests (nzbdav is the only New Window
tab, every URL uses HOST_IP, tab names are unique). Full suite 654 passed, no regressions.
`ruff check control-panel/app.py scripts/*.py` clean.

**Fish functions:** `stack-organizr-tabs`, `stack-organizr-sync`. Deployed as plain copies to
`~/.config/fish/functions/`, confirmed callable against the real running stack.

**Doc backfill:** Phases 1 and 2 shipped without registering their functions in
`fish-functions/README.md` or `stack-help.fish`. Both were two phases behind; ntfy's and
Speedtest Tracker's functions were backfilled alongside Organizr's in this commit.

## Scrutiny added: S.M.A.R.T. trending for the host's single NVMe, 2026-08-12

Phase 4 of `PLANS.md`'s 7-service integration batch. Phases 5-7 (GAPS-2, WatchState,
PlexAniSync) remain not built.

**What it is:** `ghcr.io/analogj/scrutiny:latest-omnibus` (v0.9.3 at deploy time), container
`scrutiny`, host port 8703 (container 8080). Omnibus bundles the web UI, API and the metrics
collector, plus its own InfluxDB for the time-series data. Collector runs daily at midnight.

Layered on top of, not replacing, the existing `stack-disk-health` raw-`smartctl` check: that
one answers "is the disk okay right now", Scrutiny answers "is it getting worse".

### Scope reality: this host has exactly one physical disk

PLANS.md 4.1 assumed a multi-disk SATA array and used `/dev/sda` + `/dev/sdb` as its example.
`lsblk -d` on this host shows a single 954GB NVMe (Bestoss GM988H 1TB, serial
UB988KH7Q261KN00098) plus `zram0`, which is compressed RAM swap and not a real disk. Everything
else the stack serves lives on the Usenet-backed FUSE mount, which has no SMART data to trend.

So the value here is narrower than the plan imagined but still real: wear tracking on the one
disk the entire stack runs on. Baseline at deploy: **5% used, 100% spare remaining, 0 media
errors, 0 critical warnings, 43C, 2083 power-on hours, 31 unsafe shutdowns.** That last number
is consistent with this stack's FUSE-hang-and-reboot history and is worth watching, though
nothing about it is currently alarming.

### Three PLANS.md 4.x corrections

**1. The device to pass through is `/dev/nvme0`, not a block device.** `smartctl --scan` on this
host returns `/dev/nvme0 -d nvme` — the NVMe *controller character device*. Upstream's README
says to pass exactly what `--scan` lists. PLANS.md's `/dev/sdX` block-device shape would have
registered nothing. `/dev/nvme0n1` is passed as well so the collector can read block-device
metadata via udev, but `/dev/nvme0` is the one that matters.

**2. `SYS_ADMIN` is mandatory here, not conditional.** PLANS.md 4.1 said "If any host disk is
NVMe, also add `cap_add: [SYS_ADMIN]`". Every disk here is NVMe, so it is required:
`smartctl` needs the NVMe admin passthrough ioctl, which `SYS_RAWIO` alone does not cover
(upstream README, `AnalogJ/scrutiny#26`). Without it Scrutiny registers the device and then
reports no SMART data at all — a silent-empty failure, not an error. This is a genuine
privilege grant to the container; it is the documented minimum for NVMe and still narrower
than `--privileged`.

**3. Four fish functions shipped, not 4.4's two.** `stack-scrutiny-collect` exists because
otherwise the only way to see whether collection works is to wait until midnight.
`stack-scrutiny-alert-test` exists because of the notification wiring below.

### Beyond the plan: disk-failure alerts route into ntfy

Not in PLANS.md at all, but Phase 1 built a notification sink and Scrutiny speaks shoutrrr
natively, so `docker-compose.yml` carries:

```yaml
SCRUTINY_NOTIFY_URLS: "ntfy://ntfy:80/scrutiny-alerts?scheme=http"
```

`scheme=http` is required because shoutrrr's ntfy service defaults to https/443 and stacknet has
no TLS.

**This started as a `config/scrutiny/config/scrutiny.yaml` file and was moved to an env var
mid-implementation, for a reason worth reusing:** this repo gitignores `config/` wholesale
(`.gitignore:16`), so any wiring that lives in a config file under there exists only on this
host and silently vanishes on a rebuild. The same is quietly true of ntfy's own
`config/ntfy/etc/server.yml` from Phase 1. Scrutiny's config is viper-backed with
`SetEnvPrefix("SCRUTINY")` and a `.`→`_` key replacer, and `notify.urls` has a registered
default (`webapp/backend/pkg/config/config.go:42`), which is what makes `AutomaticEnv` resolve
`SCRUTINY_NOTIFY_URLS`. Every other setting Scrutiny needs is already its own default, so the
config file was deleted entirely rather than kept for two keys — Scrutiny now boots on
`No configuration file found ... Using Defaults` plus that one env var, and the whole service
is reproducible from the committed compose file.

**Prefer an env var over a file under `config/` whenever the app supports it.** Verified
end-to-end after the switch, not assumed: `stack-scrutiny-alert-test` fires Scrutiny's own
`POST /api/health/notify`, and the message was confirmed landing on the `scrutiny-alerts` topic
by polling `http://localhost:8700/scrutiny-alerts/json?poll=1`. Scrutiny's test payload
references a fake `/dev/sda` with serial `FAKEWDDJ324KSO` — that is upstream's hardcoded test
device, not a real disk on this host.

Note Scrutiny answers **HTTP 200 with `success: false`** when a notify URL is broken, so the
router checks the body rather than relying on `raise_for_status`. A bare status check would
report a working alert path that silently isn't.

### Landmine: `detail` is a reserved key in this stack's API responses

Real bug, caught live during verification and *not* by the router's own tests. `__stack_api`
(`fish-functions/__stack_api.fish`) unwraps any top-level `detail` dict as FastAPI's
`HTTPException` envelope. A **success** payload carrying `detail` is therefore mistaken for an
error body, and the CLI prints raw JSON instead of the message. The alert-test route originally
returned `detail=body`; renamed to `scrutiny_response`.

The router was correct in isolation and only wrong through the CLI, which is the interesting
part — no unit test of that route would have caught it. There is now a shape test
(`test_no_success_route_returns_a_top_level_detail_key`) asserting that no Scrutiny success
response carries a top-level `detail` key. **Any new route in any service should avoid `detail`
as a response key.**

### Convenience: disk identifiers resolve

Scrutiny's own API only accepts its internal UUID (`500c6e6d-9dcd-584c-81e9-32a13f8f55c1` here),
which nobody has memorised and which changes if a device is re-registered.
`GET /api/scrutiny/disk` accepts a UUID, a device name (`nvme0`), or a serial, case-insensitive,
and resolves it against the summary first. With exactly one disk registered the argument is
optional entirely. With more than one it becomes required and the error names the candidates.

`stack-scrutiny-disk` surfaces only the six attributes that actually predict end-of-life
(`critical_warning`, `available_spare`, `percentage_used`, `media_errors`, `unsafe_shutdowns`,
`num_err_log_entries`) out of the 16 Scrutiny tracks for NVMe. The rest are raw counters
(`host_reads`, `data_units_written`) that only mean something as a trend line in the web UI.
Anything Scrutiny itself flags is reported regardless of whether it is in that six.

### Image tag

`latest-omnibus`, matching this repo's dominant convention (watchtower updates nightly at 04:00
and posts to Discord). Upstream's README warns against `latest-` tags generally, but surprise
updates with notification are this stack's deliberate, stack-wide answer to that problem, and
making one service the exception adds a stale-pin nobody will remember to check. Noted here so
the deviation from upstream advice is a decision on the record rather than an oversight.

**Tests:** `tests/control_panel/test_scrutiny_router.py`, 23 cases — auth gating on all four
routes, summary shaping, healthy-vs-failing classification, no-disks-yet vs unreachable,
identifier resolution across UUID/name/serial/case, the single-disk default, the multi-disk
requirement, 404 on unknown, wear-attribute filtering, flagged-attribute reporting, collector
exit codes, the `success: false` notification path, and the `detail`-key shape test. Full suite
677 passed, no regressions. `ruff` clean.

**Fish functions:** `stack-scrutiny-summary`, `stack-scrutiny-disk [id]`, `stack-scrutiny-collect`,
`stack-scrutiny-alert-test`. Deployed as plain copies to `~/.config/fish/functions/`, all four
confirmed callable against the real running stack.

---

## GAPS-2 added: collection/franchise gap detection, 2026-08-12

> **Scope reduced later the same day** — the anime libraries were removed and
> GAPS-2's own Radarr/Sonarr were wired up. Everything below describes the
> build as first shipped; see "GAPS-2 scope cut to Movies and Shows" at the
> end of this file for the current state.

Phase 5 of PLANS.md's 7-service batch. Finds titles that belong to a collection (movies, via
TMDB) or a franchise (TV, via TheTVDB) where the library owns some entries but not others — the
third Alien film when you have the other two — and pushes a chosen one into the right Arr
instance. Host port **8704**, container port 4277, image `primetime43/gaps-2:latest` (2.10.0 at
time of writing).

### The constraint that shaped everything: GAPS-2 is single-instance

GAPS-2 stores exactly **one** Radarr connection and **one** Sonarr connection (`CONFIG_KEY =
'radarr'` / `'sonarr'` in its own service modules). This stack runs four Arr instances, split
general/anime. Bear's locked decision from 2026-08-09 was that GAPS-2 must cover both general
and anime.

Those two facts can't both hold inside GAPS-2, so the integration splits responsibilities:
**GAPS-2 detects, the control panel routes.** Three consequences worth knowing before touching
any of this:

1. **GAPS-2's own Radarr/Sonarr are deliberately left unconfigured.** Not an oversight, and not
   a step the provisioning script forgot. If a single Radarr were configured, GAPS-2's web UI
   would grow an Add button that files every title — anime included — into that one instance
   under its root folder and quality profile. The add succeeds; it just lands in the wrong
   place, with nothing in the UI to indicate it. Leaving them unset makes that mis-file
   structurally impossible rather than merely discouraged.
2. **Scans run one Plex library at a time.** GAPS-2's scan accepts a `libraryNames` *list* and
   merges the owned titles from all of them into one deduplicated result. Its progress and
   history structures record `libraries` at the scan level, and the gap objects themselves carry
   no library field (`services/scan_progress.py`, `services/scan_history.py`). So a merged
   Movies + Anime Movies scan produces gaps that cannot be attributed back to a library and
   therefore cannot be routed. One library per scan makes each completed scan a scan-history
   entry tagged with exactly one library name, and that is where attribution comes from —
   GAPS-2's own persisted history, not a cache maintained on our side.
3. **`/api/gaps2/push` ignores GAPS-2's `/api/radarr/add` entirely** and calls the correct
   instance through `core.arr_client`'s existing `radarr_add_movie` / `sonarr_add_series`
   helpers. The routing table lives in `control-panel/services/gaps2/libraries.py`, imported by
   both the router and the provisioning script so it has one definition.

| Plex library | Kind | Target instance |
|---|---|---|
| Movies | movie | `radarr` |
| Anime Movies | movie | `radarr_anime` |
| Shows | show | `sonarr` |
| Anime Shows | show | `sonarr_anime` |

`test_gaps2_router.py` asserts all four mappings individually rather than spot-checking, because
a regression there is silent: the add succeeds, it just goes to the wrong library.

### Four things PLANS.md 5 got wrong

All four found by reading upstream source rather than trusting its docs.

- **The scan never touches the FUSE mount.** PLANS.md 5's headline risk was "a single
  library-wide filesystem walk over the FUSE mount can run tens of minutes", with instructions to
  read `fuse-hang-vs-slow-diagnosis` before picking a schedule. That is a different shape of
  operation than the one GAPS-2 performs: it pulls the owned-title list from Plex's own API and
  then does TMDB/TheTVDB metadata lookups. The real cost is third-party API round-trips. Measured
  on this stack: the full four-library sweep, including 16,873 owned movies, completed in about
  four minutes total.
- **No Plex OAuth.** PLANS.md 5.2 called the Plex credential an "OAuth login flow (interactive,
  one-time)". `POST /api/plex/connect-manual` takes a plain `{serverUrl, token}` and never touches
  OAuth, so the existing `PLEX_URL`/`PLEX_TOKEN` seed it. Combined with GAPS-2 shipping no auth of
  any kind, the entire service provisions headlessly — no browser step anywhere in this phase.
- **`TMDB_API_KEY` doesn't exist in this stack**; the key is `TMDB_KEY`. `TVDB_KEY` was already
  present too (poster sync uses it), so the TV scope Bear added on top of PLANS.md's movies-only
  scope needed no new credential.
- **PLANS.md 5.3's `/` healthcheck would have been wrong.** `/` is served by the bundled Angular
  frontend and answers 200 with a dead Flask backend behind it — the exact failure mode PLANS.md's
  own `verify-image-version-before-headless-config` note warns about. The healthcheck and the
  health-monitor probe both use `/api/about`, which the backend answers and which needs no
  configuration. `wget`, not `curl`: the image is `python:3.11-slim` and installs wget (for gosu),
  never curl.

### Scope: TV as well as movies

PLANS.md 5 scoped this to movies. The image ships a full Sonarr blueprint and TheTVDB franchise
gap-finding, and Bear chose to enable both (2026-08-12). Movies and TV are separate halves of the
API throughout — separate scan endpoints, separate progress trackers, separate id fields (`tmdbId`
vs `tvdbId`) — so `ENDPOINTS` in the router keys them by media kind rather than branching inline.
Crossing them would send a tvdbId to Radarr's tmdb lookup, which resolves to an unrelated title
rather than failing; there's a test for that specifically.

### Secrets

`GAPS2_CONFIG_KEY` in `.env`, the Fernet key GAPS-2 uses to encrypt `config.enc`. Set as an env
var rather than letting it generate its own `data/.config.key`, because this repo gitignores
`config/` wholesale — a generated keyfile would exist only on this host, and a `config/` wipe
would strand an undecryptable `config.enc`. `config_store._resolve_key()` checks the env var
first, then the keyfile, then generates. Verified live: no `.config.key` is created.

Same env-var-over-config-file rule Phase 4 landed on, and the second phase in a row where it
applied. Worth carrying into Phases 6-7.

### Notifications: none, deliberately

Phase 4 wired Scrutiny's disk alerts into the ntfy sink. GAPS-2 cannot do the same — its
notification service supports Discord, Telegram and email only, with no ntfy and no generic
webhook provider (`services/notification_service.py`). Bear's call (2026-08-12) was to skip
notifications rather than build a translation bridge: a missing-movie list is advisory, not an
alert condition. Recorded here so a future session doesn't go looking for the wiring or assume
it was forgotten.

### Backup

`config/gaps2/` holds `config.enc`, which carries the Plex token and both metadata API keys, plus
the cached scan history. PLANS.md 5.1 flagged this volume as needing backup coverage and 5.7 had
an acceptance box for confirming it. restic was removed on 2026-08-12, so there was no mechanism
to confirm against; Bear's instruction was to fold it into `stack-claude-full-backup`. No change
was needed — that function tars all of `~/Claude` with no excludes, so the directory is covered
the moment it exists. Verified rather than assumed. Note it is a manual, on-demand backup with no
timer behind it.

### Root-folder resolution relies on radarr-anime having one root folder

`radarr_root_folder_and_profile` looks for `/data/movies` by name and otherwise falls back to
`folders[0]`. radarr-anime has exactly one root folder (`/data/anime-movies`), so the fallback
lands correctly — but by fallback, not by intent. If radarr-anime ever gains a second root folder,
ordering decides where pushes land. Same applies to sonarr-anime and `/data/shows`.

### Live verification

- All four libraries scanned: Movies 16,873 owned / 994 gaps, Anime Movies 754 / 286, Shows 1,305
  / 219, Anime Shows 531 / 35. 1,534 gaps total.
- Attribution confirmed live: every Anime Movies gap tagged `radarr_anime`, TV gaps tagged with
  `tvdbId` and their Sonarr instance.
- One controlled push: `stack-gaps2-push 375177 "Anime Movies"` → "Aria the Avvenire" landed in
  **radarr-anime** at `/data/anime-movies/Aria the Avvenire (2015)`, and was confirmed **absent**
  from the general Radarr. Both halves checked — landing in the right place and not in the wrong
  one are different assertions.
- Container healthy, zero errors in logs, 145 MiB of its 1 GiB limit after the full sweep.
- health-monitor green; whole-stack sweep shows no regressions elsewhere.

**One real bug, caught only by live verification:** `stack-gaps2-missing "Anime Movies"` built its
query string by hand and curl rejected the URL outright — three of the four library names contain
a space. Now built with `urllib.parse.urlencode`. The router was correct in isolation and the
tests passed; the failure existed only through the CLI. Same class of miss as Phase 4's `detail`
key.

**Tests:** `tests/control_panel/test_gaps2_router.py`, 33 cases — auth gating on all four routes,
the routing table (every mapping individually, plus that each named instance really exists in
`ARR_APPS`), status shaping, never-scanned vs zero-gaps, per-gap Arr attribution, correct id field
per media type, owned-entry exclusion, multi-library scans being ignored for attribution, limit vs
total, unknown-library rejection on all three routes, all four push mappings, movie/show path
crossing, pushing an id from the wrong library, never-scanned push refusal, Arr rejection
surfacing, blank-library-means-all, and sweep overlap. Full suite **710 passed**, no regressions
(677 baseline + 33).

**Running the test suite on this host:** there is no system `httpx` and no committed venv. Use
`uv`: `uv venv .venv-test --python 3.13 && uv pip install --python .venv-test -r
control-panel/requirements.txt pytest beautifulsoup4 plexapi`, then `.venv-test/bin/python -m
pytest`. `beautifulsoup4` and `plexapi` are needed by `tests/scripts/` and are not in
`control-panel/requirements.txt`. `.venv-test/` is gitignored.

**Fish functions:** `stack-gaps2-status`, `stack-gaps2-scan [library] [--full]`,
`stack-gaps2-missing [library] [limit]`, `stack-gaps2-push <id> <library>`. Deployed as plain
copies to `~/.config/fish/functions/`, all four confirmed callable against the real running stack.


## GAPS-2 scope cut to Movies and Shows, 2026-08-12

Bear's call, hours after the section above shipped. GAPS-2 no longer covers
**Anime Movies** or **Anime Shows**. Collection/franchise detection is a poor
fit for anime: TMDB collections and TheTVDB franchises model seasons, OVAs,
specials and recap films inconsistently, so most of the 321 anime gaps the
first sweep found were metadata artefacts rather than titles worth grabbing.

### The single-instance constraint stopped biting

The whole shape of the original integration came from GAPS-2 holding exactly
**one** Radarr and **one** Sonarr connection while four Arr instances needed
covering. Drop the anime libraries and there is one Radarr and one Sonarr in
scope, which is exactly what GAPS-2 can hold. Two consequences:

1. **GAPS-2's own Radarr/Sonarr are now configured**, reversing the deliberate
   omission documented above. `scripts/gaps2-provision.py` wires
   `http://radarr:7878` and `http://sonarr:8989` (docker-network addresses —
   GAPS-2 is the client, so localhost would resolve to the gaps2 container
   itself) with the same root folder and quality profile the panel's push
   picks, so GAPS-2's own Add button and `stack-gaps2-push` land a title in
   the same place. Live: `/data/movies` + profile "Anything" (id 16) on
   Radarr, `/data/shows` + "Anything" (id 19) on Sonarr.
2. **The routing table stays anyway.** `/api/gaps2/push` still goes through
   `core.arr_client` rather than GAPS-2's `/api/radarr/add`, because that is
   what names the destination instance in the response, reuses the stack-wide
   root-folder/profile defaults, and rejects an uncovered library instead of
   adding it somewhere by default.

`auto_route_by_decade` is explicitly written as `false`. It routes an add to
whichever root folder's path contains the title's decade; both instances have
one flat root folder, so leaving it on would make every add depend on a path
match that never succeeds.

### Removing the libraries was not enough on its own

Taking the anime entries out of `libraries.py` stops the control panel
scanning, listing or pushing them — every gaps2 route derives its target from
that table — but GAPS-2 keeps what it already found. Five anime scan-history
entries stayed in `scan_history.json`, and `last_tv_scan.json` was an "Anime
Shows" scan, so GAPS-2's own dashboard still rendered 35 anime gaps. Harmless
before this change; not harmless after it, because those rows now carry a
working Add button pointed at the general Sonarr.

`scripts/gaps2-prune-history.py` (new) drops them: history entries naming any
uncovered library go, and a `last_scan.json` / `last_tv_scan.json` belonging
to one is **deleted rather than emptied** — a missing sidecar reads as "never
scanned", an empty gap list reads as "scanned, nothing missing", and those
mean opposite things. Backs up each file first and rewrites via temp file +
`os.replace`. Run with the gaps2 container stopped; a scan completing
mid-prune would rewrite the file the script has already read.

Ran live: 5 entries dropped, 4 kept, `last_tv_scan.json` deleted (GAPS-2 now
falls back to the Shows scan for its TV dashboard). Container healthy after
restart, no errors in the log.

### Live verification

- `stack-gaps2-status` → "Idle. 1148 missing title(s) across 2 libraries."
  (Movies 929, Shows 219).
- `stack-gaps2-missing "Anime Movies"` and `stack-gaps2-push 375177 "Anime
  Movies"` both → `Unknown library 'Anime Movies'. Known: Movies, Shows.`
- `stack-gaps2-missing Movies 3` and `stack-gaps2-missing Shows 2` still
  answer normally.
- GAPS-2's `/api/radarr/config` and `/api/sonarr/config` both `enabled: true`
  with the root folder and profile above.
- `scripts/gaps2-provision.py --dry-run` reports the two Arr connections and
  writes nothing; a real re-run is a plain overwrite.

The earlier note about root-folder resolution relying on radarr-anime having
exactly one root folder no longer applies to GAPS-2 — it never reaches the
anime instances now. It still applies to every other caller of
`radarr_root_folder_and_profile`.

**Tests:** `tests/control_panel/test_gaps2_router.py` re-cut to two libraries
(31 cases), including one asserting the anime libraries stay out of the table
— re-adding one is not a no-op now that a general instance is wired.
`tests/scripts/test_gaps2_provision.py` (12 cases) covers the Arr wiring, and
the regression that motivates its two-phase save: GAPS-2's `save_config` is a
wholesale overwrite, not a merge, and the root-folder/profile lookups read the
stored config, so the second save has to re-send the credentials or it wipes
them. `tests/scripts/test_gaps2_prune_history.py` (10 cases) covers the prune,
its backup, and its dry run. Full suite **730 passed** (710 before, minus the
2 router cases the smaller table folds away, plus 22 new).

**Restart needed:** `docker compose build control-panel && docker compose up -d
control-panel` (done). GAPS-2 itself only needed the stop/start around the
prune.


## WatchState added: Plex watch-state sync, 2026-08-12

Phase 6 of PLANS.md's 7-service batch. Keeps its own record of what has been
watched, fed from Plex two ways at once. Host port **8705**, container port
8080, image `ghcr.io/arabcoders/watchstate:latest` (v1.10.2 at time of
writing). Everything provisions headlessly - no browser step anywhere.

### Both feeds stay on, deliberately

A scheduled import (`WS_CRON_IMPORT`) AND a Plex webhook. Upstream's README
says to keep the scheduled import enabled even when every backend supports
webhooks, because webhooks drop events. PLANS.md 6.4 says the same
independently. This is not redundancy to clean up in a later pass - removing
either one loses watch history silently, which is the failure mode with no
symptom until someone goes looking for an episode that was never recorded.

Import cadence is `25 0-1,6-23 * * *`: hourly at :25, **skipping 02:00-05:59**.
That window already holds the poster sync (02:00), the Arr backup (03:40), the
Letterboxd sync (04:00), the Sunday docker prune (04:30) and Plex's own Butler
tasks. An import walks every library, and this stack has confirmed SQLite write
contention when Plex's DB takes concurrent write pressure from several
directions at once (see `plex-marked-deleted-db-contention`).

Export is off. It writes watch state back *into* Plex, and with Plex as the
only backend there is nothing to write back from - an accidental export is a
mass write against the same DB the cadence above exists to protect.
`stack-watchstate-status` reports `export_enabled` for exactly that reason.

### Four things the API demanded that its errors do not explain

1. **`uuid` is required on `POST /v1/api/backends`.** WatchState sends the
   backend's uuid as Plex's `X-Plex-Client-Identifier` header. Omit it and the
   add fails with "X-Plex-Client-Identifier is missing" from a users-list call
   several layers down. Fetch it from `/v1/api/backends/uuid/plex` first.
2. **`user` is required too** - the numeric Plex account id - and the users
   list call needs that same uuid to answer at all. Without it the add fails
   with `Did not find matching user id '{id}'`: the literal placeholder,
   unsubstituted. The script picks the **admin** account, not the first one;
   this server also has a restricted `guest` account, and tracking that one
   would record whatever the guest watched as Bear's own watch state.
3. **The webhook URL is the host IP, not `http://watchstate:8080`.** PLANS.md
   6.4 assumed the docker-network address, but plex runs `network_mode: host`
   and cannot resolve container names. It is
   `http://HOST_IP:8705/v1/api/webhook?apikey=<the backend's own webhook
   token>` - one endpoint serves every backend and the token is what says
   which one is posting, so it must come from WatchState's own response
   (`urls.webhook`) rather than being hand-built.
4. **Registering the webhook is scriptable.** `POST
   /v1/api/backend/plex/webhook` drives WatchState's AddWebhook action against
   plex.tv. It appends, leaving the five webhooks already registered there
   (Trakt, MDBList, and this stack's own) untouched.

`scripts/watchstate-provision.py` does all of it and is safe to re-run: an
existing backend is reported and **left alone**, never recreated, because a
fresh add issues a new webhook token and Plex would keep posting to the old
one - the webhook stops working while everything still reports healthy.

### An import is queued, not run

`POST /v1/api/tasks/import/queue` enqueues an event; a separate dispatcher
(`events:dispatch`, every minute, hidden and not disableable) runs it. So
`stack-watchstate-import-now` answers "queued" and never "done", and the
result shows up in `stack-watchstate-status`. An empty history is a **404 with
an error body**, not an empty list - the normal state before the first import
finishes, so the router translates it to zero rather than a failure.

### Auth

`WS_API_KEY` in `.env`, with `WS_SECURE_API_ENDPOINTS: "true"` in the compose
block - without that flag the entire `/v1/api` surface is unauthenticated to
anything that can reach the port, including the endpoints that hand back
backend tokens. Every call sends it as the `X-apikey` header (WatchState also
accepts `?apikey=` and a bearer token; the header keeps it out of its own
access log). `WS_SYSTEM_SECRET` signs WatchState's internal tokens. Both are
env vars rather than self-generated files, same rule Phase 4 landed on, since
`config/` is gitignored wholesale.

`user: "${PUID}:${PGID}"` in the compose block is load-bearing: the image runs
rootless and exits outright if it cannot write `/config`.

The healthcheck hits `/v1/api/system/healthcheck`, not `/` - `/` is the bundled
WebUI and answers 200 with a dead backend behind it, the same failure mode
Phases 4 and 5 both hit. That endpoint answers 200 unauthenticated even with
`WS_SECURE_API_ENDPOINTS` on, which is why the health-monitor probe needs no key.

### Live verification

- First import: **100,203 items** tracked, finished 17:58:39.
- Webhook: 27 `POST /v1/api/webhook` entries from `PlexMediaServer/1.43.3` in
  WatchState's access log, all 200. A deliberate re-scrobble of an
  already-watched episode produced a delivery at 18:00:26, seconds later - the
  webhook path proven separately from the import path, per PLANS.md 6.7.
- `stack-watchstate-status` → "Idle. 100203 item(s) tracked, last import
  2026-08-12T17:58:39-04:00, next 2026-08-12T18:25:00-04:00."
- `stack-watchstate-history "Squid Game" 3` → 15 matches, showing 3.
- health-monitor sweep green across all 18 HTTP services.

**Tests:** `tests/control_panel/test_watchstate_router.py` (19 cases) and
`tests/scripts/test_watchstate_provision.py` (12 cases). The interesting ones
cover the places WatchState's API says something that reads like the opposite
of what it means: an empty history arriving as a 404, an import that is queued
rather than run, `updated` being a unix int and `watched` a 0/1 int, and the
re-run path that must not re-add a backend.

**Restart needed:** `docker compose build control-panel && docker compose up -d
control-panel` - a new `services/<name>/` directory needs the image rebuilt,
not just recreated. Done.

## PlexAniSync added: Plex anime watch state to AniList, 2026-08-13

Phase 7 of PLANS.md's 7-service batch, and the last of it - the batch is
complete. No host port, no web UI, no API: it is a container that syncs once
and exits, fired four times a day by a systemd timer. Image
`ghcr.io/rickdb/plexanisync:latest`. AniList account **TheVeryAngryDaddy**.

### LANDMINE: the AniList token expires 2027-08-13

`PLEXANISYNC_ANILIST_TOKEN` is a 1-year AniList OAuth access token. There is no
non-interactive way to renew it - no refresh token, no API call, no service
account. It has to be fetched by a human, logged into AniList, from:

    https://anilist.co/api/v2/oauth/authorize?client_id=1549&response_type=token

**Issued 2026-08-13, expires 2027-08-13.** When it lapses the sync does not
announce itself: the container exits non-zero and anime watch state silently
stops flowing, with Plex and everything else still perfectly healthy. Two
places will say so if anyone asks - `stack-plexanisync-last-run` reports
`token_expired: true` and names the renewal, and the health-monitor sweep's new
"Scheduled jobs" section fails the freshness check. The systemd
`OnFailure=notify-failure@` hook fires too. Do not spend an afternoon
re-diagnosing this a year from now.

### It is a one-shot; the timer owns the schedule

`INTERVAL=0` in docker-compose.yml. Upstream's default (3600) turns the
container into its own sleep-loop scheduler, which would have quietly competed
with the timer; `<=0` means sync once and exit. `systemd/plexanisync.timer`
runs at **00:45 / 06:45 / 12:45 / 18:45** - 20 minutes off WatchState's ":25"
import so the two never walk Plex's libraries in the same minute, entirely
outside the 02:00-05:59 maintenance window (poster sync, Arr backup, Letterboxd
sync, docker prune, Plex Butler), and off stack-poster-sync-movies' 06/14/22.
Same SQLite-contention reasoning as WatchState's cadence.

Both triggers re-*start* one persistent-but-stopped container rather than
creating a fresh one: the timer via `docker start --attach` (exit code and
output land in the journal), the control panel via the Docker SDK. `compose run
--rm` was the obvious design and is wrong here - it discards the logs, and the
logs are the only thing `/api/plexanisync/last-run` has to read. Sitting in
`Exited(0)` between runs is the healthy state, which is why its fleet tile and
`SERVICE_META` carry no health dot (same as kometa).

### Scope: both anime libraries, neither general one

`PLEX_SECTION="Anime Shows|Anime Movies"` (Plex sections 7 and 6, fed by
sonarr-anime/radarr-anime). Pipe-separated is upstream's multi-library syntax.
The general "Shows"/"Movies" libraries must never appear here - they would push
non-anime titles to AniList.

### Config is env vars; the one mounted file is untracked

There is no settings.ini and no config directory - PLANS.md 7.1's `/app/config`
does not exist. Everything is env vars, which sidesteps the trap Phases 4, 5
and 6 each hit (config/ is gitignored wholesale, so a mounted config file lives
only on the live host). The exception is
`config/plexanisync/custom_mappings.yaml`, which is mounted at
`/plexanisync/custom_mappings.yaml`, read fresh every run, and *is* untracked
for that same reason. Its entire baseline is two `remote-urls` entries pointing
at the community mapping lists; the file documents its own recreation at the
top. `LOG_FAILED_MATCHES=True` writes unmatched titles to
`/plexanisync/failed_matches.txt` inside the container, which is the input for
curating local overrides.

### Side fix: the control panel had been reporting UTC as local

Found while reading this feature's own output - a 12:07 run reported as 16:07.
The control-panel container had no `TZ`, so `core/responses.now()`'s
`.astimezone()` resolved to UTC, meaning *every* `"time"` field the panel has
ever returned was 4-5 hours off, unlabelled. `TZ: ${TZ}` added to its compose
environment. Not Phase 7 scope, but it was Phase 7's bug to find.

### Live verification (2026-08-13)

- First run, triggered through the real systemd unit (`systemctl --user start
  plexanisync.service`): 826 series in Anime Shows + 756 in Anime Movies read,
  3 watched series found, 3 matched, 0 unmatched, exit 0, `Result=success`.
- Confirmed on AniList's own API, not just in the logs: Cowboy Bebop CURRENT
  progress 25, The Animatrix CURRENT progress 1, Dragon Ball Z COMPLETED
  progress 291 - the last one through a custom mapping collapsing 9 Plex
  seasons onto anilist-id 813.
- `stack-plexanisync-last-run` → "Last run succeeded at 2026-08-13T12:07:19
  -04:00: 3 watched series in Plex, 3 matched on AniList, 0 unmatched."
- `systemctl --user is-enabled plexanisync.timer` → enabled, next 12:45.
- health-monitor sweep: 46/46 green, including the new scheduled-jobs section.

**Tests:** `tests/control_panel/test_plexanisync_router.py` (17 cases) and
`tests/scripts/test_health_monitor_timers.py` (9 cases). The parser is pinned
to a verbatim excerpt of the real run's log, not to invented wording - the
first draft guessed at "Successfully matched N titles" summary lines that
PlexAniSync never emits. The cases that matter cover the readings that look
right and are not: `Exited(0)` as healthy rather than down, exit 0 *without*
the "sync finished" line as a run that died partway, a stated total that failed
to parse as unknown rather than 0, and a timer that succeeded three days ago as
stale rather than fine.

**Restart needed:** `docker compose build control-panel && docker compose up -d
control-panel` (new `services/<name>/` needs a rebuild, and the TZ change needs
the recreate). Done. Timer installed and enabled as a *user* unit - no sudo
anywhere in this phase.

---

## CLI naming cleanup: the repo is now the enforced source of truth, 2026-08-13

Phase 8 of PLANS.md, the deferred one. Two halves: 8a made the command surface
trustworthy, 8b renamed the 12 names that broke the schema. Design and the
decisions behind it: `docs/superpowers/specs/2026-08-13-cli-naming-cleanup-design.md`.

### What started it: two sources of truth, drifted 9 names apart

`fish-functions/` in this repo and `~/.config/fish/functions/` on the host were
hand-copied between each other. Nothing enforced that they matched, and they
did not: 4 functions existed only in the repo (`stack-mdblist-radarr-{history,
track,tracked,untrack}`), 5 only on the host (four `stack-backup-*` plus
`stack-newapps-backup-check`, all dead since restic was removed 2026-08-12).
A command could be in the repo and not run, or run and not be in the repo.

`scripts/fish-functions-install.py` replaces the copy with a symlink per
function, so the two cannot diverge. It manages `stack-*.fish` and nothing
else - the target directory also holds the user's own fish functions, and
`__stack_api.fish`, which stays a plain copy because it has no `stack-` prefix.

`tests/test_fish_functions_installed.py` is the invariant: it fails the commit
if any installed function is a plain copy, points somewhere other than this
repo, dangles, or exists on one side and not the other. It skips on a machine
with no `~/.config/fish`, so a fresh clone and CI stay green.

### 8a also closed three real gaps

- **5 dead functions removed** from the host. They were restic-era; restic went
  2026-08-12 and these survived it.
- **4 commands `commands.json` advertised but that did not exist**:
  `stack-loop-candidates`, `stack-loop-unmonitor`, `stack-loop-exclude`,
  `stack-nzbdav-dedup-check`. Their control-panel routes were live the whole
  time - only the fish side was missing. Written from the manifest's own specs.
- **1 command that existed with no `commands.json` entry**:
  `stack-arr-toggle-search`. The plan's proposed entry was single-arg; the real
  function takes two (`<radarr|sonarr|all> <on|off>`) and passes
  `?enabled=true|false`, so the entry follows the function. The palette entry
  drops `all` because `palette.js` issues one request per command and `all`
  fans out to two.
- `control-panel/services/backups/` deleted. It was an empty directory left by
  the restic removal, and `main.py` imports `services.<name>.router` for every
  directory it finds, so an empty one is a latent import error.

### 8b: the 12 renames

`tests/test_fish_naming.py` is the schema. There is no prose rule that can
drift from it. `scripts/fish-rename.py` applied the table in one pass.

| Old | New | Why |
|---|---|---|
| `stack-arr-blocklist-clear` | `stack-arr-clear-blocklist` | verb order |
| `stack-arr-search-toggle` | `stack-arr-toggle-search` | verb order |
| `stack-plex-rss-import` | `stack-plex-import-rss` | verb order |
| `stack-plex-watchlist-import` | `stack-plex-import-watchlist` | verb order |
| `stack-radarr-list-import` | `stack-radarr-import-list` | verb order |
| `stack-sonarr-custom-list-import` | `stack-sonarr-import-custom-list` | verb order |
| `stack-sonarr-monitor-episodes-fix` | `stack-sonarr-fix-episode-monitoring` | verb order |
| `stack-tmdb-company-import` | `stack-tmdb-import-company` | verb order |
| `stack-tmdb-keyword-import` | `stack-tmdb-import-keyword` | verb order |
| `stack-trakt-list-import` | `stack-trakt-import-list` | verb order |
| `stack-recently-added` | `stack-arr-recently-added` | had no domain; collided in meaning with `stack-plex-recently-added` and `stack-tautulli-recently-added` |
| `stack-disk-usage` | `stack-disk-config-sizes` | said "disk usage", actually reports per-app `config/` directory sizes |

Hard cutover, no aliases. Every reference moved in the same commit and the
script proved it by grepping each old name afterwards.

### What was deliberately NOT renamed

- **35 host domains** (`disk`, `journal`, `kernel`, `pkg`, `oom`, `zombie`...).
  These are host-level concerns, not services, and they are a legitimate second
  namespace rather than an inconsistency. `loop` joined them in 8b.
- **21 source-first commands** (`stack-letterboxd-radarr-*`,
  `stack-mdblist-radarr-*`, `stack-tmdb-*`, `stack-trakt-*`, `stack-rating-*`).
  Naming the data source before the target app reads as intent and
  tab-completes by source. `test_source_first_domains_stay_source_first` now
  guards the exception in *both* directions, so a well-meaning later rename to
  `stack-radarr-letterboxd-*` fails.
- **7 top-level commands**, in two shapes: dispatchers where the action is an
  argument (`stack-arr`, `stack-plex`, `stack-container`) and bare reads
  (`stack-status`, `stack-top`, `stack-version`, `stack-help`).

### Landmine: the linter catches 7 of 12, and that is on purpose

`test_actions_are_verb_first` flagged 7 of the 12 renames. It misses any name
whose leading token is noun-verb ambiguous - `search` in
`stack-arr-search-toggle`, `list` in `stack-radarr-list-import`, `monitor` in
`stack-sonarr-monitor-episodes-fix` - because that token is in `VERBS`, so the
name already looks verb-first.

A trailing-verb rule was tried as the fix and rejected on measured numbers, not
taste: it flags 33 legitimate names (`stack-gaps2-scan`, `stack-oom-check`,
every single-token action) and would have flagged 4 of the rename's own targets
including `stack-radarr-import-list`. English noun/verb ambiguity is not
resolvable in a token set. The ambiguous cases stay human judgment; the linter
owns the unambiguous ones. Do not "fix" this by widening the rule - check the
numbers first.

### Landmine: some files describe the rename and must never be rewritten

`fish-rename.py` excludes `docs/superpowers/**`, `PLANS.md`,
`tests/test_fish_naming.py` and its own test file. Those contain tables and
docstrings that read `old -> new`; a blind pass collapses both sides into the
new name and destroys the only record of what changed. The post-rename grep
check skips them for the same reason. If you add a rename later, extend
`RECORD_PATHS`, do not delete the exclusion.

Conversely `targets()` covers `control-panel/**/*.py` and `tests/**/*.py`,
which the plan's first draft missed: `control-panel/services/arr/router.py`
names seven `.fish` files in a comment about auth dependencies, and a router
test names the command that exercises it.

### Numbers

194 functions, identical on both sides. Test suite 824 -> 849 (+7 installer,
+3 drift, +6 schema, +9 rename script). `commands.json` 135 -> 136 entries;
its rename diff is 12 insertions and 12 deletions, all `"Name"` values.

**Never round-trip `commands.json` through `json.dump`.** It re-escapes em
dashes across unrelated entries. Edit it key-by-key. This bit once already,
on 2026-08-13, and had to be reverted.

## Checkrr removed, 2026-08-12 (commit 278ff4a)

The corrupt-media scanner is gone: container, compose block, 6 fish
functions, control-panel router/routes/tiles/commands, Organizr tab,
health-monitor probe, and FUSE cascade membership. Nothing scans this
library for dead media on a schedule now.

**Why it went.** Checkrr wrote a single reason for everything it flagged —
`unknown` — across all 1,251 files. That merged two unrelated populations:
genuinely dead media, and disc images `ffprobe` simply cannot demux. A
report where 27% of rows are false positives and nothing distinguishes
them cannot drive a re-download, so the scanner's output was never
actionable on its own.

**What replaced it.** `scripts/checkrr-badfiles-report.py` re-verifies
every row by container magic bytes rather than trusting the reason
column. A zeroed header is nzbdav's gap-fill for expired Usenet
articles, and that is the real signal. Of the 1,251 flagged files, 915
are genuinely unplayable. Report-only, deliberately: see this repo's
mass-deletion history before making anything here delete.

**The data outlived the scanner.** The final scan is archived at
`data/checkrr-final/` — gitignored, because it holds Arr API keys. Dead
media does not disappear when the thing that found it does.

**Before reinstalling it, know the cost.** Checkrr's whole method is
`ffprobe` against every file. Every file in this stack is a symlink into
a streamed Usenet mount, so a full scan pulls real bytes for all 104,282
of them. STACK.md's 2026-07-26 entry records 8+ D-state hangs in one
~3-hour session caused by exactly that access pattern. A scheduled
scanner here is a scheduled outage risk, not just I/O.

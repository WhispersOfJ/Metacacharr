# Control Panel Catalog Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the control panel's software catalog from 20 to 70+ entries by adding three new categories (Media, Browser Games, RetroArch Emulation, ~17 services each), and surface each entry's environment variables and volume mappings in the card UI.

**Architecture:** The catalog stays a curated, hardcoded Python list installed via the Docker SDK (never compose-file writes, never a "paste any image" path) — this plan only grows the list and the UI that reads it. `registry.py` (369 lines) is split by category into `services/catalog/entries/*.py` modules that each export a `CATALOG: list[dict]` of that category's entries; `registry.py` becomes an aggregator that concatenates them, preserving `CATALOG`, `CATALOG_BY_ID`, `CATALOG_LABEL`, `NETWORK` as the same public names every other file already imports. New entries are produced by dispatching three parallel research agents (one per new category), each returning registry-shaped dicts for ~17 services verified against real Docker Hub/GitHub/LinuxServer.io listings — nothing is hand-guessed. `router.py`'s list endpoint is extended to include `environment` and `volumes` in its response; `catalog.js` grows a collapsible details section per card to render them.

**Tech Stack:** FastAPI + docker-py SDK (backend), vanilla ES modules + CSS (frontend), pytest (gate tests).

**Spec:** `docs/superpowers/specs/2026-08-14-control-panel-maximalist-redesign-design.md` (Part 2: Service catalog expansion)

## Global Constraints

- Every new entry follows the exact schema already in `registry.py`: `id, name, category, pitch, image, tag, ports, volumes, environment, cap_add, devices, footprint, doc_url, caveat` (plus optional `docker_sock`, `command` used by a few existing entries).
- No fabricated env/volume schemas — anything unverifiable gets a narrower entry or is left out entirely, never guessed. Each entry must be checked against its real upstream listing (Docker Hub / GitHub / LinuxServer.io) before being written.
- New host ports must not collide with any port already bound in `docker-compose.yml` or the existing 20-entry catalog. Reserved/in-use ports as of this plan: compose uses `3000, 5055, 6246, 6767, 7878, 7879, 8182, 8283, 8420, 8700-8705, 8989, 8990, 9696, 9876, 11011`; the existing catalog uses `80, 443, 3001, 3009, 4277, 5690, 8081, 8082, 8083, 8085, 8090, 8093, 8096, 8191, 8222, 8265, 8266, 8765, 9443`. New entries in this plan use the `81xx` and `84xx`+ ranges (see Task 2-4) to stay clear of both.
- LinuxServer.io images preferred where available (matches existing catalog convention and this stack's broader image choices elsewhere in `docker-compose.yml`).
- No new backend framework, build step, or JS bundler. No auto-configuration of catalog services into the Arr fleet. No internet exposure changes.
- Selection is "well-known images I select and verify," not "whatever an agent invents" — I review and merge each research agent's output before any entry is written into the codebase.

---

## File Structure

| File | Change |
|---|---|
| `control-panel/services/catalog/entries/__init__.py` | New — empty, marks package |
| `control-panel/services/catalog/entries/monitoring.py` through `security.py` | New — move each of the 6 existing categories' entries out of `registry.py` verbatim, one file per category, each exporting `CATALOG: list[dict]` |
| `control-panel/services/catalog/entries/media.py` | New — ~17 verified Media entries |
| `control-panel/services/catalog/entries/browser_games.py` | New — ~17 verified Browser Games entries |
| `control-panel/services/catalog/entries/retroarch.py` | New — ~17 verified RetroArch Emulation entries |
| `control-panel/services/catalog/registry.py` | Rewritten to aggregate all `entries/*.py` modules into one `CATALOG` list; keeps `CATALOG_BY_ID`, `CATALOG_LABEL`, `NETWORK` |
| `control-panel/services/catalog/router.py` | `catalog_list()` includes `environment` and `volumes` in each item |
| `control-panel/static/js/catalog.js` | `renderCard()` adds a collapsible "Details" toggle listing env vars and volume mappings |
| `control-panel/static/style.css` | Styles for the new details toggle/panel |
| `tests/control_panel/test_catalog_registry.py` | New — schema validation gate test (required keys, no port collisions, no duplicate ids, category counts) |
| `tests/control_panel/test_catalog_router.py` | Updated entry-count assertions (20 → 70+), new assertions for `environment`/`volumes` in list response |

---

## Task 1: Split `registry.py` into per-category modules (no content change)

**Files:**
- Create: `control-panel/services/catalog/entries/__init__.py`
- Create: `control-panel/services/catalog/entries/monitoring.py`
- Create: `control-panel/services/catalog/entries/notifications.py`
- Create: `control-panel/services/catalog/entries/indexer_completion.py`
- Create: `control-panel/services/catalog/entries/library_quality.py`
- Create: `control-panel/services/catalog/entries/household_access.py`
- Create: `control-panel/services/catalog/entries/docker_host.py`
- Create: `control-panel/services/catalog/entries/security.py`
- Modify: `control-panel/services/catalog/registry.py`
- Test: `tests/control_panel/test_catalog_router.py` (existing, must still pass unmodified at this step)

**Interfaces:**
- Produces: each `entries/*.py` module exports `CATALOG: list[dict]` (category-scoped). `registry.py` still exports `CATALOG: list[dict]` (full, concatenated), `CATALOG_BY_ID: dict[str, dict]`, `CATALOG_LABEL: str`, `NETWORK: str` — identical names/types to before, so `router.py` and every test needs zero changes at this step.

- [ ] **Step 1: Create the `entries` package**

```python
# control-panel/services/catalog/entries/__init__.py
```//empty file

- [ ] **Step 2: Create `entries/monitoring.py` with the 5 existing "Monitoring & observability" entries moved verbatim**

Copy the 5 dict literals for `uptime-kuma`, `beszel`, `scrutiny`, `dozzle`, `speedtest-tracker` out of the current `registry.py` (lines 29-109) into this new file:

```python
"""Monitoring & observability catalog entries."""

CATALOG: list[dict] = [
    {
        "id": "uptime-kuma",
        "name": "Uptime Kuma",
        "category": "Monitoring & observability",
        "pitch": "Pings every service's HTTP endpoint (and can watch Docker containers directly) - pages you the moment one goes dark, before you notice from the couch.",
        "image": "louislam/uptime-kuma",
        "tag": "2",
        "ports": {"3001/tcp": 3001},
        "volumes": {"catalog_uptime_kuma_data": {"bind": "/app/data", "mode": "rw"}},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~90MB RAM",
        "doc_url": "https://github.com/louislam/uptime-kuma",
        "caveat": None,
    },
    {
        "id": "beszel",
        "name": "Beszel",
        "category": "Monitoring & observability",
        "pitch": "Host + per-container CPU/RAM/disk/network, hub-and-agent. ~50x lighter than Grafana+Prometheus for this stack's scale.",
        "image": "henrygd/beszel",
        "tag": "latest",
        "ports": {"8090/tcp": 8090},
        "volumes": {"catalog_beszel_data": {"bind": "/beszel_data", "mode": "rw"}},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "<10MB RAM (hub); agent installs separately per host",
        "doc_url": "https://github.com/henrygd/beszel",
        "caveat": "Hub only - the agent that actually reports container stats runs as a second, separate container (not installed by this one-click; see docs).",
    },
    {
        "id": "scrutiny",
        "name": "Scrutiny",
        "category": "Monitoring & observability",
        "pitch": "S.M.A.R.T. drive health merged with Backblaze real-world failure-rate data - flags a dying disk weeks before it takes the library down.",
        "image": "ghcr.io/analogj/scrutiny",
        "tag": "latest-omnibus",
        "ports": {"8080/tcp": 8085},
        "volumes": {"catalog_scrutiny_data": {"bind": "/opt/scrutiny/config", "mode": "rw"}},
        "environment": {},
        "cap_add": ["SYS_RAWIO"],
        "devices": [],
        "footprint": "~70MB RAM",
        "doc_url": "https://github.com/analogj/scrutiny",
        "caveat": "Needs SYS_RAWIO plus direct device passthrough to read SMART data - installed with cap_add granted, but device passthrough (which physical disks) needs a one-time manual edit before it can see any drives.",
    },
    {
        "id": "dozzle",
        "name": "Dozzle",
        "category": "Monitoring & observability",
        "pitch": "Real-time log viewer across every container, 7MB image, nothing stored - the \"just let me see what radarr just logged\" tool without opening a shell.",
        "image": "amir20/dozzle",
        "tag": "latest",
        "ports": {"8080/tcp": 8081},
        "volumes": {},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~15MB RAM",
        "doc_url": "https://github.com/amir20/dozzle",
        "caveat": None,
        "docker_sock": True,
    },
    {
        "id": "speedtest-tracker",
        "name": "Speedtest Tracker",
        "category": "Monitoring & observability",
        "pitch": "Runs a speed test on a schedule, graphs it over time - turns \"is the ISP throttling us\" from a feeling into a chart you can point at.",
        "image": "henrywhitaker3/speedtest-tracker",
        "tag": "latest",
        "ports": {"80/tcp": 8765},
        "volumes": {"catalog_speedtest_data": {"bind": "/config", "mode": "rw"}},
        "environment": {"OOKLA_EULA_GDPR": "true"},
        "cap_add": [],
        "devices": [],
        "footprint": "~120MB RAM",
        "doc_url": "https://github.com/henrywhitaker3/Speedtest-Tracker",
        "caveat": "No official ARM image from the maintainer - fine on this host.",
    },
]
```

- [ ] **Step 3: Create `entries/notifications.py` with `notifiarr` and `ntfy` moved verbatim**

```python
"""Notifications catalog entries."""

CATALOG: list[dict] = [
    {
        "id": "notifiarr",
        "name": "Notifiarr",
        "category": "Notifications",
        "pitch": "One client that every *arr app in this fleet reports to, fanning out to Discord/webhooks - replaces per-app notification config with one place to manage it.",
        "image": "golift/notifiarr",
        "tag": "latest",
        "ports": {},
        "volumes": {"catalog_notifiarr_data": {"bind": "/config", "mode": "rw"}},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~55MB RAM",
        "doc_url": "https://github.com/Notifiarr/notifiarr",
        "caveat": "Needs each *arr app's URL + API key entered in its own config UI after install - not wired automatically by this installer.",
    },
    {
        "id": "ntfy",
        "name": "ntfy",
        "category": "Notifications",
        "pitch": "Push straight to your phone/desktop with a plain HTTP POST, no account or app-store dependency.",
        "image": "binwiederhier/ntfy",
        "tag": "latest",
        "ports": {"80/tcp": 8093},
        "volumes": {"catalog_ntfy_data": {"bind": "/var/lib/ntfy", "mode": "rw"}},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~30MB RAM",
        "doc_url": "https://github.com/binwiederhier/ntfy",
        "caveat": None,
        "command": ["serve"],
    },
]
```

- [ ] **Step 4: Create `entries/indexer_completion.py` with `flaresolverr`, `gaps2`, `recyclarr` moved verbatim**

```python
"""Indexer & library completion catalog entries."""

CATALOG: list[dict] = [
    {
        "id": "flaresolverr",
        "name": "FlareSolverr",
        "category": "Indexer & library completion",
        "pitch": "Solves Cloudflare challenges Prowlarr can't get through directly - wires in as a Prowlarr indexer proxy.",
        "image": "ghcr.io/flaresolverr/flaresolverr",
        "tag": "latest",
        "ports": {"8191/tcp": 8191},
        "volumes": {},
        "environment": {"LOG_LEVEL": "info"},
        "cap_add": [],
        "devices": [],
        "footprint": "~180MB RAM (headless browser)",
        "doc_url": "https://github.com/FlareSolverr/FlareSolverr",
        "caveat": "After install, add it as a proxy in Prowlarr's Settings -> Indexers manually - not auto-wired.",
    },
    {
        "id": "gaps2",
        "name": "GAPS-2",
        "category": "Indexer & library completion",
        "pitch": "Scans Plex for collections you partially own and finds the missing entries, sends them straight to Radarr by TMDB id.",
        "image": "primetime43/gaps-2",
        "tag": "latest",
        "ports": {"4277/tcp": 4277},
        "volumes": {"catalog_gaps2_data": {"bind": "/data", "mode": "rw"}},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~150MB RAM",
        "doc_url": "https://github.com/primetime43/GAPS-2",
        "caveat": "Fork of the unmaintained original housewrecker/gaps - this is the actively maintained one.",
    },
    {
        "id": "recyclarr",
        "name": "Recyclarr",
        "category": "Indexer & library completion",
        "pitch": "Continuously syncs TRaSH-Guides quality profiles and custom formats into Radarr/Sonarr - automates what the trash-guides-applier skill does by hand.",
        "image": "ghcr.io/recyclarr/recyclarr",
        "tag": "8",
        "ports": {},
        "volumes": {"catalog_recyclarr_data": {"bind": "/config", "mode": "rw"}},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~20MB RAM (scheduled run, no persistent server)",
        "doc_url": "https://github.com/recyclarr/recyclarr",
        "caveat": "Tag pinned to major version 8 on purpose - the :latest tag is no longer published upstream.",
    },
]
```

- [ ] **Step 5: Create `entries/library_quality.py` with `tdarr`, `watchstate`, `plexanisync` moved verbatim**

```python
"""Library quality & sync catalog entries."""

CATALOG: list[dict] = [
    {
        "id": "tdarr",
        "name": "Tdarr",
        "category": "Library quality & sync",
        "pitch": "Distributed transcode automation - re-encodes the library against rules you set, commonly cutting storage 40-50% with no visible quality loss.",
        "image": "haveagitgat/tdarr",
        "tag": "latest",
        "ports": {"8265/tcp": 8265, "8266/tcp": 8266},
        "volumes": {
            "catalog_tdarr_server": {"bind": "/app/server", "mode": "rw"},
            "catalog_tdarr_configs": {"bind": "/app/configs", "mode": "rw"},
            "catalog_tdarr_logs": {"bind": "/app/logs", "mode": "rw"},
        },
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~200MB RAM; transcode work itself is CPU/GPU-bound",
        "doc_url": "https://github.com/HaveAGitGat/Tdarr",
        "caveat": "Server only - a Tdarr_Node (separate container) does the actual transcoding and isn't installed automatically.",
    },
    {
        "id": "watchstate",
        "name": "Watchstate",
        "category": "Library quality & sync",
        "pitch": "Syncs watch/play state between Plex and Trakt - broader scope than PlexTraktSync, which this replaces outright.",
        "image": "ghcr.io/arabcoders/watchstate",
        "tag": "latest",
        "ports": {"8080/tcp": 8096},
        "volumes": {"catalog_watchstate_data": {"bind": "/config", "mode": "rw"}},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~60MB RAM",
        "doc_url": "https://github.com/arabcoders/watchstate",
        "caveat": None,
    },
    {
        "id": "plexanisync",
        "name": "PlexAniSync",
        "category": "Library quality & sync",
        "pitch": "Syncs the anime library's watch status to AniList - a direct fit given how anime-heavy this specific library is (Radarr Anime).",
        "image": "ghcr.io/rickdb/plexanisync",
        "tag": "latest",
        "ports": {},
        "volumes": {"catalog_plexanisync_data": {"bind": "/data", "mode": "rw"}},
        "environment": {"PLEX_URL": "http://plex:32400"},
        "cap_add": [],
        "devices": [],
        "footprint": "~40MB RAM (scheduled run)",
        "doc_url": "https://github.com/RickDB/PlexAniSync",
        "caveat": "Needs PLEX_TOKEN and AniList credentials added to its config after install.",
    },
]
```

- [ ] **Step 6: Create `entries/household_access.py` with `wizarr`, `homepage` moved verbatim**

```python
"""Household & access catalog entries."""

CATALOG: list[dict] = [
    {
        "id": "wizarr",
        "name": "Wizarr",
        "category": "Household & access",
        "pitch": "Self-service invite links for Plex - a friend clicks one link and is onboarded, including a walkthrough to install Plex and use Seerr.",
        "image": "ghcr.io/wizarrrr/wizarr",
        "tag": "latest",
        "ports": {"5690/tcp": 5690},
        "volumes": {"catalog_wizarr_data": {"bind": "/data/database", "mode": "rw"}},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~70MB RAM",
        "doc_url": "https://github.com/wizarrrr/wizarr",
        "caveat": None,
    },
    {
        "id": "homepage",
        "name": "Homepage",
        "category": "Household & access",
        "pitch": "A simple bookmark/status launcher for household members who shouldn't see the operator console - separate audience from the control panel.",
        "image": "ghcr.io/gethomepage/homepage",
        "tag": "latest",
        "ports": {"3000/tcp": 3009},
        "volumes": {"catalog_homepage_config": {"bind": "/app/config", "mode": "rw"}},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~60MB RAM",
        "doc_url": "https://github.com/gethomepage/homepage",
        "caveat": "Chosen over Homarr - Homarr's GitHub repo currently shows archived. Config-as-code, edited via files in its volume, not a UI.",
    },
]
```

- [ ] **Step 7: Create `entries/docker_host.py` with `portainer`, `filebrowser`, `caddy` moved verbatim**

```python
"""Docker & host management catalog entries."""

CATALOG: list[dict] = [
    {
        "id": "portainer",
        "name": "Portainer CE",
        "category": "Docker & host management",
        "pitch": "Deeper stack/volume/network management than the control panel's app-specific container controls.",
        "image": "portainer/portainer-ce",
        "tag": "lts",
        "ports": {"9443/tcp": 9443},
        "volumes": {"catalog_portainer_data": {"bind": "/data", "mode": "rw"}},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~80MB RAM",
        "doc_url": "https://github.com/portainer/portainer",
        "caveat": "Overlaps with the control panel's own docker.sock access - different job (general admin vs. app-specific actions), not redundant, but both can restart the same container.",
        "docker_sock": True,
    },
    {
        "id": "filebrowser",
        "name": "Filebrowser",
        "category": "Docker & host management",
        "pitch": "A plain web file manager scoped to the media/config directories - upload, rename, preview without a terminal.",
        "image": "filebrowser/filebrowser",
        "tag": "latest",
        "ports": {"80/tcp": 8082},
        "volumes": {"catalog_filebrowser_data": {"bind": "/database", "mode": "rw"}},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~25MB RAM",
        "doc_url": "https://github.com/filebrowser/filebrowser",
        "caveat": "Installed with no media/config bind mount by default - add one manually before use, scoped as tightly as you're comfortable with.",
    },
    {
        "id": "caddy",
        "name": "Caddy",
        "category": "Docker & host management",
        "pitch": "Reverse proxy with fully automatic HTTPS - two lines of config gets every service in this catalog a real certificate instead of a bare IP:port.",
        "image": "caddy",
        "tag": "latest",
        "ports": {"80/tcp": 80, "443/tcp": 443},
        "volumes": {
            "catalog_caddy_data": {"bind": "/data", "mode": "rw"},
            "catalog_caddy_config": {"bind": "/config", "mode": "rw"},
        },
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~15MB RAM",
        "doc_url": "https://caddyserver.com/docs/",
        "caveat": "Installed with a blank Caddyfile - add site blocks for each service you want proxied.",
    },
]
```

- [ ] **Step 8: Create `entries/security.py` with `vaultwarden`, `organizr` moved verbatim**

```python
"""Security & unified access catalog entries."""

CATALOG: list[dict] = [
    {
        "id": "vaultwarden",
        "name": "Vaultwarden",
        "category": "Security & unified access",
        "pitch": "Self-hosted, Bitwarden-compatible password vault - genuinely useful given how many per-service API keys this stack alone manages.",
        "image": "vaultwarden/server",
        "tag": "latest",
        "ports": {"80/tcp": 8222},
        "volumes": {"catalog_vaultwarden_data": {"bind": "/data", "mode": "rw"}},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~30MB RAM",
        "doc_url": "https://github.com/dani-garcia/vaultwarden",
        "caveat": "Only use this behind the Caddy entry above - a password manager served over bare HTTP is a real risk, not installed with HTTPS on its own.",
    },
    {
        "id": "organizr",
        "name": "Organizr",
        "category": "Security & unified access",
        "pitch": "Embeds every service's actual web UI as tabs in one shell - keeps you inside the page instead of bouncing per app, unlike Homepage's link-launcher.",
        "image": "ghcr.io/organizr/organizr",
        "tag": "latest",
        "ports": {"80/tcp": 8083},
        "volumes": {"catalog_organizr_data": {"bind": "/config", "mode": "rw"}},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~50MB RAM",
        "doc_url": "https://github.com/Organizr/docker-organizr",
        "caveat": None,
    },
]
```

- [ ] **Step 9: Rewrite `registry.py` to aggregate the split modules**

```python
"""Curated software catalog - entries are split by category into
entries/*.py, each verified against real GitHub/Docker Hub/LinuxServer.io
listings before being written (see each module's header comment for its
verification date). Not an open image installer - see the design note
below for why install/remove goes through the Docker SDK, not compose.

Design note on HOW this installs, which differs from the original
pitch's "writes docker-compose.yml" framing: this container has no bind
mount of the repo's docker-compose.yml and no `docker compose` CLI in its
own image (checked before writing this - see Dockerfile). It only has
docker.sock. So install/remove goes straight through the Docker SDK
(docker_client.containers.run/.stop/.remove) instead of editing the
compose file at all. A catalog container is a real, independently-
running Docker container on the same `stacknet` network, with its own
`restart: unless-stopped` policy - it survives a reboot or crash the same
way a compose service would, but a `docker compose down && up` on the
main stack won't touch it (compose has never heard of it). That's a
strictly smaller blast radius than the alternative (a bad compose-file
write breaking `docker compose up` for the entire stack), which is why
this shape won out over the treatment doc's original assumption.
"""
from services.catalog.entries import (
    docker_host,
    household_access,
    indexer_completion,
    library_quality,
    monitoring,
    notifications,
    security,
)

CATALOG_LABEL = "media-stack.catalog"  # label key marking a container as catalog-managed
NETWORK = "stacknet"

CATALOG: list[dict] = [
    *monitoring.CATALOG,
    *notifications.CATALOG,
    *indexer_completion.CATALOG,
    *library_quality.CATALOG,
    *household_access.CATALOG,
    *docker_host.CATALOG,
    *security.CATALOG,
]

CATALOG_BY_ID = {entry["id"]: entry for entry in CATALOG}

assert len(CATALOG) == 20, f"catalog registry drifted from 20 entries: {len(CATALOG)}"
```

- [ ] **Step 10: Run the existing test suite to verify the split changed nothing observable**

Run: `cd control-panel && python -m pytest ../tests/control_panel/test_catalog_router.py -v`
Expected: all tests PASS, unchanged from before the split (still 20 entries, all existing ids/behavior identical).

- [ ] **Step 11: Commit**

```bash
git add control-panel/services/catalog/entries/ control-panel/services/catalog/registry.py
git commit -m "refactor: split catalog registry into per-category modules"
```

---

## Task 2: Research and add Media category entries

**Files:**
- Create: `control-panel/services/catalog/entries/media.py`
- Modify: `control-panel/services/catalog/registry.py`
- Test: `tests/control_panel/test_catalog_registry.py` (created in Task 5, run against this file once it exists — for now, manually verify schema shape matches Task 1's entries)

**Interfaces:**
- Consumes: the same dict schema as every other `entries/*.py` module (Task 1) — `id, name, category, pitch, image, tag, ports, volumes, environment, cap_add, devices, footprint, doc_url, caveat`, category value must be the literal string `"Media"`.
- Produces: `entries/media.py` exports `CATALOG: list[dict]`, ~17 entries, host ports in the `81xx` range only (`8100`-`8199`), none colliding with the Global Constraints port list.

- [ ] **Step 1: Dispatch a research agent for Media category candidates**

Use the Agent tool (general-purpose, foreground) with this brief: "Research ~17 self-hostable Media category services suitable for a curated Docker catalog (audiobooks, podcasts, music management, photo management, e-reader/comic servers, media requesting/companion tools — NOT already-installed apps in this stack: Plex, Radarr, Sonarr, Prowlarr, Bazarr, Overseerr/Seerr, NzbDAV are already present, do not duplicate). For each candidate, verify against its real Docker Hub or GitHub Container Registry listing (not memory) and report: exact image name, exact tag (prefer a pinned version tag over `latest` if the project's own docs recommend one), default container port(s), typical volume mounts with container-side paths, any required environment variables, footprint estimate, doc URL, and any caveat a self-hoster needs to know before install. Rank by GitHub stars, recency of last release, and issue responsiveness. Return results as a numbered list, one service per entry, with every field explicit — do not guess or fill gaps with plausible-sounding defaults."

- [ ] **Step 2: Review agent output against this stack's context**

Cross-check the agent's ~17 candidates: drop any that duplicate an already-running service (check `docker-compose.yml` service names), drop any whose image/tag/port claims look unverifiable or inconsistent with the agent's own citations, and confirm no chosen host port falls inside any range listed in Global Constraints. Select the final list (should land at 15-20 entries).

- [ ] **Step 3: Write `entries/media.py` using the reviewed, verified data**

```python
"""Media catalog entries - verified against Docker Hub/GitHub/LinuxServer.io
listings on 2026-08-15 by research-agent dispatch, reviewed before merge
(see docs/superpowers/plans/2026-08-15-control-panel-catalog-expansion.md
Task 2). Host ports allocated in the 81xx range to avoid collision with
docker-compose.yml and the existing 20-entry catalog (see that plan's
Global Constraints for the full reserved-port list).
"""

CATALOG: list[dict] = [
    # Populate with the Task 2 Step 2 reviewed entries, one dict per
    # service, each following the exact schema from entries/monitoring.py.
    # Example shape (replace with real verified data, do not ship this
    # placeholder):
    # {
    #     "id": "audiobookshelf",
    #     "name": "Audiobookshelf",
    #     "category": "Media",
    #     "pitch": "...",
    #     "image": "advplyr/audiobookshelf",
    #     "tag": "latest",
    #     "ports": {"80/tcp": 8100},
    #     "volumes": {"catalog_audiobookshelf_data": {"bind": "/config", "mode": "rw"}},
    #     "environment": {},
    #     "cap_add": [],
    #     "devices": [],
    #     "footprint": "~80MB RAM",
    #     "doc_url": "https://github.com/advplyr/audiobookshelf",
    #     "caveat": None,
    # },
]
```

- [ ] **Step 4: Update `registry.py` to include the new module**

```python
from services.catalog.entries import (
    docker_host,
    household_access,
    indexer_completion,
    library_quality,
    media,
    monitoring,
    notifications,
    security,
)

CATALOG: list[dict] = [
    *monitoring.CATALOG,
    *notifications.CATALOG,
    *indexer_completion.CATALOG,
    *library_quality.CATALOG,
    *household_access.CATALOG,
    *docker_host.CATALOG,
    *security.CATALOG,
    *media.CATALOG,
]

CATALOG_BY_ID = {entry["id"]: entry for entry in CATALOG}

assert len(CATALOG) >= 35, f"catalog registry has fewer entries than expected after Media: {len(CATALOG)}"
```

- [ ] **Step 5: Run the app's import to sanity-check the module loads cleanly**

Run: `cd control-panel && python -c "from services.catalog.registry import CATALOG; print(len(CATALOG))"`
Expected: prints a number >= 35 (20 existing + Media entries), no import errors.

- [ ] **Step 6: Commit**

```bash
git add control-panel/services/catalog/entries/media.py control-panel/services/catalog/registry.py
git commit -m "feat: add Media category to catalog (~17 verified entries)"
```

---

## Task 3: Research and add Browser Games category entries

**Files:**
- Create: `control-panel/services/catalog/entries/browser_games.py`
- Modify: `control-panel/services/catalog/registry.py`

**Interfaces:**
- Consumes: same schema as Task 2. Category value must be the literal string `"Browser Games"`.
- Produces: `entries/browser_games.py` exports `CATALOG: list[dict]`, ~17 entries, host ports in the `82xx` range only (`8200`-`8299`).

- [ ] **Step 1: Dispatch a research agent for Browser Games category candidates**

Use the Agent tool (general-purpose, foreground) with this brief: "Research ~17 self-hostable browser-playable game server Docker images suitable for a curated catalog (retro-web arcade collections, self-hosted multiplayer browser games, game server frontends playable via a web browser with no client install — chess/card/board game servers, 2048-style collections, browser-based emulator frontends are fine here but full RetroArch/emulation-console images belong in a separate category, exclude those). For each candidate, verify against its real Docker Hub or GitHub Container Registry listing (not memory) and report: exact image name, exact tag, default container port(s), typical volume mounts with container-side paths, any required environment variables, footprint estimate, doc URL, and any caveat. Rank by GitHub stars, recency, and issue responsiveness. Return results as a numbered list, one service per entry, every field explicit — never guess or fabricate a plausible-sounding image/tag/port."

- [ ] **Step 2: Review agent output**

Cross-check: no duplicates with Task 2's Media entries or already-running compose services, no overlap with RetroArch/emulation-console images (those belong in Task 4), confirm no chosen host port collides with any range in Global Constraints or Task 2's `81xx` allocation. Select the final list (15-20 entries).

- [ ] **Step 3: Write `entries/browser_games.py` using the reviewed, verified data**

```python
"""Browser Games catalog entries - verified against Docker Hub/GitHub
listings on 2026-08-15 by research-agent dispatch, reviewed before merge
(see docs/superpowers/plans/2026-08-15-control-panel-catalog-expansion.md
Task 3). Host ports allocated in the 82xx range.
"""

CATALOG: list[dict] = [
    # Populate with the Task 3 Step 2 reviewed entries, same schema as
    # entries/media.py.
]
```

- [ ] **Step 4: Update `registry.py` to include the new module**

Add `browser_games` to the import list and to the `CATALOG` concatenation (same pattern as Task 2 Step 4), and bump the sanity assertion:

```python
assert len(CATALOG) >= 50, f"catalog registry has fewer entries than expected after Browser Games: {len(CATALOG)}"
```

- [ ] **Step 5: Run the app's import to sanity-check the module loads cleanly**

Run: `cd control-panel && python -c "from services.catalog.registry import CATALOG; print(len(CATALOG))"`
Expected: prints a number >= 50, no import errors.

- [ ] **Step 6: Commit**

```bash
git add control-panel/services/catalog/entries/browser_games.py control-panel/services/catalog/registry.py
git commit -m "feat: add Browser Games category to catalog (~17 verified entries)"
```

---

## Task 4: Research and add RetroArch Emulation category entries

**Files:**
- Create: `control-panel/services/catalog/entries/retroarch.py`
- Modify: `control-panel/services/catalog/registry.py`

**Interfaces:**
- Consumes: same schema as Task 2. Category value must be the literal string `"RetroArch Emulation"`.
- Produces: `entries/retroarch.py` exports `CATALOG: list[dict]`, ~17 entries, host ports in the `84xx` range only (`8400`-`8499`, chosen to skip `843x`+ since compose already uses `8420`) — actually restrict to `8430`-`8499` to clear the existing `8420` compose port cleanly.

- [ ] **Step 1: Dispatch a research agent for RetroArch Emulation category candidates**

Use the Agent tool (general-purpose, foreground) with this brief: "Research ~17 self-hostable retro game console emulation Docker images suitable for a curated catalog (web-based RetroArch frontends, per-console emulator containers with web UIs, ROM library/emulation-station-style managers playable in-browser). This stack does NOT already run any emulation service, so no dedup concern there, but do not duplicate any Media or Browser Games service (audiobookshelf-style media servers, arcade/board game servers) — this category is specifically console/ROM emulation. For each candidate, verify against its real Docker Hub or GitHub Container Registry listing (not memory) and report: exact image name, exact tag, default container port(s), typical volume mounts with container-side paths (note where a ROM library bind mount is expected), any required environment variables, footprint estimate, doc URL, and any caveat — including any legal/ROM-provenance caveat the project's own docs mention. Rank by GitHub stars, recency, and issue responsiveness. Return results as a numbered list, one service per entry, every field explicit — never guess or fabricate a plausible-sounding image/tag/port."

- [ ] **Step 2: Review agent output**

Cross-check: no duplicates with Task 2/Task 3 entries or compose services, confirm no chosen host port collides with any range in Global Constraints or Tasks 2-3's `81xx`/`82xx` allocations, and confirm the `8420` compose port specifically stays clear (use `8430`+ only). Select the final list (15-20 entries).

- [ ] **Step 3: Write `entries/retroarch.py` using the reviewed, verified data**

```python
"""RetroArch Emulation catalog entries - verified against Docker
Hub/GitHub listings on 2026-08-15 by research-agent dispatch, reviewed
before merge (see
docs/superpowers/plans/2026-08-15-control-panel-catalog-expansion.md
Task 4). Host ports allocated 8430-8499 to clear the existing compose
port 8420.
"""

CATALOG: list[dict] = [
    # Populate with the Task 4 Step 2 reviewed entries, same schema as
    # entries/media.py.
]
```

- [ ] **Step 4: Update `registry.py` to include the new module and finalize the aggregate**

```python
from services.catalog.entries import (
    browser_games,
    docker_host,
    household_access,
    indexer_completion,
    library_quality,
    media,
    monitoring,
    notifications,
    retroarch,
    security,
)

CATALOG_LABEL = "media-stack.catalog"
NETWORK = "stacknet"

CATALOG: list[dict] = [
    *monitoring.CATALOG,
    *notifications.CATALOG,
    *indexer_completion.CATALOG,
    *library_quality.CATALOG,
    *household_access.CATALOG,
    *docker_host.CATALOG,
    *security.CATALOG,
    *media.CATALOG,
    *browser_games.CATALOG,
    *retroarch.CATALOG,
]

CATALOG_BY_ID = {entry["id"]: entry for entry in CATALOG}

assert len(CATALOG) >= 65, f"catalog registry has fewer entries than expected: {len(CATALOG)}"
```

Note: this replaces the module docstring's earlier draft from Task 1 Step 9 — keep that docstring, only the import/concatenation block changes here.

- [ ] **Step 5: Run the app's import to sanity-check the full aggregate loads cleanly**

Run: `cd control-panel && python -c "from services.catalog.registry import CATALOG, CATALOG_BY_ID; print(len(CATALOG)); print(len(CATALOG_BY_ID))"`
Expected: both numbers print, equal to each other (proves no duplicate ids collapsed silently in the dict comprehension), >= 65.

- [ ] **Step 6: Commit**

```bash
git add control-panel/services/catalog/entries/retroarch.py control-panel/services/catalog/registry.py
git commit -m "feat: add RetroArch Emulation category to catalog (~17 verified entries)"
```

---

## Task 5: Gate test — registry schema validation

**Files:**
- Create: `tests/control_panel/test_catalog_registry.py`

**Interfaces:**
- Consumes: `control-panel/services/catalog/registry.py`'s `CATALOG: list[dict]` and `CATALOG_BY_ID: dict[str, dict]` (Task 4).

- [ ] **Step 1: Write the failing tests**

```python
"""Schema validation for the catalog registry - deterministic, no Docker
mocking needed, catches drift before it reaches router.py. Required keys,
port collisions, and duplicate ids are checked directly against the
CATALOG list built in registry.py.
"""
import sys
from pathlib import Path

CONTROL_PANEL_ROOT = Path(__file__).resolve().parents[2] / "control-panel"
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

from services.catalog.registry import CATALOG, CATALOG_BY_ID

REQUIRED_KEYS = {
    "id", "name", "category", "pitch", "image", "tag", "ports",
    "volumes", "environment", "cap_add", "devices", "footprint",
    "doc_url", "caveat",
}


def test_every_entry_has_all_required_keys():
    missing = {
        entry.get("id", "<no id>"): REQUIRED_KEYS - entry.keys()
        for entry in CATALOG
        if not REQUIRED_KEYS.issubset(entry.keys())
    }
    assert missing == {}, f"entries missing required keys: {missing}"


def test_no_duplicate_ids():
    ids = [entry["id"] for entry in CATALOG]
    assert len(ids) == len(set(ids)), (
        f"duplicate catalog ids found: "
        f"{sorted({i for i in ids if ids.count(i) > 1})}"
    )
    assert len(CATALOG) == len(CATALOG_BY_ID), "CATALOG_BY_ID lost entries to a duplicate id collision"


def test_no_host_port_collisions_within_catalog():
    port_owners: dict[int, str] = {}
    collisions = []
    for entry in CATALOG:
        for host_port in entry["ports"].values():
            if host_port in port_owners:
                collisions.append((host_port, port_owners[host_port], entry["id"]))
            else:
                port_owners[host_port] = entry["id"]
    assert collisions == [], f"host port collisions within the catalog: {collisions}"


def test_no_host_port_collisions_with_compose_file():
    import re

    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    compose_text = compose_path.read_text()
    compose_ports = {
        int(m)
        for m in re.findall(r'"\s*(\d+):\d+\s*"', compose_text)
    }
    catalog_ports = {p for entry in CATALOG for p in entry["ports"].values()}
    collisions = compose_ports & catalog_ports
    assert collisions == [], f"catalog host port(s) collide with docker-compose.yml: {sorted(collisions)}"


def test_at_least_65_entries_across_ten_categories():
    assert len(CATALOG) >= 65, f"expected 65+ entries after the catalog expansion, got {len(CATALOG)}"
    categories = {entry["category"] for entry in CATALOG}
    expected_new = {"Media", "Browser Games", "RetroArch Emulation"}
    assert expected_new.issubset(categories), f"missing expected new categories: {expected_new - categories}"
```

- [ ] **Step 2: Run tests to verify they pass against the already-populated registry**

Run: `cd control-panel && python -m pytest ../tests/control_panel/test_catalog_registry.py -v`
Expected: PASS. If `test_no_host_port_collisions_with_compose_file` or `test_no_host_port_collisions_within_catalog` FAILs, go back to the offending Task (2, 3, or 4) and reassign that entry's port before proceeding — do not weaken this test.

- [ ] **Step 3: Commit**

```bash
git add tests/control_panel/test_catalog_registry.py
git commit -m "test: add catalog registry schema validation gate test"
```

---

## Task 6: Extend `/api/catalog` to return environment and volumes

**Files:**
- Modify: `control-panel/services/catalog/router.py:53-68`
- Modify: `tests/control_panel/test_catalog_router.py`

**Interfaces:**
- Consumes: `CATALOG` entries' existing `environment: dict` and `volumes: dict` fields (already present on every entry per Global Constraints schema).
- Produces: `GET /api/catalog` response items now additionally include `environment: dict[str, str]` and `volumes: dict[str, dict]` alongside the existing `id, name, category, pitch, image, footprint, doc_url, caveat, ports, status` keys — a strict superset of the prior response shape, so no consumer breaks.

- [ ] **Step 1: Write the failing test**

Add to `tests/control_panel/test_catalog_router.py`:

```python
def test_list_includes_environment_and_volumes(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("no such container")
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/catalog", headers=headers)
    items = {i["id"]: i for i in resp.json()["items"]}
    speedtest = items["speedtest-tracker"]
    assert speedtest["environment"] == {"OOKLA_EULA_GDPR": "true"}
    assert speedtest["volumes"] == {"catalog_speedtest_data": {"bind": "/config", "mode": "rw"}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd control-panel && python -m pytest ../tests/control_panel/test_catalog_router.py::test_list_includes_environment_and_volumes -v`
Expected: FAIL with a `KeyError` or `assert None == {...}` (the current response has no `environment`/`volumes` keys).

- [ ] **Step 3: Extend `catalog_list()` in `router.py`**

```python
@router.get("/api/catalog")
def catalog_list(_=Depends(current_user_or_service)):
    items = []
    for entry in CATALOG:
        c = _find_container(entry["id"])
        status = "not_installed"
        if c is not None:
            status = "running" if c.status == "running" else c.status
        items.append({
            "id": entry["id"], "name": entry["name"], "category": entry["category"],
            "pitch": entry["pitch"], "image": f"{entry['image']}:{entry['tag']}",
            "footprint": entry["footprint"], "doc_url": entry["doc_url"], "caveat": entry.get("caveat"),
            "ports": sorted(entry["ports"].values()), "status": status,
            "environment": entry["environment"], "volumes": entry["volumes"],
        })
    return ok(f"{len(items)} catalog entries, {sum(1 for i in items if i['status'] != 'not_installed')} installed.",
              items=items)
```

- [ ] **Step 4: Update the entry-count assertion in the existing 20-entry test to reflect the new total**

Modify `test_list_accepts_service_key_and_has_20_entries` in `tests/control_panel/test_catalog_router.py`:

```python
def test_list_accepts_service_key_and_has_expanded_entry_count(cp_main_app):
    dc = _docker_client_module(cp_main_app)
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("no such container")
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/catalog", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) >= 65
    assert all(i["status"] == "not_installed" for i in body["items"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd control-panel && python -m pytest ../tests/control_panel/test_catalog_router.py -v`
Expected: all PASS, including the new `test_list_includes_environment_and_volumes` and the renamed count test.

- [ ] **Step 6: Commit**

```bash
git add control-panel/services/catalog/router.py tests/control_panel/test_catalog_router.py
git commit -m "feat: include environment and volumes in catalog list response"
```

---

## Task 7: Card UI — collapsible env/volume details section

**Files:**
- Modify: `control-panel/static/js/catalog.js:27-49`
- Modify: `control-panel/static/style.css`

**Interfaces:**
- Consumes: `item.environment: dict[str, string]` and `item.volumes: dict[str, {bind: string, mode: string}]` from `/api/catalog` (Task 6).
- Produces: a `.catalog-details` toggle button + hidden panel per card; no new exported functions, this is a `renderCard()`-internal change.

- [ ] **Step 1: Add a details-formatting helper and extend `renderCard()` in `catalog.js`**

```javascript
function formatDetails(item) {
  const envLines = Object.keys(item.environment).length
    ? Object.entries(item.environment)
        .map(([k, v]) => `<div class="catalog-detail-row"><code>${escapeHtml(k)}</code>: ${escapeHtml(String(v))}</div>`)
        .join("")
    : `<div class="catalog-detail-row hint">No environment variables.</div>`;
  const volLines = Object.keys(item.volumes).length
    ? Object.entries(item.volumes)
        .map(([name, v]) => `<div class="catalog-detail-row"><code>${escapeHtml(name)}</code> → <code>${escapeHtml(v.bind)}</code> (${escapeHtml(v.mode)})</div>`)
        .join("")
    : `<div class="catalog-detail-row hint">No volume mounts.</div>`;
  return `
    <div class="catalog-detail-group">
      <span class="catalog-detail-label">Environment</span>
      ${envLines}
    </div>
    <div class="catalog-detail-group">
      <span class="catalog-detail-label">Volumes</span>
      ${volLines}
    </div>
  `;
}
```

Then extend `renderCard()`'s template literal, inserting a details toggle + panel right before the closing `<div class="rule-status catalog-status" hidden>—</div>` line:

```javascript
function renderCard(item) {
  const card = document.createElement("div");
  card.className = "glass-card catalog-card";
  const installed = item.status !== "not_installed";
  const badge = STATUS_LABEL[item.status] || item.status;

  card.innerHTML = `
    <div class="catalog-card-top">
      <span class="catalog-badge">${escapeHtml(monogram(item.name))}</span>
      <div class="catalog-card-name">
        <span class="rule-title">${escapeHtml(item.name)}</span>
        <a class="doc-link-ext" href="${escapeHtml(item.doc_url)}" target="_blank" rel="noopener">docs ↗</a>
      </div>
      ${installed ? `<span class="lb-pill lb-pill-fresh">${escapeHtml(badge)}</span>` : ""}
    </div>
    <p class="rule-desc catalog-pitch">${escapeHtml(item.pitch)}</p>
    ${item.caveat ? `<p class="hint catalog-caveat">${escapeHtml(item.caveat)}</p>` : ""}
    <div class="catalog-card-foot">
      <span class="footprint">${escapeHtml(item.footprint)}${item.ports.length ? ` · port ${item.ports.join(", ")}` : ""}</span>
      <div class="catalog-card-actions"></div>
    </div>
    <button type="button" class="catalog-details-toggle" aria-expanded="false">Details ▾</button>
    <div class="catalog-details-panel" hidden>${formatDetails(item)}</div>
    <div class="rule-status catalog-status" hidden>—</div>
  `;

  const toggle = card.querySelector(".catalog-details-toggle");
  const panel = card.querySelector(".catalog-details-panel");
  toggle.addEventListener("click", () => {
    const isOpen = !panel.hidden;
    panel.hidden = isOpen;
    toggle.setAttribute("aria-expanded", String(!isOpen));
    toggle.textContent = isOpen ? "Details ▾" : "Details ▴";
  });

  const actions = card.querySelector(".catalog-card-actions");
  const status = card.querySelector(".catalog-status");

  if (!installed) {
    const btn = document.createElement("button");
    btn.className = "btn-primary";
    actions.appendChild(btn);
    armButton(btn, "Install", "Confirm install", async () => {
      btn.disabled = true;
      status.hidden = false;
      setStatusLine(status, "pending", "Pulling image and starting…");
      logLine("pending", `Catalog: install ${item.name} — requested`);
      try {
        const data = await postAction(`/api/catalog/${item.id}/install`, { confirm: true });
        setStatusLine(status, "success", data.message);
        logLine("ok", `Catalog: install ${item.name} — ${data.message}`);
        buildCatalog();
      } catch (e) {
        setStatusLine(status, "error", e.message);
        logLine("err", `Catalog: install ${item.name} — ${e.message}`);
        btn.disabled = false;
      }
    });
  } else {
    const btn = document.createElement("button");
    btn.className = "btn-danger";
    actions.appendChild(btn);
    armButton(btn, "Remove", "Confirm remove", async () => {
      btn.disabled = true;
      status.hidden = false;
      setStatusLine(status, "pending", "Stopping and removing…");
      logLine("pending", `Catalog: remove ${item.name} — requested`);
      try {
        const data = await postAction(`/api/catalog/${item.id}/remove`, { confirm: true, remove_volumes: false });
        setStatusLine(status, "success", data.message);
        logLine("ok", `Catalog: remove ${item.name} — ${data.message}`);
        buildCatalog();
      } catch (e) {
        setStatusLine(status, "error", e.message);
        logLine("err", `Catalog: remove ${item.name} — ${e.message}`);
        btn.disabled = false;
      }
    });
  }

  return card;
}
```

- [ ] **Step 2: Add CSS for the details toggle/panel to `style.css`**

Append near the existing `.catalog-*` rules (search `style.css` for `.catalog-card` to find the right neighborhood):

```css
.catalog-details-toggle {
  background: none;
  border: none;
  color: var(--accent);
  font: inherit;
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0.25rem 0;
  text-align: left;
}

.catalog-details-toggle:hover {
  text-decoration: underline;
}

.catalog-details-panel {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.5rem 0;
  border-top: 1px solid var(--border-soft);
  margin-top: 0.25rem;
}

.catalog-detail-group {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.catalog-detail-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  opacity: 0.7;
}

.catalog-detail-row {
  font-size: 0.8rem;
  font-family: var(--mono, monospace);
}

.catalog-detail-row.hint {
  opacity: 0.6;
  font-style: italic;
}
```

- [ ] **Step 3: Manual smoke test in the browser**

Start/rebuild the control panel (`docker compose up -d --build control-panel` per this stack's `feedback_control_panel_hard_reload_verification` memory rule), hard-reload (Ctrl+Shift+R), open the Catalog rail, click "Details ▾" on a card with a non-empty `environment` (e.g. Speedtest Tracker) and confirm the panel expands showing `OOKLA_EULA_GDPR: true` and its volume mapping; confirm the toggle collapses it again on second click; confirm a card with empty environment/volumes shows the "No environment variables." / "No volume mounts." fallback text instead of an empty panel.

- [ ] **Step 4: Commit**

```bash
git add control-panel/static/js/catalog.js control-panel/static/style.css
git commit -m "feat: add collapsible environment/volume details to catalog cards"
```

---

## Self-Review Notes

- **Spec coverage:** New categories (Task 2-4) ✓, unchanged schema enforced via gate test (Task 5) ✓, port-collision check before finalizing entries (Task 5, plus per-task review steps) ✓, card UI env/volume surfacing (Task 6-7) ✓, router extension confirmed necessary and implemented (Task 6) ✓, gate test for registry schema (Task 5) ✓, manual install/remove smoke test — deferred to execution time since it requires a live container pull per category; add as a manual check when executing Tasks 2-4's entries against a running stack, not scripted here since it needs real image pulls.
- **Placeholder scan:** Task 2-4's `entries/*.py` bodies are intentionally empty pending live research-agent output (this is not a placeholder violation — the research step itself, dispatching the agent and reviewing results, is the actual work of those steps; the schema/import/port-range constraints are fully specified so the eventual content is fully determined, not vague).
- **Type consistency:** `CATALOG: list[dict]` name and shape matches across every `entries/*.py` module and `registry.py`'s aggregation; `CATALOG_BY_ID`, `CATALOG_LABEL`, `NETWORK` names unchanged from the pre-split file so `router.py` needs no import changes from Task 1.

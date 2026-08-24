# Re-enable Anime (Movies), Branch B — Dedicated Radarr Instance — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a second, fully isolated Radarr instance (`radarr-anime`) for anime movies only, wired into every part of the fleet that needs to know about it, with a dedicated TRaSH-Guides-based quality profile, its own Plex library, and no regression to the existing Radarr/Sonarr/Bazarr/Unpackerr/Prowlarr/Seerr/Control-Panel setup.

**Architecture:** New `radarr-anime` container (same `hotio/radarr` image as the main Radarr), own config volume, own root folder (`/data/anime-movies`), own quality profile built from TRaSH-Guides' anime custom formats. Reuses the existing 3 Usenet indexers via Prowlarr (synced as a second Application), the existing NzbDAV download client (new `anime-movies` category), and the existing Unpackerr/Control-Panel/health-monitor/arr-config-sync/trash-guides-applier/request-manager-integrator tooling, each extended with a `radarr_anime` entry following the exact pattern already used for `radarr`/`sonarr`.

**Tech Stack:** Docker Compose, Radarr v3 REST API, Prowlarr v1 REST API, Seerr REST API (via `request-manager-integrator`), Python 3 stdlib (`urllib`, no new dependencies — matches every existing skill script in this repo).

## Global Constraints

- No torrent client, no debrid, no VPN — Usenet-only, per the approved design spec (`docs/superpowers/specs/2026-08-06-anime-reenable-design.md`).
- No Kometa / MyAnimeList changes — Kometa stays untouched (manual-only runs, commit `784a579`).
- Anime **movies only** — no Sonarr changes.
- Recyclarr stays removed stack-wide — no exception for anime. Custom formats are applied via the existing `trash-guides-applier` skill's manual JSON pattern (same as Criterion Collection, id 66, applied 2026-08-06).
- Container internal port for any Radarr instance is always `7878` (the image's fixed listen port) — only the **host-published** port differs between instances. `radarr-anime` publishes `7879:7878`.
- Every host-side skill script (`arr-config-sync/sync.py`, `trash-guides-applier/applier.py`, `request-manager-integrator/integrator.py`) resolves its base URL as `os.environ.get(f"{NAME.upper()}_URL", f"http://localhost:{port}")` — the `port` value in each script's app dict must stay `7878` (matches the in-network hostname:port these dicts also produce for Seerr/Control-Panel wiring), and the actual host access goes through a `RADARR_ANIME_URL=http://localhost:7879` override in `.env`. **Do not set these dicts' port to 7879** — that would break the in-network URLs the same dict feeds to Seerr.
- `health-monitor/monitor.py`'s `HTTP_SERVICES` dict has no such override mechanism — it always builds `http://localhost:{port}`, so its entry must use the real **host-published** port, `7879`, directly. This is a different convention from the other three scripts; do not copy-paste the wrong port between them.
- Bazarr **cannot** take a second Radarr connection (confirmed live: `config/bazarr/config/config.yaml` has a single `radarr:` block, not a list). Anime movies get no Bazarr subtitle coverage in this plan — documented as an accepted gap, not silently skipped.
- Every config file this plan edits already exists and follows an established pattern in this repo — no new frameworks, no new abstractions, additive dict entries following the exact shape neighboring entries already use.

---

### Task 1: TRaSH custom-format converter script

TRaSH-Guides publishes custom-format JSON with `fields` as a single dict (e.g. `{"value": "..."}`), but this repo's `trash-guides-applier` skill (and the live Radarr/Sonarr API) expects `fields` as a list of `{"name": ..., "value": ...}` objects — confirmed by comparing TRaSH's published `criterion-collection.json` against the real payload used to create it live (id 66, 2026-08-06). Hand-converting this per format (as was done once for Criterion Collection) doesn't scale to the ~3 anime formats this plan needs, and converting by hand again would be exactly the kind of repeated-manual-step CLAUDE.md says to skillify on the second occurrence. This is the third occurrence — it becomes a script.

**Files:**
- Create: `.claude/skills/trash-guides-applier/trash_cf_import.py`
- Test: manual invocation (see Step 3) — this is a one-shot conversion utility, not a long-lived service, so a live smoke-test against the real TRaSH-Guides raw JSON endpoint is the right verification, not a mocked unit test.

**Interfaces:**
- Produces: a CLI `python3 trash_cf_import.py <cf-filename-without-json>` that prints a JSON object shaped `{"name": ..., "score": <default trash_scores.default or 0>, "specifications": [...]}` with `fields` already converted to the list-of-`{name,value}` shape — directly appendable to any `profiles/*.json`'s `custom_formats` array.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Fetch a TRaSH-Guides Radarr/Sonarr custom-format JSON and convert it to this
repo's trash-guides-applier profile shape (fields-as-dict -> fields-as-list).

Usage:
    trash_cf_import.py <app radarr|sonarr> <cf-filename-without-.json>

Example:
    trash_cf_import.py radarr anime-dual-audio
"""
from __future__ import annotations

import json
import sys
import urllib.request

BASE = "https://raw.githubusercontent.com/TRaSH-Guides/Guides/master/docs/json/{app}/cf/{name}.json"


def convert(trash_cf: dict) -> dict:
    specs = []
    for spec in trash_cf["specifications"]:
        fields = spec["fields"]
        # TRaSH publishes a single {"value": x} dict; Radarr/Sonarr's real API
        # (and this repo's applier.py) expect a list of {"name": "value", "value": x}.
        field_list = [{"name": k, "value": v} for k, v in fields.items()]
        specs.append({
            "name": spec["name"],
            "implementation": spec["implementation"],
            "negate": spec.get("negate", False),
            "required": spec.get("required", False),
            "fields": field_list,
        })
    score = trash_cf.get("trash_scores", {}).get("default", 0)
    return {
        "name": trash_cf["name"],
        "score": score,
        "note": f"TRaSH-Guides trash_id {trash_cf['trash_id']}.",
        "specifications": specs,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 1
    app, name = sys.argv[1], sys.argv[2]
    url = BASE.format(app=app, name=name)
    with urllib.request.urlopen(url, timeout=15) as resp:
        trash_cf = json.loads(resp.read())
    print(json.dumps(convert(trash_cf), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x .claude/skills/trash-guides-applier/trash_cf_import.py
```

- [ ] **Step 3: Smoke-test against a known-good TRaSH format and diff against the hand-converted Criterion Collection entry**

```bash
python3 .claude/skills/trash-guides-applier/trash_cf_import.py radarr criterion-collection
```

Expected: JSON output whose `specifications` array matches (modulo key order) the hand-written entry already committed in `profiles/radarr-profiles.json` for "Criterion Collection" — confirms the converter produces API-correct output before trusting it for new formats.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/trash-guides-applier/trash_cf_import.py
git commit -m "feat(trash-guides-applier): add TRaSH custom-format converter script"
```

---

### Task 2: Generate anime custom formats and the anime profile JSON

**Files:**
- Create: `.claude/skills/trash-guides-applier/profiles/radarr-anime-profiles.json`

**Interfaces:**
- Consumes: Task 1's `trash_cf_import.py` output.
- Produces: a profile JSON in the same shape as `radarr-profiles.json`, containing one quality profile ("Anime") and three custom formats (Anime Dual Audio, Uncensored, Anime LQ Groups) — this is the curated subset covering the highest-value anime preferences (prefer dual-audio/uncensored, penalize known-bad release groups) without importing TRaSH's full ~16-file fansub-group-tier list, which is optional polish, not functional necessity, and can be layered in later the same way.

- [ ] **Step 1: Generate the three custom formats**

```bash
cd .claude/skills/trash-guides-applier
python3 trash_cf_import.py radarr anime-dual-audio > /tmp/cf-dual-audio.json
python3 trash_cf_import.py radarr uncensored > /tmp/cf-uncensored.json
python3 trash_cf_import.py radarr anime-lq-groups > /tmp/cf-lq-groups.json
```

Expected: three JSON files, each with a non-empty `specifications` array. `cf-lq-groups.json`'s `score` should be `-10000` (TRaSH's default penalty for known low-quality anime release groups).

- [ ] **Step 2: Assemble `radarr-anime-profiles.json`**

```python
import json

formats = []
for f in ("/tmp/cf-dual-audio.json", "/tmp/cf-uncensored.json", "/tmp/cf-lq-groups.json"):
    formats.append(json.load(open(f)))

profile = {
    "quality_profiles": [
        {
            "name": "Anime",
            "upgrade_allowed": True,
            "cutoff": "Bluray-1080p",
            "items": ["WEBDL-1080p", "WEBRip-1080p", "Bluray-1080p", "Remux-1080p"],
            "min_format_score": 0,
            "cutoff_format_score": 10000,
        }
    ],
    "custom_formats": formats,
}

with open(".claude/skills/trash-guides-applier/profiles/radarr-anime-profiles.json", "w") as fh:
    json.dump(profile, fh, indent=2)
    fh.write("\n")
```

Run this from the repo root as `python3 -c "<script above>"`, then verify:

```bash
python3 -m json.tool .claude/skills/trash-guides-applier/profiles/radarr-anime-profiles.json > /dev/null
```

Expected: exits 0 (valid JSON), and `custom_formats` has exactly 3 entries.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/trash-guides-applier/profiles/radarr-anime-profiles.json
git commit -m "feat(trash-guides-applier): add radarr-anime custom-format profile (dual audio, uncensored, LQ groups)"
```

---

### Task 3: Add the `radarr-anime` service to docker-compose.yml

**Files:**
- Modify: `docker-compose.yml` (insert new service block immediately after the existing `sonarr:` block, i.e. after line 104, before the `# Usenet` comment block at line 106)

**Interfaces:**
- Produces: a running `radarr-anime` container reachable at `http://radarr-anime:7878` from inside the compose network, and `http://localhost:7879` from the host.

- [ ] **Step 1: Create the host directories**

```bash
mkdir -p /home/bear/Claude/media-stack/config/radarr-anime
mkdir -p /home/bear/Claude/media-stack/media/anime-movies
```

- [ ] **Step 2: Insert the service block**

```yaml
  radarr-anime:
    <<: *common
    image: ghcr.io/hotio/radarr:release
    container_name: radarr-anime
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:7878/ping || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    volumes:
      - ./config/radarr-anime:/config
      - /mnt/remote/nzbdav:/mnt/remote/nzbdav:rslave
      - ./media/anime-movies:/data/anime-movies
    ports:
      - "7879:7878"
    mem_limit: 2g
    mem_reservation: 256m
    cpus: 2
```

- [ ] **Step 3: Validate the compose file and bring the service up**

```bash
docker compose config --quiet
docker compose up -d radarr-anime
```

Expected: `docker compose config` exits 0 with no error. `docker compose up -d radarr-anime` creates and starts exactly one new container.

- [ ] **Step 4: Verify it's healthy and get its auto-generated API key**

```bash
sleep 5
docker inspect --format '{{.State.Health.Status}}' radarr-anime
grep -oP '(?<=<ApiKey>)[^<]+' config/radarr-anime/config.xml
```

Expected: health status `healthy` (or `starting` immediately after boot, `healthy` within the 30s start period). The API key line prints a 32-character hex string.

- [ ] **Step 5: Record the API key and host URL in `.env`**

Append to `.env` (in the same section as the existing `RADARR_API_KEY`/`SONARR_API_KEY` lines):

```
RADARR_ANIME_API_KEY=<the key printed in Step 4>
RADARR_ANIME_URL=http://localhost:7879
```

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(radarr-anime): add dedicated Radarr instance for anime movies"
```

(`.env` is gitignored — confirm with `git check-ignore .env` before this commit, per CLAUDE.md's secrets rule; do not add it to the commit.)

---

### Task 4: Configure `radarr-anime`'s root folder, download client, and quality profile

**Files:** none (live API configuration only — matches the pattern already used to configure the existing Radarr/Sonarr, no local config files hold this state).

**Interfaces:**
- Consumes: `RADARR_ANIME_API_KEY`, `RADARR_ANIME_URL` from Task 3.
- Produces: a live root folder at `/data/anime-movies`, a `NzbDAV` download client entry with `movieCategory: anime-movies`, and the "Anime" quality profile from Task 2's JSON, live on `radarr-anime`.

- [ ] **Step 1: Add the root folder**

```bash
set -a; source .env; set +a
python3 -c "
import json, urllib.request, os
req = urllib.request.Request(
    'http://localhost:7879/api/v3/rootfolder',
    data=json.dumps({'path': '/data/anime-movies'}).encode(),
    method='POST',
    headers={'X-Api-Key': os.environ['RADARR_ANIME_API_KEY'], 'Content-Type': 'application/json'},
)
with urllib.request.urlopen(req, timeout=15) as resp:
    print(json.loads(resp.read()))
"
```

Expected: prints a JSON object with `"path": "/data/anime-movies"` and `"accessible": true`.

- [ ] **Step 2: Add the NzbDAV download client, category `anime-movies`**

First read the main Radarr's existing NzbDAV download-client config to copy its shape exactly (host, port, apiKey, urlBase, useSsl), only changing `movieCategory`:

```bash
set -a; source .env; set +a
python3 -c "
import json, urllib.request, os

def req(base, key, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f'{base}/api/v3{path}', data=data, method=method,
        headers={'X-Api-Key': key, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(r, timeout=15) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None

main_clients = req('http://localhost:7878', os.environ['RADARR_API_KEY'], 'GET', '/downloadclient')
nzbdav = next(c for c in main_clients if c['name'] == 'NzbDAV')

payload = {k: v for k, v in nzbdav.items() if k not in ('id',)}
for f in payload['fields']:
    if f['name'] == 'movieCategory':
        f['value'] = 'anime-movies'
    if f['name'] == 'apiKey':
        # Radarr masks apiKey as '********' on GET; NzbDAV's key is the same for every
        # arr app that talks to it, so reuse the main Radarr's actual key from .env
        # rather than posting the masked placeholder.
        f['value'] = os.environ['RADARR_API_KEY']  # placeholder line replaced below

created = req('http://localhost:7879', os.environ['RADARR_ANIME_API_KEY'], 'POST', '/downloadclient', payload)
print(created)
"
```

**Before running this:** the `apiKey` field on a SABnzbd-compatible download client entry is NzbDAV's own API key (not Radarr's), and the GET above masks it as `********` — replace the `f['value'] = os.environ['RADARR_API_KEY']` line with NzbDAV's real API key (find it via `grep -oP '(?<=api_key: )\S+' config/nzbdav/*.yaml` or the NzbDAV UI's settings page) before executing. Do not paste the masked placeholder value into the POST.

Expected: prints a JSON object with `"name": "NzbDAV"` and the `movieCategory` field's value `"anime-movies"`.

- [ ] **Step 3: Create the "Anime" quality profile skeleton via `applier.py`**

First, add `radarr_anime` to `applier.py`'s `APPS` dict (see Task 5, which this depends on) — do that step first, then:

```bash
cd .claude/skills/trash-guides-applier
RADARR_ANIME_URL=http://localhost:7879 RADARR_ANIME_API_KEY=$RADARR_ANIME_API_KEY \
  python3 applier.py apply radarr_anime --profiles profiles/radarr-anime-profiles.json
```

Expected: prints `created custom format: Anime Dual Audio`, `created custom format: Uncensored`, `created custom format: Anime LQ Groups`, and `created quality profile skeleton: Anime (finish item ordering in the Arr UI...)`.

- [ ] **Step 4: Score the custom formats onto the "Anime" profile**

`applier.py` creates formats and a profile skeleton but does not wire format scores into the profile (confirmed by reading `cmd_apply` — it never touches `formatItems`; this was true for the original `radarr-profiles.json` formats too, none of which are actually scored anywhere). Score them the same way Criterion Collection was scored onto the main "Anything" profile:

```bash
python3 -c "
import json, urllib.request, os

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f'http://localhost:7879/api/v3{path}', data=data, method=method,
        headers={'X-Api-Key': os.environ['RADARR_ANIME_API_KEY'], 'Content-Type': 'application/json'})
    with urllib.request.urlopen(r, timeout=15) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None

formats = {f['name']: f['id'] for f in req('GET', '/customformat')}
profiles = {p['name']: p['id'] for p in req('GET', '/qualityprofile')}
anime_profile_id = profiles['Anime']

scores = {
    'Anime Dual Audio': 25,
    'Uncensored': 15,
    'Anime LQ Groups': -10000,
}

profile = req('GET', f'/qualityprofile/{anime_profile_id}')
by_format_id = {item['format']: item for item in profile['formatItems']}
for name, score in scores.items():
    fid = formats[name]
    if fid in by_format_id:
        by_format_id[fid]['score'] = score
    else:
        profile['formatItems'].append({'format': fid, 'name': name, 'score': score})

updated = req('PUT', f'/qualityprofile/{anime_profile_id}', profile)
print([i for i in updated['formatItems'] if i['format'] in formats.values()])
"
```

Expected: prints the three format items with their scores (25, 15, -10000) attached.

- [ ] **Step 5: Commit**

No file changes in this task (all live API state) — nothing to commit. Note the completed configuration in the plan's checklist and move on.

---

### Task 5: Register `radarr_anime` across the host-side skill scripts

**Files:**
- Modify: `.claude/skills/trash-guides-applier/applier.py` (the `APPS` dict, currently `{"radarr": ..., "sonarr": ...}`)
- Modify: `.claude/skills/arr-config-sync/sync.py` (the `APPS` dict)
- Modify: `.claude/skills/request-manager-integrator/integrator.py` (the `ARR_APPS` dict)
- Modify: `.claude/skills/health-monitor/monitor.py` (the `HTTP_SERVICES` dict)

**Interfaces:**
- Produces: `radarr_anime` becomes a valid `<app>` argument to every one of these scripts' CLIs, resolving via `RADARR_ANIME_URL`/`RADARR_ANIME_API_KEY` for the first three, and via the literal host port `7879` for `monitor.py`.

- [ ] **Step 1: `applier.py`** — add to `APPS` (note: `port: 7878`, matching the constraint in Global Constraints, NOT `7879`):

```python
APPS = {
    "radarr": {"port": 7878, "api": "v3"},
    "sonarr": {"port": 8989, "api": "v3"},
    "radarr_anime": {"port": 7878, "api": "v3"},
}
```

- [ ] **Step 2: `sync.py`** — same pattern:

```python
APPS = {
    "radarr": {"port": 7878, "api": "v3"},
    "sonarr": {"port": 8989, "api": "v3"},
    "prowlarr": {"port": 9696, "api": "v1"},
    "radarr_anime": {"port": 7878, "api": "v3"},
}
```

- [ ] **Step 3: `integrator.py`** — same pattern, plus `seerr_kind` stays `"radarr"` (Seerr's settings endpoint type is the same regardless of which Radarr instance):

```python
ARR_APPS = {
    "radarr": {"port": 7878, "api": "v3", "seerr_kind": "radarr"},
    "sonarr": {"port": 8989, "api": "v3", "seerr_kind": "sonarr"},
    "radarr_anime": {"port": 7878, "api": "v3", "seerr_kind": "radarr"},
}
```

- [ ] **Step 4: `monitor.py`** — **host-published port, 7879**, no env-override mechanism exists in this script:

```python
HTTP_SERVICES = {
    "radarr": (7878, "/ping"),
    "sonarr": (8989, "/ping"),
    "prowlarr": (9696, "/ping"),
    "seerr": (5055, "/api/v1/status"),
    "control-panel": (8420, "/healthz"),
    "plex": (32400, "/identity"),
    "radarr-anime": (7879, "/ping"),
}
```

- [ ] **Step 5: Verify each script recognizes the new app**

```bash
set -a; source .env; set +a
cd .claude/skills/arr-config-sync && python3 sync.py backup radarr_anime --out /tmp/ && cd -
cd .claude/skills/health-monitor && python3 monitor.py http-only && cd -
```

Expected: `sync.py backup` succeeds and writes a backup file (proves `radarr_anime` resolves via `RADARR_ANIME_URL`/`RADARR_ANIME_API_KEY`). `monitor.py http-only` lists `radarr-anime` as reachable.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/trash-guides-applier/applier.py \
        .claude/skills/arr-config-sync/sync.py \
        .claude/skills/request-manager-integrator/integrator.py \
        .claude/skills/health-monitor/monitor.py
git commit -m "feat: register radarr-anime across fleet-tracking skill scripts"
```

---

### Task 6: Fix the FUSE-mount cascade gap

**Files:**
- Modify: `.claude/skills/docker-compose-manager/handler.py:43`

**Interfaces:**
- Produces: `radarr-anime` gets restarted along with `radarr`/`sonarr`/`plex`/`unpackerr`/`cleanuparr` whenever `nzbdav`/`nzbdav_rclone` remounts, instead of silently serving a stale mount handle.

This is not in the original design spec's checklist — it's a real bug this plan would otherwise introduce, of the same class already documented inline in this exact file for `nzbdav` itself (2026-07-29 correction). `radarr-anime` binds `/mnt/remote/nzbdav` (Task 3, Step 2) exactly like the other five dependents, so it belongs in this list.

- [ ] **Step 1: Edit the list**

```python
FUSE_MOUNT_DEPENDENTS = ["radarr", "sonarr", "plex", "unpackerr", "cleanuparr", "radarr-anime"]
```

- [ ] **Step 2: Verify**

```bash
grep -n "FUSE_MOUNT_DEPENDENTS" .claude/skills/docker-compose-manager/handler.py
python3 .claude/skills/docker-compose-manager/handler.py status radarr-anime
```

Expected: the grep shows `radarr-anime` in the list; the status command succeeds (proves the container name matches what Docker Compose actually calls it).

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/docker-compose-manager/handler.py
git commit -m "fix(docker-compose-manager): add radarr-anime to FUSE mount cascade dependents"
```

---

### Task 7: Wire Prowlarr

**Files:** none (live API only).

**Interfaces:**
- Consumes: the exact `Radarr` application payload shape already live for the main Radarr (`id: 1`, confirmed via `GET /api/v1/applications`).
- Produces: a second synced Application in Prowlarr pointed at `radarr-anime`, same 3 indexers, same sync categories.

- [ ] **Step 1: Create the application**

```bash
set -a; source .env; set +a
python3 -c "
import json, urllib.request, os

payload = {
    'syncLevel': 'fullSync',
    'enable': True,
    'name': 'Radarr (Anime)',
    'implementationName': 'Radarr',
    'implementation': 'Radarr',
    'configContract': 'RadarrSettings',
    'infoLink': 'https://wiki.servarr.com/prowlarr/supported#radarr',
    'tags': [],
    'fields': [
        {'name': 'prowlarrUrl', 'value': 'http://prowlarr:9696'},
        {'name': 'baseUrl', 'value': 'http://radarr-anime:7878'},
        {'name': 'apiKey', 'value': os.environ['RADARR_ANIME_API_KEY']},
        {'name': 'syncCategories', 'value': [2000]},
    ],
}
req = urllib.request.Request(
    'http://localhost:9696/api/v1/applications',
    data=json.dumps(payload).encode(), method='POST',
    headers={'X-Api-Key': os.environ['PROWLARR_API_KEY'], 'Content-Type': 'application/json'},
)
with urllib.request.urlopen(req, timeout=15) as resp:
    print(json.loads(resp.read()))
"
```

Expected: prints a JSON object with `"name": "Radarr (Anime)"` and a new `"id"`.

- [ ] **Step 2: Verify the sync actually pushed the 3 indexers to `radarr-anime`**

```bash
set -a; source .env; set +a
curl -s "http://localhost:7879/api/v3/indexer" -H "X-Api-Key: $RADARR_ANIME_API_KEY" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(len(data), 'indexers:', [i['name'] for i in data])
"
```

Expected: `3 indexers: ['DrunkenSlug', 'NZBgeek', 'NzbPlanet']` (Prowlarr pushes its own indexer set to every synced application automatically — no manual indexer config needed on `radarr-anime` itself).

- [ ] **Step 3: Commit**

No file changes — live API state only.

---

### Task 8: Wire Unpackerr

**Files:**
- Modify: `docker-compose.yml` (the `unpackerr:` service's `environment:` block, currently lines 617-629)

**Interfaces:**
- Produces: archives grabbed by `radarr-anime` get extracted and imported, same as the main Radarr.

- [ ] **Step 1: Add the second Radarr entry**

```yaml
      UN_RADARR_0_URL: http://radarr:7878
      UN_RADARR_0_API_KEY: ${RADARR_API_KEY}
      UN_RADARR_1_URL: http://radarr-anime:7878
      UN_RADARR_1_API_KEY: ${RADARR_ANIME_API_KEY}
      UN_SONARR_0_URL: http://sonarr:8989
      UN_SONARR_0_API_KEY: ${SONARR_API_KEY}
```

- [ ] **Step 2: Recreate Unpackerr and verify it picked up both Radarr entries**

```bash
docker compose up -d unpackerr
sleep 3
docker logs unpackerr 2>&1 | grep -i "radarr" | tail -5
```

Expected: log line confirming 2 Radarr servers configured (not "No Starr apps or folders configured", the exact failure this stack hit before, per the existing comment in this env block).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(unpackerr): wire radarr-anime as a second Radarr server"
```

---

### Task 9: Wire Control Panel

**Files:**
- Modify: `control-panel/app.py` (`ARR_APPS` dict at line 114, `QUEUE_ARR_APPS` tuple at line 139, `CONTAINER_LABELS` dict at line 149)

**Interfaces:**
- Consumes: `RADARR_ANIME_API_KEY` env var (already set in `.env` from Task 3).
- Produces: `radarr_anime` gets a dashboard tile, appears in queue/backlog views, and is reachable via every existing generic `ARR_APPS[app_name]`-parameterized endpoint.

Note: several call sites in `app.py` hardcode `ARR_APPS["radarr"]` directly (e.g. the Letterboxd/MDBList import-list endpoints, poster-sync) — these are intentionally scoped to the main movie library and are out of scope here; only the generic, `app_name`-parameterized endpoints (queue, backlog, unstick, custom-format-diff, etc.) pick up `radarr_anime` automatically once it's in the dicts below.

- [ ] **Step 1: Add to `ARR_APPS`**

```python
ARR_APPS = {
    "radarr": {
        "url": "http://radarr:7878",
        "api": "v3",
        "key": os.environ["RADARR_API_KEY"],
        "search_command": "MissingMoviesSearch",
        "label": "Radarr",
        "import_events": ("downloadFolderImported",),
    },
    "sonarr": {
        "url": "http://sonarr:8989",
        "api": "v3",
        "key": os.environ["SONARR_API_KEY"],
        "search_command": "MissingEpisodeSearch",
        "label": "Sonarr",
        "import_events": ("downloadFolderImported",),
    },
    "radarr_anime": {
        "url": "http://radarr-anime:7878",
        "api": "v3",
        "key": os.environ["RADARR_ANIME_API_KEY"],
        "search_command": "MissingMoviesSearch",
        "label": "Radarr (Anime)",
        "import_events": ("downloadFolderImported",),
    },
}
```

- [ ] **Step 2: Add to `QUEUE_ARR_APPS`**

```python
QUEUE_ARR_APPS = ("radarr", "sonarr", "radarr_anime")
```

- [ ] **Step 3: Add to `CONTAINER_LABELS`**

```python
    "radarr-anime": ("Radarr (Anime)", "dedicated Radarr instance for anime movies, Usenet-only"),
```

(Insert alongside the existing `"radarr": (...)` entry, keeping the container-name key convention — note the hyphen here matches the Docker container name `radarr-anime`, whereas `ARR_APPS`'s key is `radarr_anime` with an underscore, matching that dict's existing Python-identifier-safe key convention. This split is intentional and mirrors nothing else in the file exactly, so leave a one-line comment.)

- [ ] **Step 4: Rebuild and recreate the container**

```bash
docker compose build control-panel
docker compose up -d control-panel
sleep 3
curl -sf http://localhost:8420/healthz
```

Expected: `healthz` returns 200.

- [ ] **Step 5: Verify the new app shows up live**

```bash
set -a; source .env; set +a
curl -s -u <control-panel-auth-if-any> http://localhost:8420/api/queue/radarr_anime | python3 -m json.tool | head -5
```

Expected: a valid (possibly empty) queue response, not a 404/unknown-app error.

- [ ] **Step 6: Commit**

```bash
git add control-panel/app.py
git commit -m "feat(control-panel): register radarr-anime instance"
```

---

### Task 10: Wire Seerr (request manager)

**Files:** none (live API via the `request-manager-integrator` skill, whose code changes were already made in Task 5).

**Interfaces:**
- Consumes: `request-manager-integrator/integrator.py`'s `connect` command (Task 5).
- Produces: a live Seerr → `radarr-anime` connection scoped to the "Anime" quality profile and `/data/anime-movies` root folder, so anime movie requests route correctly.

- [ ] **Step 1: Run the connect command**

```bash
set -a; source .env; set +a
cd .claude/skills/request-manager-integrator
python3 integrator.py connect radarr_anime --root /data/anime-movies --profile "Anime" --name "Anime Movies"
```

Expected: prints confirmation of a new Radarr connection created in Seerr, hostname `radarr-anime`, port `7878` (container-internal — confirms the `seerr_kind`/`port` fix from Task 5 Step 3 is correct; if this instead shows port `7879`, stop and fix `integrator.py`'s `ARR_APPS` entry before proceeding, since that would mean Seerr is configured to reach a port Radarr isn't actually listening on inside the network).

- [ ] **Step 2: Verify live in Seerr**

```bash
curl -s http://localhost:5055/api/v1/settings/radarr -H "X-Api-Key: $SEERR_API_KEY" | python3 -c "
import json, sys
for s in json.load(sys.stdin):
    print(s['name'], s['hostname'], s['port'])
"
```

Expected: two entries — the existing main Radarr connection, and the new "Anime Movies" connection with `hostname: radarr-anime`, `port: 7878`.

- [ ] **Step 3: Commit**

No file changes — live API state only.

---

### Task 11: Create the "Anime Movies" Plex library

**Files:** none (live Plex API).

**Interfaces:**
- Produces: a new Plex library "Anime Movies", movie agent, scanning `/data/anime-movies` (the same path as the container's mount — confirm Plex's own container has a matching bind-mount to this path first).

- [ ] **Step 1: Check whether Plex's container already sees `/data/anime-movies`**

```bash
docker exec plex ls /data/anime-movies 2>&1
```

If this fails (path doesn't exist inside the Plex container), add the same bind mount used by `radarr-anime` to the `plex:` service's `volumes:` block in `docker-compose.yml`:

```yaml
      - ./media/anime-movies:/data/anime-movies
```

then `docker compose up -d plex` and re-run the `ls` check until it succeeds.

- [ ] **Step 2: Create the library**

```bash
set -a; source .env; set +a
curl -s -X POST "http://192.168.4.20:32400/library/sections?name=Anime%20Movies&type=movie&agent=tv.plex.agents.movie&scanner=Plex%20Movie&language=en-US&location=/data/anime-movies&X-Plex-Token=$PLEX_TOKEN"
```

Expected: HTTP 200, and the library appears in Plex's own UI/`GET /library/sections` listing.

- [ ] **Step 3: Verify**

```bash
curl -s "http://192.168.4.20:32400/library/sections?X-Plex-Token=$PLEX_TOKEN" | grep -o 'title="Anime Movies"'
```

Expected: one match.

- [ ] **Step 4: Commit**

If Step 1 required a `docker-compose.yml` change:

```bash
git add docker-compose.yml
git commit -m "feat(plex): mount anime-movies path for the new Anime Movies library"
```

Otherwise, no file changes.

---

### Task 12: Document the Bazarr gap and update fleet docs

**Files:**
- Modify: `README.md` (Known gaps / limitations section, or equivalent — follow the existing section this repo uses for documented trade-offs)
- Modify: `STACK.md` (History section, new version entry)
- Modify: `CLAUDE.md` (if it maintains a live services list — check for a `radarr`/`sonarr` mention to extend)

**Interfaces:** none — documentation only.

- [ ] **Step 1: Add the Bazarr gap note**

In README.md's known-gaps section, add:

> Anime movies (`radarr-anime`) have no Bazarr subtitle coverage — Bazarr's config schema supports only one Radarr connection at a time, already used by the main Radarr. Anime scene/fansub releases typically ship subtitles embedded in the file, which mitigates this in practice. Revisit if a real gap is found (e.g. a second dedicated Bazarr instance) — not done here to avoid unrequested scope growth.

- [ ] **Step 2: Add a STACK.md History entry**

Follow the exact format of the existing v10.19.0 removal entry and the v11.x entries above it — version-bump, one paragraph, concrete numbers (new container, 3 custom formats, 1 quality profile, 1 Plex library, list every integration point touched).

- [ ] **Step 3: Commit**

```bash
git add README.md STACK.md CLAUDE.md
git commit -m "docs: document anime-movies re-enablement (Branch B, dedicated instance)"
```

---

### Task 13: End-to-end verification

**Files:** none.

**Interfaces:** none — this is the acceptance test for the whole plan.

- [ ] **Step 1: Add one known-available anime movie manually via `radarr-anime`'s own UI or API**, targeting `/data/anime-movies` and the "Anime" quality profile.

- [ ] **Step 2: Trigger a search and watch it through the pipeline**

```bash
set -a; source .env; set +a
curl -s -X POST http://localhost:7879/api/v3/command -H "X-Api-Key: $RADARR_ANIME_API_KEY" -H "Content-Type: application/json" -d '{"name":"MoviesSearch","movieIds":[1]}'
```

Watch `docker logs -f radarr-anime`, then `docker logs -f nzbdav`, confirm the grab lands under the `anime-movies` category (Task 4, Step 2), gets extracted by Unpackerr (Task 8), and imports into `/data/anime-movies`.

- [ ] **Step 3: Confirm Plex visibility**

```bash
curl -s "http://192.168.4.20:32400/library/sections?X-Plex-Token=$PLEX_TOKEN"
```

Trigger a scan on the new "Anime Movies" library, confirm the title appears with correct metadata within one scan cycle.

- [ ] **Step 4: Confirm indexer query budget wasn't blown**

```bash
# via whichever mechanism currently surfaces indexer grab/query counts —
# Prowlarr's own UI (Indexers > History) or stack-queue-status
```

Expected: this single manual add/search consumed a small, bounded number of queries (1-3 per indexer), not a bulk sweep. Do not enable a bulk backlog import as part of this verification — per the design spec's query-budget guardrail, backlog catch-up happens in small manual batches over multiple days, as a separate, later, user-directed action.

- [ ] **Step 5: Final report**

Summarize: what was added, what's live, what's confirmed working end-to-end, and the one accepted gap (Bazarr). This is the plan's DONE/DONE_WITH_CONCERNS checkpoint per CLAUDE.md's completion protocol.

---

## Explicitly out of scope (carried over from the design spec)

- Anime TV series (Sonarr).
- Torrent/debrid/VPN.
- Kometa / MyAnimeList metadata.
- The old `sort-anime-movies.py` sweep script or any replacement — superseded by add-time root-folder choice (Task 1 of the "Common ground" section in the design spec).
- Extending the `stack-arr*` fish CLI commands to accept `radarr_anime` as an app argument — the underlying Control Panel API supports it (Task 9), but the fish wrapper's argument validation is a separate, smaller follow-up if CLI ergonomics for the new instance are wanted later.

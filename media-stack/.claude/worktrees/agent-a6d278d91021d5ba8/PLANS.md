# PLANS.md

Agent-oriented implementation spec for the current pending work: adding 7 new
services to the stack, fully wired in, plus a deferred phase-2 naming cleanup.

Source of truth for the human-readable version of this same plan (same content,
presentation-only): the published Artifact at
`https://claude.ai/code/artifact/6b115a3f-1972-44ff-968a-1d49a70fb281`. This file
is the canonical one an implementing agent should follow — if the two ever drift,
this file wins.

**Status: see each phase's own `Status:` line — that's the single source of
truth, not this paragraph.** As of last update (2026-08-13): Phases 1 (ntfy),
2 (Speedtest Tracker), 3 (Organizr), 4 (Scrutiny), 5 (GAPS-2),
6 (WatchState) and 7 (PlexAniSync) DONE — the whole 7-service batch has
landed. Phase 8 (naming cleanup) is now unblocked but still DEFERRED until
explicitly started. Phase 1 was built out
of this doc's stated risk order at Bear's explicit request (see its own
Phase 1 section for why that's a deliberate deviation, not an oversight).
See STACK.md's "ntfy added" and "Speedtest Tracker added" entries for the
full implementation records, including real bugs/assumption-mismatches
found and fixed during live verification of each.
Each phase below gets its own commit(s); update the `Status` line at the top
of a phase's section to `IN PROGRESS` / `DONE` as work lands, and update
`MEMORY.md` per the memory-reference note at the bottom.

---

## 0. How to use this doc

This is written so a fresh agent session, with no prior context, can pick up any
one phase and implement it correctly. Each service phase is self-contained:
it names exact files to create/edit, exact env vars, exact fish function names,
exact control-panel routes, and an acceptance checklist. Do not start a phase
until the previous one's acceptance checklist is fully green — phases are
ordered by risk, and skipping ahead defeats that.

**Global rules that apply to every phase (do not repeat per-phase unless a
phase deviates):**

- One commit per service. Commit message format: `feat: add <service> (<one-line
  what it does>)`. No `--no-verify`. Follow the repo's existing pre-commit hooks.
- Every phase ships with tests in the same commit: a pytest suite for the new
  control-panel router, and a live integration check run against the actual
  running container (documented per-phase as "Live verification").
- After a phase's commit, restart/redeploy per the `docker-compose-manager`
  skill and re-run `health-monitor` before starting the next phase.
- Secrets: prefer services that self-generate their own API key into their own
  `/config` volume, read off disk by the control-panel router (the existing
  `_tautulli_key()` pattern in `control-panel/services/tautulli/router.py` and
  the legacy copy in `control-panel/app.py:5193` — copy that pattern exactly,
  do not invent a new one). Only touch `secret-injector`
  (`.claude/skills/secret-injector`) if a service needs a key pushed *into* it
  rather than read back out.
- Naming: new fish functions and control-panel routes follow the *existing*
  `stack-<service>-<action>` / `/api/<service>/*` convention exactly as it
  stands today. Do **not** attempt to apply the phase-8 naming cleanup while
  building phases 1–7 — that would mix an unreviewed schema into services that
  haven't shipped yet. Match today's convention, nothing fancier.
- Every new docker-compose service block goes in a new `# new-services
  (2026-08)` section at the bottom of `docker-compose.yml`, mirroring the
  existing `# awesome-arr additions (2026-07-30)` section's structure (see
  `docker-compose.yml:780-784` for the comment-block style to match).
- Host ports for this batch are pre-allocated in the table below so there is
  no conflict-checking ambiguity mid-implementation.
- Before hardcoding any `<APP>_CONFIG__*`-style env var (or equivalent
  headless/env-driven config key) into a new service's compose block based on
  that project's own GitHub docs, verify the feature's "since vX.Y.Z" against
  the actually-deployed image tag, not just the docs on `main` — see the
  `verify-image-version-before-headless-config` skill. A mutable tag like
  `:latest` tracks the newest *stable* release only; docs on `main` can
  describe features not yet in any published image. Real incident this rule
  is from: hardcoding a documented nzbdav/InfiniDysk env var crashed that
  service's backend outright on recreate, and Docker's own healthcheck stayed
  green throughout because it was answered by a frontend/proxy layer
  independent of the crashed backend — don't trust `docker ps` health alone
  after a config-driven recreate; grep `docker logs <service>` for
  fatal/unknown-config errors too.
- For any live-verification step expected to take more than ~30s (a scan, a
  collector run, a library reconcile), use a background poll (Monitor-style:
  spawn it, poll on a longer interval, report progress rather than blocking)
  instead of a blocking wait. Frequent tight-interval polling against a
  service's own database while it's mid-write can itself add contention and
  slow the operation down — space polls out (tens of seconds, not sub-10s).

**Host port allocation (checked against every port currently in
`docker-compose.yml` as of 2026-08-08 — none of 8700–8706 are in use):**

| Service | Container port | Host port |
|---|---|---|
| ntfy | 80 | 8700 |
| Speedtest Tracker | 80 | 8701 |
| Organizr | 80 | 8702 |
| Scrutiny | 8080 | 8703 |
| GAPS-2 | 4277 | 8704 |
| WatchState | 8080 | 8705 |
| PlexAniSync | — (no web UI, scheduled job) | — |

---

## Phase 1 — ntfy

**Status:** DONE (2026-08-09)
**Risk:** low
**Role:** shared push-notification sink for the whole stack.

Built out of the plan's stated risk order at Bear's explicit request (asked for
"just step 1" when offered the choice between that and doing Phases 1-5 in
order). Implemented, live-verified, and committed - see STACK.md's "ntfy
added" entry for the full record. Two deviations from this section as
originally written, both discovered during live verification against the
real running Radarr/Sonarr/Prowlarr, not assumed from docs:
- 1.4's "Connect settings API call" needed every optional field present in
  the payload (empty string/list), not omitted - Radarr 400s with a
  misleading error otherwise.
- The plan didn't call out that Prowlarr's API is `/api/v1/`, not `/api/v3/`
  like Radarr/Sonarr - the setup-connections route reads each app's real
  version from `ARR_APPS`/`PROWLARR_CFG` rather than assuming v3 everywhere.

### 1.1 Compose

Add to `docker-compose.yml` in the new-services section:

```yaml
  ntfy:
    restart: unless-stopped
    image: binwiederhier/ntfy
    container_name: ntfy
    command: serve
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "wget -q --tries=1 http://localhost:80/v1/health -O - | grep -q true || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    volumes:
      - ./config/ntfy/cache:/var/cache/ntfy
      - ./config/ntfy/etc:/etc/ntfy
    ports:
      - "8700:80"
    mem_limit: 256m
    mem_reservation: 32m
    cpus: 1
```

Create `./config/ntfy/etc/server.yml` (mounted, not baked into the image) with
cache retention tuned down from the unbounded default:

```yaml
base-url: "http://<host>:8700"
cache-file: "/var/cache/ntfy/cache.db"
cache-duration: "72h"
behind-proxy: false
```

No auth-file needed initially — anonymous read/write is acceptable since the
stack is not exposed publicly. Note this explicitly in the STACK.md entry
(1.6) so it isn't mistaken for an oversight later.

### 1.2 Secrets

None. ntfy needs no API key for basic publish/subscribe use.

### 1.3 Health monitor

Add to `HTTP_SERVICES` in `.claude/skills/health-monitor/monitor.py`:

```python
"ntfy": (8700, "/v1/health"),
```

### 1.4 Radarr/Sonarr/Prowlarr wiring

For each of `radarr`, `radarr-anime`, `sonarr`, `sonarr-anime`, `prowlarr`:
Settings → Connect → add ntfy connection, pointing at
`http://ntfy:80/<app-name>-alerts` (e.g. topic `radarr-alerts`,
`sonarr-anime-alerts`). Trigger on at minimum: health issue, application
update, manual interaction required. This is done via each app's REST API
(`POST /api/v3/notification`) inside the control-panel router below, not by
hand in each UI — write a one-time setup script or router action, not a
manual click-through, since this repeats 5 times identically.

### 1.5 Fish functions

New file `fish-functions/stack-ntfy-*.fish`:

- `stack-ntfy-publish <topic> <message>` — thin wrapper calling
  `__stack_api POST /api/ntfy/publish` with `{topic, message}` body. Mirrors
  the existing `__stack_api` pattern used by every other `stack-<service>-*`
  function — see `fish-functions/stack-tautulli-stats.fish:3` for the exact
  shape to copy.
- `stack-ntfy-topics` — lists configured topics (reads server.yml via the
  router), calls `__stack_api GET /api/ntfy/topics`.
- `stack-notify-test` already exists (see the existing function list) —
  **update it**, don't duplicate it, to route through ntfy once ntfy exists.
  Check its current implementation before touching it; if it already posts to
  a different notification channel, add ntfy as an additional sink rather than
  replacing existing behavior, and confirm with a quick check of what it
  currently does before assuming.

### 1.6 Control panel

- New `control-panel/services/ntfy/router.py`: `SERVICE_META`, `APIRouter`,
  routes `POST /api/ntfy/publish`, `GET /api/ntfy/topics`, `GET
  /api/ntfy/health`. Mirror `control-panel/services/tautulli/router.py`'s
  structure exactly (imports, error handling, response shape).
- Register in the fleet: `control-panel/app.py` — add to the fleet
  label/description dict (same place as the existing entries near line 161),
  add to `NEW_APP_CONTAINERS` (~line 5818) and the port map (~line 5827).
- Frontend: `control-panel/static/js/fleet.js` — add ntfy to the
  notifications/utility category grouping. `control-panel/static/js/reference.js`
  — add `{id: "ntfy", label: "ntfy", port: 8700}` tile. `control-panel/static/commands.json`
  — add entries for the two new CLI commands mirroring the router routes.
- `STACK.md` — new entry: what ntfy is, why it was added (central alert sink
  instead of N per-app configs), the anonymous-access note from 1.1, host port.

### 1.7 Tests

- `tests/control_panel/services/test_ntfy_router.py` — pytest, mock the ntfy
  HTTP client, assert publish/topics/health routes behave (200 on success,
  meaningful error on ntfy unreachable). Match the test file structure of
  the existing tautulli router tests (find via `find tests -iname
  '*tautulli*'` and mirror it).
- **Live verification** (run once against the real deployed container, record
  result in the phase status note, not a permanent test): `curl -d "hello" \
  http://localhost:8700/media-stack-test`, confirm delivery via the ntfy web
  UI or app, then delete the test topic's cached messages.
- Confirm `health-monitor` reports ntfy green.
- Confirm at least one Arr app (e.g. Radarr) successfully delivers a real
  ntfy notification end-to-end (trigger a test notification from Radarr's
  Connect settings).

### 1.8 Acceptance

Ticked 2026-08-13, four days after this phase shipped - the boxes were left
blank on 2026-08-09 even though STACK.md recorded the verification. Every item
below was re-verified live on 2026-08-13 rather than taken from that record.

- [x] Container healthy via `docker compose ps` (up 2 days, healthy)
- [x] health-monitor probe green (`ntfy` HTTP 200 on `/v1/health`)
- [x] pytest suite passing (`tests/control_panel/test_ntfy_router.py`, 10 cases)
- [x] Live publish/subscribe verified - published to `plans-md-acceptance` and
      read the same message back off the topic's JSON stream
- [x] All 5 Arr-family apps have a working ntfy connection: radarr, sonarr,
      radarr-anime, sonarr-anime (7 triggers each) and prowlarr (4 - it has
      fewer trigger types, not a misconfiguration)
- [x] Fish functions callable: `stack-ntfy-topics` (5 topics),
      `stack-ntfy-publish`, and `stack-notify-test`, which was **updated**
      rather than duplicated - `/api/notify/test` now fans out to Discord
      *and* ntfy and reports both results independently, so one dead sink
      cannot mask the other
- [x] STACK.md entry added (`## ntfy added:`, 2026-08-09)
- [x] Committed as its own commit (2b70fae)

---

## Phase 2 — Speedtest Tracker

**Status:** DONE (2026-08-11)
**Risk:** low
**Role:** scheduled ISP speed monitoring + history, so link degradation is
visible before it's the reason downloads/streaming feel slow.

Implemented, live-verified, and committed - see STACK.md's "Speedtest Tracker
added" entry for the full record, including two real bugs found and fixed
during live verification (not just discovered during planning): the Ookla
CLI's IPv6 socket failure that made every run fail 100% of the time until a
`sysctls` fix landed, and a naive-vs-aware datetime 500 in `/history` caused
by the live API's real timestamp format differing from its own docs. Also
two deviations from this section as originally written, both discovered
during implementation, not assumed from docs:
- 2.2's default-login note is moot - the image's `ADMIN_NAME`/`ADMIN_EMAIL`/
  `ADMIN_PASSWORD` env vars seed a real admin on first boot, so there was
  never a default `admin@example.com`/`password` login to change.
- 2.5's "sqlite query" assumption for reading the API token back out was
  wrong - Sanctum only stores a hash, and the image has no `tinker`. The
  token was minted by replicating Sanctum's own token-generation algorithm
  and inserting the row directly via Python's `sqlite3` against the
  bind-mounted DB file. Full detail in STACK.md.

### 2.1 Compose

```yaml
  speedtest-tracker:
    restart: unless-stopped
    image: lscr.io/linuxserver/speedtest-tracker:latest
    container_name: speedtest-tracker
    environment:
      PUID: "${PUID}"
      PGID: "${PGID}"
      TZ: "${TZ}"
      APP_KEY: "${SPEEDTEST_TRACKER_APP_KEY}"
      APP_URL: "http://localhost:8701"
      DB_CONNECTION: sqlite
      SPEEDTEST_SCHEDULE: "0 * * * *"
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:80/api/healthcheck || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    volumes:
      - ./config/speedtest-tracker:/config
    ports:
      - "8701:80"
    mem_limit: 512m
    mem_reservation: 64m
    cpus: 1
```

`SPEEDTEST_SCHEDULE: "0 * * * *"` is hourly — deliberately not upstream's
15-minute default, since a full speedtest saturates the link and running it
4x/hour is unnecessary noise for a monitoring signal, not a benchmark tool.

### 2.2 Secrets

`APP_KEY` must be generated once (Laravel app key, 32-byte base64) and stored
in `.env` as `SPEEDTEST_TRACKER_APP_KEY`. Generate with:
`docker run --rm lscr.io/linuxserver/speedtest-tracker:latest php artisan
key:generate --show` (or equivalent one-liner — verify the exact command
against the image's entrypoint at implementation time, since LinuxServer
images sometimes wrap this differently). Add `SPEEDTEST_TRACKER_APP_KEY` to
`.env.example` as a placeholder with a comment explaining how to generate it.

Default web login (`admin@example.com` / `password`) must be changed on
first login — note this as a manual one-time step in the STACK.md entry, it
cannot be automated via the API before the app has booted once.

### 2.3 Health monitor

```python
"speedtest-tracker": (8701, "/api/healthcheck"),
```

### 2.4 Fish functions

- `stack-speedtest-latest` — `GET /api/speedtest/latest`, returns most recent
  result (down/up/ping/jitter).
- `stack-speedtest-history [days]` — `GET /api/speedtest/history?days=<n>`,
  default 7.
- `stack-speedtest-run-now` — `POST /api/speedtest/run`, triggers an
  out-of-schedule test.

### 2.5 Control panel

- `control-panel/services/speedtest_tracker/router.py` — routes matching
  2.4's three fish functions, reading Speedtest Tracker's own REST API
  (`/api/*` on the container, authenticated via a Sanctum token generated
  in-app — same read-off-disk-or-DB pattern as other self-generated keys;
  confirm exact token location during implementation since LinuxServer's
  Speedtest Tracker stores it in its sqlite DB, not a flat config file like
  Tautulli — the read helper will need a sqlite query, not a file read).
- Fleet/tile/commands.json registration — same three-file pattern as 1.6.
- STACK.md entry: schedule choice, APP_KEY generation step, sqlite token
  quirk.

### 2.6 Tests

- pytest for the router (mock the Speedtest Tracker API/DB read).
- Live verification: trigger `stack-speedtest-run-now`, confirm a result
  appears in Speedtest Tracker's own UI and via `stack-speedtest-latest`.
- health-monitor green.

### 2.7 Acceptance

- [x] Container healthy
- [x] APP_KEY generated and in `.env` (not committed — verified `.gitignore`
      covers `.env` before this phase's commit)
- [x] Default login changed (moot - seeded correctly via ADMIN_* env vars,
      see the deviation note above)
- [x] health-monitor probe green
- [x] pytest suite passing
- [x] Live speedtest run + readback verified
- [x] Fish functions callable
- [x] STACK.md entry added
- [x] Committed as its own commit (43ed2fb - this box was left unticked by
      mistake; the commit landed 2026-08-11 and was pushed the same night)

---

## Phase 3 — Organizr

**Status:** DONE (2026-08-12), scope reduced same day — see "Anime libraries
removed" below.
**Risk:** low
**Role:** single landing dashboard with tabs for every service in the stack
(existing + all new ones from this batch).

Implemented, live-verified, and committed — see STACK.md's "Organizr added"
entry for the full record. **This section as originally written was wrong in
four places**, all corrected inline below and all found by reading upstream
source rather than trusting the docs. The headline one: 3.4's "manual by
design, do not attempt to script this" was false. Organizr exposes a full
tabs REST API *and* a bypass-listed setup-wizard endpoint, so the entire
phase provisions from a bare volume with one command
(`scripts/organizr-provision.py`) and has no manual step at all.

### 3.1 Compose

**Corrected at implementation time:** image is `ghcr.io/organizr/organizr`,
not the `organizr/organizr` Docker Hub path below — the `docker-organizr`
README lists the Hub name (and `organizrtools/organizr-v2` before it) as the
legacy name ghcr replaced. `fpm` is also inert: the base image is "now set up
to use the unix socket exclusively", so that toggle does nothing and was
dropped. `branch` is real and was kept. Healthcheck hits `/api/v2/ping`
rather than `/` — ping is unauthenticated and hard-200s both before and after
the wizard, whereas `/` serves the wizard pre-setup and 302s to login after.

```yaml
  organizr:
    restart: unless-stopped
    image: organizr/organizr:latest
    container_name: organizr
    environment:
      PUID: "${PUID}"
      PGID: "${PGID}"
      TZ: "${TZ}"
      fpm: "false"
      branch: "v2-master"
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:80/ || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    volumes:
      - ./config/organizr:/config
    ports:
      - "8702:80"
    mem_limit: 256m
    mem_reservation: 32m
    cpus: 1
```

### 3.2 Secrets

~~None required for base operation (single-user setup, auth optional via
Organizr's own UI).~~

**Wrong.** There is no unauthenticated Organizr: the setup wizard mandates an
admin account, and every API route past `/ping` runs through
`qualifyRequest()`. Six `.env` keys were added — `ORGANIZR_API_KEY`,
`ORGANIZR_HASH_KEY`, `ORGANIZR_ADMIN_USERNAME`, `ORGANIZR_ADMIN_EMAIL`,
`ORGANIZR_ADMIN_PASSWORD`, `ORGANIZR_REGISTRATION_PASSWORD`.

**Landmine:** `ORGANIZR_API_KEY` must be exactly 20 characters.
`isApprovedRequest` gates on `strlen($requesterToken) == 20` *before* it
compares the value (`api/classes/organizr.class.php:4609`), so a wrong-length
key 401s every write route with a message that reads like a permissions
problem and is not.

### 3.3 Health monitor

```python
"organizr": (8702, "/"),
```

### 3.4 Tab provisioning (~~manual by design~~ — fully scripted)

~~Organizr has no tab-provisioning API; all tab state lives in its own SQLite
DB. Do not attempt to script this.~~

**Wrong on both counts.** What upstream source actually shows:

- `api/v2/routes/tabs.php` defines a full `GET/POST/PUT/DELETE /api/v2/tabs`.
- `isApprovedRequest` (`api/classes/organizr.class.php:4596-4623`) accepts a
  `Token:` header equal to the configured API key, treats that caller as
  admin, and short-circuits the CSRF formKey check that would otherwise
  reject any non-browser POST.
- `POST /api/v2/wizard` is in `$GLOBALS['bypass']` (`api/v2/index.php:41-52`)
  so first-boot setup needs no auth at all, and it takes the API key as an
  *input* — we choose it, Organizr doesn't generate it. That is what makes
  every later step scriptable. `wizardConfig()` self-disables once config and
  DB exist, so the call is naturally idempotent.

So step 1 below (the "not automatable" wizard) and step 2 (18 tabs by hand)
are both a single idempotent run of `scripts/organizr-provision.py`, which is
what PLANS.md 1.4's own rule about scripting repeated click-throughs asks for.

Step 3's framing check was still done, just up front rather than per-tab
during a manual pass: every live service was swept for `X-Frame-Options` and
CSP `frame-ancestors`, following redirects. Exactly one service refuses
framing — nzbdav (`X-Frame-Options: SAMEORIGIN`) — so it is the only
`type=2` (New Window) tab and the other 17 are `type=1` (iFrame). That result
is asserted by `test_organizr_router.py::test_nzbdav_is_the_only_new_window_tab`
rather than only written down, and the full table is in the STACK.md entry.

Original steps, kept for the record:

1. ~~On first boot, log into Organizr's setup wizard (documented step, not
   automatable).~~
2. Add one tab per service currently in the stack, using the port table from
   this doc plus the existing `docker-compose.yml` port mappings. Build the
   full tab list from `docker-compose.yml`'s port bindings at implementation
   time — do not hand-copy a stale list into this doc, since ports here can
   drift. *(Done — the list is derived in `services/organizr/tabs.py`, which
   both the script and the router import, so there is one definition.)*
3. For each tab, check whether the target service sets `X-Frame-Options` or
   a restrictive CSP before enabling iframe mode; if it blocks framing, set
   that tab to "open in new tab" mode instead of iframe. Record which
   services needed which mode in the STACK.md entry so a future service
   addition to Organizr doesn't have to re-discover this per-service. *(Done
   — see above.)*

### 3.5 Fish functions / control panel

- `stack-organizr-tabs` — `GET /api/organizr/tabs`. It does expose a listing
  API (`GET /api/v2/tabs`), so the SQLite-fallback branch below never
  applied. Also reports which of this stack's services are missing a tab.
- `stack-organizr-sync` — `POST /api/organizr/tabs/sync`, added beyond this
  section's plan. Adds a tab for any service in the canonical table that
  doesn't have one. Additive only: never edits or deletes an existing tab, so
  a hand-tweaked tab survives and a deliberately-added stray isn't reaped.
  This is what makes "add a service to the stack" a one-row change.
- Fleet/tile/commands.json registration — same pattern as 1.6, **except**
  1.6's `app.py` step no longer exists: routers auto-mount by directory scan
  (`control-panel/main.py:134-146`), so the real edit sites are
  `core/docker_client.py`'s fleet dict, `static/js/fleet.js`,
  `static/js/reference.js` and `static/commands.json`. Note
  `services/catalog/registry.py` is the *newapps installer* catalog, a
  different thing — leave it alone.

### 3.6 Tests

- pytest for the router's read-only tab-list endpoint.
- Live verification: manual click-through confirming every tab loads its
  target service correctly (this is the one phase where "test" includes a
  manual UI pass, since tab provisioning itself is manual — see 3.4).
- health-monitor green.

### 3.7 Acceptance

- [x] Container healthy
- [x] health-monitor probe green
- [x] Every existing + new service has a working tab (iframe or direct-link,
      whichever the per-service framing check calls for) — 18 tabs, 17 iframe
      + nzbdav new-window
- [x] pytest suite passing for the read-only router — 15 cases, full suite 654
- [x] STACK.md entry documents the iframe/direct-link decision per service
- [x] Committed as its own commit

---

## Phase 4 — Scrutiny

**Status:** DONE (2026-08-12)
**Risk:** low
**Role:** disk S.M.A.R.T. health trending and failure prediction, layered on
top of (not replacing) the existing `stack-disk-health` raw-`smartctl` check.

Implemented, live-verified, and committed — see STACK.md's "Scrutiny added"
entry for the full record.

**Scope reality this section did not anticipate:** this host has exactly ONE
physical disk, a 954GB NVMe. `zram0` is compressed RAM swap, not a disk, and
everything else the stack serves lives on the Usenet-backed FUSE mount, which
has no SMART data. The two-SATA-disk shape below is not this machine.

### 4.1 Compose

**Corrected at implementation time, three ways:**

- The device to pass is `/dev/nvme0`, the NVMe *controller character device*,
  because that is what `smartctl --scan` reports here. Upstream says to pass
  exactly what `--scan` lists; the `/dev/sdX` block-device shape below would
  have registered nothing. `/dev/nvme0n1` is passed too for udev metadata.
- `SYS_ADMIN` is **mandatory**, not the conditional "if any host disk is
  NVMe" below — every disk here is NVMe. Without it Scrutiny registers the
  device and then silently reports no SMART data at all.
- Healthcheck and API paths in 4.3/4.4 were verified correct against
  `webapp/backend/pkg/web/server.go` and needed no change.

```yaml
  scrutiny:
    restart: unless-stopped
    image: ghcr.io/analogj/scrutiny:latest-omnibus
    container_name: scrutiny
    cap_add:
      - SYS_RAWIO
    devices:
      # Enumerate every physical disk backing this host explicitly at
      # implementation time via `lsblk -d -o NAME,TYPE` — do not use a
      # blanket /dev:/dev or --privileged. Example shape:
      - "/dev/sda:/dev/sda"
      - "/dev/sdb:/dev/sdb"
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8080/api/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    volumes:
      - ./config/scrutiny/config:/opt/scrutiny/config
      - ./config/scrutiny/influxdb:/opt/scrutiny/influxdb
      - /run/udev:/run/udev:ro
    ports:
      - "8703:8080"
    mem_limit: 512m
    mem_reservation: 64m
    cpus: 1
```

If any host disk is NVMe, also add `cap_add: [SYS_ADMIN]`. Check
`lsblk -d -o NAME,ROTA,TRAN` at implementation time to decide.

### 4.2 Secrets

None.

### 4.3 Health monitor

```python
"scrutiny": (8703, "/api/health"),
```

### 4.4 Fish functions

- `stack-scrutiny-summary` — `GET /api/scrutiny/summary` (proxies Scrutiny's
  own `/api/summary`), all-disk status at a glance.
- `stack-scrutiny-disk [disk_id]` — `GET /api/scrutiny/disk?disk_id=<id>`
  (proxies `/api/device/{uuid}/details`), per-disk SMART attributes. Scrutiny
  only accepts its internal UUID, so the router resolves a device name or
  serial first; the argument is optional entirely on a single-disk host.

Two more shipped beyond this section:

- `stack-scrutiny-collect` — runs the collector now. Without it the only way
  to know collection works is to wait for the midnight cron.
- `stack-scrutiny-alert-test` — fires Scrutiny's own test notification
  through the ntfy sink from Phase 1 (see 4.5).

### 4.5 Control panel

- `control-panel/services/scrutiny/router.py` — proxy routes for the two
  fish functions above, straightforward passthrough to Scrutiny's own REST
  API (no auth needed).
- Fleet/tile/commands.json registration — same pattern as 1.6.
- STACK.md entry: relationship to existing `stack-disk-health`, the explicit
  device list decision (why not `--privileged`), cron schedule (default
  daily, leave as-is — SMART trending doesn't need to run more often).
- **Beyond this section:** disk-failure alerts wired into the Phase 1 ntfy
  sink via Scrutiny's native shoutrrr support, as the `SCRUTINY_NOTIFY_URLS`
  env var in `docker-compose.yml` (`scheme=http` required, shoutrrr defaults
  to https/443). Env var, not a config file, because this repo gitignores
  `config/` wholesale — anything under there exists only on the live host and
  vanishes on a rebuild. **Worth generalising to Phases 5-7: prefer an env
  var over a file under `config/` whenever the app supports it.** Verified
  end-to-end by polling the topic, not assumed. Note Scrutiny answers HTTP
  200 with `success: false` on a broken notify URL, so check the body, not
  the status.

### 4.6 Tests

- pytest for the router (mock Scrutiny's API).
- Live verification: confirm every physical disk enumerated in the compose
  `devices` list actually shows up with populated SMART data in
  `stack-scrutiny-summary` within one collector cron cycle (default daily —
  trigger a manual collector run for verification instead of waiting a full
  day: `docker exec scrutiny /opt/scrutiny/bin/scrutiny-collector-metrics
  run`).
- health-monitor green.

### 4.7 Acceptance

- [x] Container healthy
- [x] Every physical disk has SMART data populated — the one NVMe: 5% used,
      100% spare, 0 media errors, 43C, 2083h
- [x] health-monitor probe green
- [x] pytest suite passing — 23 cases, full suite 677
- [x] Fish functions callable — all four
- [x] STACK.md entry added
- [x] Committed as its own commit

---

## Phase 5 — GAPS-2

**Status:** DONE (2026-08-12)
**Risk:** medium — touches Radarr (can push adds) and reads the Plex library
directly; scan cost against the FUSE mount needs real tuning, not defaults.

Implemented, live-verified, and committed — see STACK.md's "GAPS-2 added"
entry for the full record. **The FUSE-mount risk this section leads with does
not apply**: GAPS-2 reads the owned-title list from Plex's API and then does
TMDB/TheTVDB lookups, and never touches the mount. The full four-library
sweep, 16,873 owned movies included, took about four minutes. Four other
corrections, all from reading upstream source rather than its docs:

- 5.2's Plex "OAuth login flow (interactive, one-time)" is avoidable —
  `POST /api/plex/connect-manual` takes a plain `{serverUrl, token}`, so the
  whole service provisions headlessly via `scripts/gaps2-provision.py`.
- 5.2's `TMDB_API_KEY` is called `TMDB_KEY` here, and `TVDB_KEY` already
  existed too.
- 5.3's `/` healthcheck would have been wrong: `/` is the bundled Angular
  frontend and answers 200 with a dead backend behind it. Both the compose
  healthcheck and the health-monitor probe use `/api/about`.
- 5.1's `/app/data` backup note: restic was removed 2026-08-12, but
  `stack-claude-full-backup` tars all of `~/Claude` with no excludes, so the
  volume is already covered. Verified, not assumed.

**Scope decisions Bear made at implementation time (2026-08-12):**

- **TV as well as movies**, beyond this section's movies-only scope. GAPS-2
  ships a full Sonarr blueprint and TheTVDB franchise scanning, and `TVDB_KEY`
  was already present.
- **One container, with the control panel owning push routing**, rather than
  a second `gaps2-anime` instance. GAPS-2 stores only one Radarr and one
  Sonarr connection, so it cannot honour 5.2's anime-scope decision by
  itself — see the STACK.md entry for why scans therefore run one library at
  a time, and why GAPS-2's own Radarr/Sonarr are deliberately left
  unconfigured.
- **No notifications.** GAPS-2 supports Discord/Telegram/email only, with no
  ntfy or generic-webhook provider, so the Phase 1 sink can't be reused
  without a translation bridge. A missing-title list is advisory, not an
  alert condition.
Concrete numbers from this stack (2026-08-11): a single library-wide
filesystem walk over the FUSE mount can run tens of minutes on a library this
size, and Plex's own DB reconcile (`emptyTrash` over ~1,176 items) took ~45
min with real write contention (`Waited over 10 seconds for a busy database`
in Plex's log). GAPS-2 doing a full Plex+Radarr cross-reference at scan time
is the same shape of operation. **Read `fuse-hang-vs-slow-diagnosis` and
`plex-marked-deleted-db-contention` before picking a scan schedule** — don't
default to upstream's schedule or assume "check current movie count" alone
is enough tuning input; also avoid scheduling GAPS-2 scans to overlap a Plex
library refresh or trash-empty window (see `scoped-plex-library-refresh`).

**Anime-scope decision, locked in ahead of implementation (2026-08-09):** Bear
was asked "general Radarr only" (this section's stated default) vs "both
general and anime" while Phase 1 was being built, and chose **both** — GAPS-2
should scan and report gaps for `radarr` and `radarr_anime`. This overrides
5.2's default below; when 5.2 is implemented, wire GAPS-2 (or the
`stack-gaps2-*` router) against both Radarr instances, not just the general
one.

### 5.1 Compose

```yaml
  gaps2:
    restart: unless-stopped
    image: primetime43/gaps-2:latest
    container_name: gaps2
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:4277/ || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    volumes:
      - ./config/gaps2:/app/data
    ports:
      - "8704:4277"
    mem_limit: 1024m
    mem_reservation: 128m
    cpus: 2
```

`/app/data` holds `config.enc` and `.config.key` — losing either bricks the
saved configuration (Plex OAuth, Radarr key, TMDB key all re-entry required).
**This volume must be included in whatever backup mechanism replaces the
retired restic setup** — verify new top-level `./config/<service>`
directories get picked up automatically rather than taking it on faith,
since a silently-unbacked-up encryption key is the actual failure mode
this note exists to prevent.

### 5.2 Secrets

Entered via GAPS-2's own Settings UI post-boot, not pre-seeded:
- Plex: OAuth login flow (interactive, one-time).
- Radarr: API key + URL — use the existing Radarr instance; if GAPS-2 should
  also scan the radarr-anime library, this needs a decision Bear should make
  at implementation time (does GAPS-2 report anime gaps too, or only
  general-library gaps? default to general Radarr only unless told
  otherwise, since anime "missing from Plex" detection is noisier given
  the existing anime backfill history in this stack).
- TMDB API key: reuse the same TMDB key already used elsewhere in the stack
  (check `.env` for an existing `TMDB_API_KEY` before asking Bear for a new
  one).
- TheTVDB key: optional, skip unless TV franchise scanning is wanted later.

### 5.3 Health monitor

```python
"gaps2": (8704, "/"),
```

### 5.4 Fish functions

- `stack-gaps2-scan` — `POST /api/gaps2/scan`, triggers a scan.
- `stack-gaps2-missing` — `GET /api/gaps2/missing`, list of movies GAPS-2
  currently considers missing.
- `stack-gaps2-push <tmdb_id>` — `POST /api/gaps2/push` with `{tmdb_id}`,
  pushes one missing title into Radarr. Deliberately per-title, not a bulk
  "push all" function — bulk-adding without review is the kind of one-shot
  destructive-ish action this repo's CLAUDE.md asks to confirm before doing,
  and a missing-movie list can contain false positives (wrong-year matches,
  short films, etc).

### 5.5 Control panel

- `control-panel/services/gaps2/router.py` — routes for the three fish
  functions, proxying GAPS-2's own REST API.
- Fleet/tile/commands.json registration — same pattern as 1.6.
- STACK.md entry: the anime-scope decision from 5.2, the encryption-key
  backup note from 5.1, scan schedule chosen (tie to library size — check
  current movie count via Radarr's API at implementation time and pick
  something reasonable, e.g. weekly for a large library rather than
  upstream's more aggressive default).

### 5.6 Tests

- pytest for the router (mock GAPS-2's API).
- Live verification: run a real scan against the live library, confirm at
  least one known-missing title surfaces correctly, and do one controlled
  single-title push into Radarr, then verify it landed in Radarr's queue/
  wanted list correctly (respecting existing quality profile / root folder
  routing — do not verify against radarr-anime unless 5.2's scope decision
  included it).
- health-monitor green.

### 5.7 Acceptance

- [x] Container healthy
- [x] `/app/data` confirmed covered by existing backup mechanism —
      `stack-claude-full-backup`'s no-excludes tar of `~/Claude`, verified
      (restic, which this box originally assumed, was removed 2026-08-12)
- [x] Plex + TMDB + TheTVDB keys configured — headlessly, no OAuth. Radarr
      and Sonarr were deliberately NOT configured inside GAPS-2 while anime
      was in scope; they are configured now that it is not (see below)
- [x] Anime-scope decision made and documented — one container, control panel
      owns push routing. Anime coverage reversed later the same day (below)
- [x] health-monitor probe green
- [x] pytest suite passing — 33 cases, full suite 710
- [x] Live scan + one controlled push verified — 1,534 gaps across 4
      libraries; "Aria the Avvenire" pushed to radarr-anime and confirmed
      absent from general radarr
- [x] Fish functions callable — all four
- [x] STACK.md entry added
- [x] Committed as its own commit

### 5.8 Anime libraries removed (2026-08-12, same day)

Bear's call, reversing the anime-scope decision above. GAPS-2 now covers
**Movies and Shows only**. Collection/franchise detection is a poor fit for
anime: TMDB collections and TheTVDB franchises model seasons, OVAs, specials
and recap films inconsistently, so most of the 321 anime gaps found in the
first sweep were metadata artefacts rather than titles worth grabbing.

What changed:

- `control-panel/services/gaps2/libraries.py` — the routing table is Movies →
  `radarr`, Shows → `sonarr`. Every gaps2 route derives its target from this
  table, so `/scan`, `/missing` and `/push` all reject the anime libraries as
  unknown.
- **GAPS-2's own Radarr/Sonarr are now configured**, reversing the box above.
  That was only ever blocked by the four-instance ambiguity; with one Radarr
  and one Sonarr in scope, `scripts/gaps2-provision.py` wires both with the
  same root folder and quality profile the panel's push uses, so GAPS-2's own
  Add button and `stack-gaps2-push` land a title in the same place.
- `scripts/gaps2-prune-history.py` (new) — deleted the leftover anime scan
  results out of GAPS-2's data dir. Removing the libraries from the table
  stops the panel touching them, but GAPS-2 kept the stored gaps, and those
  rows now carry a working Add button pointed at the general instances. 5
  history entries dropped, `last_tv_scan.json` (an Anime Shows scan) deleted.

Live after the change: 1,148 gaps across 2 libraries (Movies 929, Shows 219).

---

## Phase 6 — WatchState

**Status:** DONE (2026-08-12). Built, live-verified on both the import and the
webhook path, and committed. Three further corrections beyond 6.0's recon:

- **`uuid` and `user` are required on `POST /v1/api/backends`,** not optional.
  WatchState sends the backend uuid as Plex's `X-Plex-Client-Identifier`, so
  omitting it fails several layers down with "X-Plex-Client-Identifier is
  missing"; omitting `user` (the numeric Plex account id, fetched with that
  same uuid) fails with the literal unsubstituted placeholder `'{id}'`.
- **6.4's webhook URL is wrong for this stack.** plex runs `network_mode:
  host`, so it cannot resolve `watchstate`. The registered URL is
  `http://HOST_IP:8705/v1/api/webhook?apikey=<the backend's own token>` - and
  the token is not optional decoration, it is what identifies which backend
  posted.
- **Registering the webhook is scriptable**, as 6.0 suspected: `POST
  /v1/api/backend/plex/webhook` drives WatchState's own AddWebhook action
  against plex.tv, so there is no browser step anywhere in Phase 6.

Import cadence: `25 0-1,6-23 * * *` - hourly at :25, skipping 02:00-05:59,
which already holds the poster sync, Arr backup, Letterboxd sync, Sunday
docker prune and Plex's own Butler window.

### 6.0 Recon findings (2026-08-12) — read before implementing
**Risk:** medium — writes watch-state data continuously; needs both the
scheduled import task and Plex webhook configured correctly, or events get
silently dropped (per WatchState's own documented caveat).

### 6.0 Recon findings (2026-08-12) — read before implementing

Upstream source was read at `arabcoders/watchstate` (PHP, 1.5k stars, active).
No code was written; this section exists so a fresh session can skip straight
to building. **Four corrections to the subsections below, which were written
from assumption.**

1. **Everything is env-driven** (`config/config.php`): `WS_API_KEY`,
   `WS_SECURE_API_ENDPOINTS`, `WS_SYSTEM_SECRET`, `WS_AUTH_TOKEN_EXPIRY`,
   `WS_WEBHOOK_TOKEN_LENGTH`. This satisfies Phase 4's env-var-over-config-file
   rule directly — set the API key in `.env`, do not let it self-generate into
   the gitignored `config/`.

2. **6.2 is wrong that secrets must be entered via a setup CLI/UI.** The API
   exposes `POST /v1/api/backends` (`src/API/Backends/Add.php`), alongside
   `Discover.php`, `PlexToken.php`, `Users.php` and `AccessToken.php`. So the
   Plex backend seeds headlessly from the existing `PLEX_URL`/`PLEX_TOKEN` via
   a `scripts/watchstate-provision.py`, exactly as Phase 5 did. Note there is
   **no** `backends:add` console command (only `Backend/RestoreCommand.php` and
   `Backend/TestCommand.php`), so the API is the only scriptable path — a
   `docker exec` approach will not work.

3. **Real route paths**, resolved from the `URL` constants against
   `api.prefix` = `/v1/api`:
   - health: `/v1/api/system/healthcheck` (`src/API/System/HealthCheck.php`) —
     use this for 6.3, **not** `/`. A real backend endpoint, same reasoning as
     Phases 4 and 5.
   - webhook: `/v1/api/webhook` (`src/API/WebHook.php`, accepts GET/POST/PUT)
     — **not** 6.4's guessed `/v1/api/webhook/plex`. There is one endpoint for
     every backend type; the backend is identified by its own webhook token,
     not by the path.
   - backends: `GET`/`POST /v1/api/backends`.

4. **6.1's compose block would likely fail to start.** The container runs
   rootless and *exits* if it cannot write `/config`; upstream's README calls
   this out and its own example sets `user: "${UID:-1000}:${UID:-1000}"`. The
   block below has no `user:` line at all. Set it to match the owner of
   `./config/watchstate` (this stack's `PUID`/`PGID`).

Also confirmed rather than assumed: upstream's README independently states to
keep the scheduled import enabled even when every backend supports webhooks,
which is exactly 6.4's caveat. The redundancy is deliberate on both sides.

`src/Backends/Plex/Action/AddWebhook.php` exists, so WatchState may be able to
register the webhook into Plex itself rather than needing it configured from
the Plex side — worth checking first when implementing 6.4, since it would
make that step scriptable too.

### 6.1 Compose

```yaml
  watchstate:
    restart: unless-stopped
    image: ghcr.io/arabcoders/watchstate:latest
    container_name: watchstate
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8080/ || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    volumes:
      - ./config/watchstate:/config
    ports:
      - "8705:8080"
    mem_limit: 512m
    mem_reservation: 64m
    cpus: 1
```

### 6.2 Secrets

Plex token entered via WatchState's own setup CLI/UI (its `console`
sub-commands, run via `docker exec`, or its web onboarding — confirm which
path this image exposes at implementation time). No pre-seeding via
secret-injector.

### 6.3 Health monitor

```python
# Corrected by 6.0's recon - "/" would be served by the WebUI and can answer
# with a dead backend behind it, the same failure mode Phases 4 and 5 both hit.
"watchstate": (8705, "/v1/api/system/healthcheck"),
```

### 6.4 Import task + webhook

1. Enable WatchState's own scheduled import task (its internal cron,
   confirm default interval and tune it to match Plex's existing library
   refresh cadence already configured elsewhere in this stack — check
   `stack-plex-refresh-libraries`'s schedule for the cadence to mirror).
   Do not schedule it to overlap a Plex library refresh, backfill, or
   trash-empty window — this stack has confirmed real SQLite write
   contention (`busy database` errors) when Plex's DB takes concurrent write
   pressure from multiple directions at once (see
   `plex-marked-deleted-db-contention` and `scoped-plex-library-refresh`);
   pick a clear offset, don't assume WatchState's reads are cheap enough to
   ignore this.
2. **Also** configure a Plex webhook pointing at WatchState
   (`http://watchstate:8080/v1/api/webhook` — confirmed against
   `src/API/WebHook.php` by 6.0's recon; there is no per-backend `/plex`
   suffix, the backend is identified by its webhook token)
   for near-real-time updates. Keep the scheduled import running regardless
   — WatchState's own docs warn webhooks alone can drop events, do not
   disable the import task as an "optimization."

### 6.5 Fish functions

- `stack-watchstate-status` — `GET /api/watchstate/status`, last import run
  time/result.
- `stack-watchstate-import-now` — `POST /api/watchstate/import`, triggers an
  out-of-schedule import.
- `stack-watchstate-history <item>` — `GET
  /api/watchstate/history?item=<title>`, watch-state history for a title.

### 6.6 Control panel

- `control-panel/services/watchstate/router.py` — routes for the three fish
  functions, proxying WatchState's own REST API.
- Fleet/tile/commands.json registration — same pattern as 1.6.
- STACK.md entry: import interval chosen, webhook path configured, the
  "keep import task on even with webhooks" caveat restated so a future pass
  doesn't accidentally "clean up" the redundancy.

### 6.7 Tests

- pytest for the router (mock WatchState's API).
- Live verification: mark one episode watched in Plex, confirm it appears in
  WatchState within one import cycle (via `stack-watchstate-history`), and
  separately confirm the webhook itself fires (check WatchState's logs for
  a webhook-triggered event, not just the scheduled import).
- health-monitor green.

### 6.8 Acceptance

- [x] Container healthy
- [x] Plex token configured — headlessly, via scripts/watchstate-provision.py
- [x] Scheduled import enabled and interval tuned — `25 0-1,6-23 * * *`
- [x] Plex webhook configured and confirmed firing — registered into plex.tv
      from the API; PlexMediaServer POSTs landing 200 in WatchState's access log
- [x] health-monitor probe green
- [x] pytest suite passing — 31 new cases, full suite 761
- [x] Live watch-state sync verified via both paths — 100,203 items imported,
      webhook delivery confirmed after a Plex scrobble
- [x] Fish functions callable — all three
- [x] STACK.md entry added
- [x] Committed as its own commit

---

## Phase 7 — PlexAniSync

**Status:** DONE (2026-08-13)
**Risk:** medium — the one service in this batch with an unautomatable
secret (AniList OAuth, yearly manual renewal) and no persistent web UI.

### 7.0 Corrections to this section, found while implementing (2026-08-13)

Five things below were written from guesses and turned out wrong. The build
follows the corrections, not 7.1–7.5 as originally written.

1. **Image is `ghcr.io/rickdb/plexanisync:latest`**, not `rickdb/...`.
   Upstream publishes to GHCR only.
2. **Config path is not `/app/config`.** There is no config directory. The
   Docker image is configured entirely by env vars (`PLEX_URL`, `PLEX_TOKEN`,
   `PLEX_SECTION`, `ANI_USERNAME`, `ANI_TOKEN`, …); only
   `custom_mappings.yaml` is a mounted file, at
   `/plexanisync/custom_mappings.yaml`. This satisfies Phase 4's
   env-var-over-config-file preference for free.
3. **`INTERVAL=0` is what makes it a one-shot.** The image's default (3600)
   turns it into its own sleep-loop scheduler, which would have collided with
   the systemd timer this section calls for. `<=0` means sync once and exit.
4. **`docker compose run --rm` was the wrong trigger.** It throws the logs
   away on exit, and logs are the *only* thing 7.4/7.5 have to parse. Both
   triggers instead re-*start* one persistent-but-stopped container: the timer
   via `docker start --attach`, the control panel via the Docker SDK.
5. **Kometa was the wrong template.** Kometa runs its own internal scheduler
   (`KOMETA_TIMES`) and has no systemd unit at all — 7.1's "copy Kometa's
   structure" is not a thing that exists. The real precedent is
   `systemd/stack-letterboxd-sync.{service,timer}`, and every stack timer on
   this host is a **user** unit symlinked from `systemd/` into
   `~/.config/systemd/user/`, needing no sudo.

### 7.1 Compose

Not a long-running web service — runs as a scheduled job via a systemd timer
(mirroring the existing pattern for `kometa` — check
`.claude/skills/kometa-run-and-monitor` or the systemd unit backing Kometa's
own scheduled runs, and copy that structure exactly rather than inventing a
new scheduling mechanism):

```yaml
  plexanisync:
    image: rickdb/plexanisync:latest
    container_name: plexanisync
    networks: [stacknet]
    volumes:
      - ./config/plexanisync:/app/config
    profiles: ["scheduled"]   # not started by `docker compose up`; invoked by the timer
```

New systemd files (mirror whatever unit pattern backs Kometa's scheduled
run — check `systemd/` in this repo for the existing example to copy):
`systemd/plexanisync.service` (runs `docker compose run --rm plexanisync`),
`systemd/plexanisync.timer` (interval matched to WatchState's import
interval from 6.4, so anime and general watch-state sync don't race each
other — pick an offset, not the same exact minute, to avoid both hitting
Plex's API simultaneously). Same contention risk as 6.4's note applies here
too: don't let this offset land inside a Plex library refresh or trash-empty
window either — check `stack-plex-refresh-libraries`'s schedule and any
backup/maintenance windows before picking the final offset.

### 7.2 Secrets

- Plex token: reuse the same token pattern as WatchState (6.2) — do not
  create a second, separately-obtained token if one is already sitting in
  `.env` from Phase 6; check first.
- AniList OAuth token: **cannot be automated.** Interactive OAuth flow,
  1-year expiry. Store as `PLEXANISYNC_ANILIST_TOKEN` in `.env` (not
  committed), obtained by Bear visiting AniList's auth endpoint per
  PlexAniSync's own docs. Add a clearly-flagged comment in `.env.example`
  and a STACK.md entry under a section future sessions will actually read
  (a dated "known landmine" entry, matching this file's existing style for
  things like the AltMount/nzbdav lineage correction) noting the renewal
  date so a future session doesn't waste time re-diagnosing "why did anime
  sync silently stop" a year from now.

### 7.3 Health monitor

Not applicable in the usual HTTP sense (no persistent service). Instead, add
a **run-freshness check**: confirm the systemd timer's last run succeeded
within the expected interval. If `health-monitor`'s existing pattern already
has a mechanism for checking systemd timer freshness (check how it currently
handles Kometa, if at all), reuse that; otherwise this is the one new check
type this batch introduces — keep it minimal (parse `systemctl status
plexanisync.timer` / `journalctl -u plexanisync.service` for last-run
success/failure).

### 7.4 Fish functions

- `stack-plexanisync-run-now` — triggers `systemctl start
  plexanisync.service` (or the docker-compose-manager equivalent — confirm
  which mechanism this repo's other scheduled jobs use for a manual trigger
  and match it).
- `stack-plexanisync-last-run` — reports last run time/result/synced-title-
  count, parsed from the container's own log output (no REST API to query,
  since PlexAniSync is not a persistent service).

### 7.5 Control panel

- `control-panel/services/plexanisync/router.py` — routes for the two fish
  functions above. Since there's no long-running API to proxy, this router
  shells out to `systemctl`/`docker compose run` and parses logs — follow
  whatever existing pattern this repo uses for other systemd-timer-backed
  jobs (check if Kometa's control-panel router already does this, and copy
  its approach rather than inventing a new one).
- Fleet/tile/commands.json registration — same pattern as 1.6, noting in the
  tile that this is a scheduled job, not a persistent service (so its status
  display should show "last run" rather than a simple up/down health dot).
- STACK.md entry: AniList token renewal reminder (see 7.2), scheduling
  offset from WatchState, anime library scope (confirm it targets the
  correct Plex anime library given this stack's existing radarr-anime/
  sonarr-anime split).

### 7.6 Tests

- pytest for the router (mock the systemctl/log-parsing calls).
- Live verification: manually trigger `stack-plexanisync-run-now` against a
  known-watched anime title, confirm the title's watch state appears on the
  configured AniList account, and confirm the systemd timer is enabled
  (`systemctl is-enabled plexanisync.timer`).

### 7.7 Acceptance

- [x] systemd service + timer installed and enabled (user units, symlinked
      from `systemd/`, no sudo)
- [x] Plex token configured (reused from Phase 6 - `PLEX_URL`/`PLEX_TOKEN`)
- [x] AniList OAuth token configured; issued 2026-08-13, **expires
      2027-08-13**, documented in STACK.md's landmine section
- [x] Timer offset confirmed not to race WatchState's import (00/06/12/18:45
      vs WatchState's :25, and outside 02:00-05:59 entirely)
- [x] pytest suite passing (797 -> 824; 17 router cases + 9 timer-freshness)
- [x] Live sync verified against real watched titles, confirmed on AniList's
      own API: Cowboy Bebop, The Animatrix, Dragon Ball Z
- [x] Fish functions callable (`run-now`, `last-run`, `logs`)
- [x] STACK.md entry added, including the yearly-renewal landmine note
- [x] Committed as its own commit

---

## Phase 8 — deferred: whole-stack fish-function / endpoint naming cleanup

**Status:** DONE (2026-08-13). 8a integrity + 8b rename both shipped. 12
commands renamed, schema enforced by `tests/test_fish_naming.py`. Design and
decisions: `docs/superpowers/specs/2026-08-13-cli-naming-cleanup-design.md`,
which supersedes 8.2-8.4 below. Implementation record, including the two
landmines (the linter's deliberate 7-of-12 coverage, and the files
`fish-rename.py` must never rewrite): STACK.md's "CLI naming cleanup" entry.

**Note on 8.3 below:** it names commands by their pre-rename names on purpose.
It is the audit that motivated the rename, so it is excluded from
`fish-rename.py`'s reference sweep. Do not "fix" those names.
**Risk:** high blast radius, not high technical risk — this is a scope/
coordination risk, not a correctness risk.

### 8.1 Why deferred

Phases 1–7 add ~15-20 new fish functions and control-panel routes using
today's existing naming convention. Renaming everything (today's ~150
functions across ~20 services, plus whatever this batch adds) in the same
pass as building new services would mean designing a naming schema against a
moving target. This phase starts only once the new services' own names are
settled and stable.

### 8.2 Locked decisions (from design conversation, 2026-08-08)

- **Scope: whole stack.** Every existing service's fish functions and
  control-panel endpoints, not just the 7 new ones from Phases 1–7.
- **Keep the `stack-<service>-<action>` prefix structure.** The rename is
  about consistency of verb order, phrasing, and eliminating duplicates —
  not a structural redesign of the naming scheme itself.
- **Hard cutover, no deprecated aliases.** Every caller (fish functions
  themselves, `control-panel/static/commands.json`, every `stack-cli-*`
  skill doc, this repo's own docs) gets updated in the same commit set as
  the rename. No transition period, no dead aliases left behind.
- **Own spec.** This phase needs its own brainstorm → design doc → plan
  cycle before implementation — this section is a pointer to that future
  work, not the spec itself.

### 8.3 Known inconsistencies to start the audit from

(Captured 2026-08-08 via `grep -h "^function stack-" fish-functions/*.fish` —
re-verify this list is still current before starting Phase 8, since Phases
1-7 add more functions and any other work between now and then may add
more still.)

- Verb-order drift: `stack-plex-empty-trash` (verb-noun) vs
  `stack-plex-recently-added` (adjective-noun) vs `stack-arr-search-toggle`
  (noun-verb) vs `stack-arr-blocklist-clear` (noun-noun-verb).
- Duplicate/ambiguous pair: top-level `stack-recently-added` vs
  `stack-plex-recently-added` — same concept, unclear which is canonical or
  whether the top-level one is dead code. Resolve during the audit, not
  before.
- Inconsistent modifier placement: `stack-radarr-list-import` vs
  `stack-sonarr-custom-list-import` for conceptually similar actions.
- Source-first naming for a family of functions (`stack-letterboxd-radarr-*`,
  `stack-mdblist-radarr-*`, `stack-tmdb-*-import`, `stack-trakt-list-import`)
  that puts the data source before the target app rather than the usual
  `stack-<service>-<action>` order — determine during the audit whether this
  is a deliberate, worth-keeping exception (source-oriented commands read
  naturally as "stack-letterboxd-radarr-watchlist" = "import my Letterboxd
  watchlist into Radarr") or an inconsistency worth normalizing.

### 8.4 What Phase 8's eventual spec must cover

- A full audit output (every current function name, proposed new name,
  reasoning) — not just the illustrative examples in 8.3.
- Every file that references a function name by string: `commands.json`,
  every `stack-cli-*` skill's `SKILL.md`, any cross-reference in `STACK.md`
  or `README.md`.
- A migration checklist proving no reference was missed (e.g. grep for the
  old name across the whole repo post-rename, expect zero hits outside git
  history).
- Whether control-panel REST endpoint paths (`/api/<service>/*`) get renamed
  too, or only the fish function layer — these are currently 1:1 but don't
  have to stay that way; this needs an explicit decision in that spec, not
  an assumption carried over from this doc.

---

## Reference

- Design conversation and approved Artifact:
  `https://claude.ai/code/artifact/6b115a3f-1972-44ff-968a-1d49a70fb281`
- Existing wiring pattern this doc mirrors throughout: tautulli/maintainerr,
  see `docker-compose.yml:786-852`, `control-panel/services/tautulli/router.py`,
  `.claude/skills/health-monitor/monitor.py:32,34`,
  `control-panel/static/js/fleet.js:15,19`,
  `control-panel/static/js/reference.js:18,20`.
- This doc is referenced from Claude's cross-session memory — see
  `MEMORY.md` in the memory store for the pointer entry.

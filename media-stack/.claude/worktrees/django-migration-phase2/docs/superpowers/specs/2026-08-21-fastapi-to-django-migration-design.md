# Control-Panel: FastAPI → Django Migration Design

**Date:** 2026-08-21
**Status:** Approved, ready for implementation planning

## Summary

Replace the control-panel backend (FastAPI, `control-panel/`) with Django,
rebuild the browser UI as server-rendered Django templates + htmx (replacing
the static HTML/JS SPA), and migrate the 280-file fish CLI onto a redesigned,
versioned JSON API. Existing SQLite data (`/data/control-panel.db`) is
preserved. Big-bang cutover — no side-by-side running period.

## Current State (as of this audit)

- **Backend:** FastAPI (`main.py` + 18 service routers under `services/*/router.py`),
  114 endpoints total, entirely synchronous (`def`, sync `httpx` calls — no
  `async def` anywhere except one middleware). SQLAlchemy 2.0 ORM + Alembic
  migrations, SQLite at `/data/control-panel.db`. 10 models: `User`, `Setting`,
  `ApiKey`, `AuditLog`, `LetterboxdTmdbCache`, `LetterboxdTrackedList`,
  `LetterboxdSyncLog`, `MDBListTrackedList`, `MDBListSyncLog`. Session auth via
  itsdangerous-signed `cp_session` cookie + argon2 password hashing; service
  auth via `X-Api-Key` header checked against `ApiKey.key_hash`.
- **Frontend:** Static `index.html` + `app.js` + `static/js/*.js` (~2900 lines:
  fleet.js, auth.js, sparkline.js, palette.js, overview.js, etc.) — a
  client-side-rendered SPA that fetches the JSON API and renders DOM by hand.
  3 `.test.js` files exist; no test runner config found in the repo root.
- **Tests:** Zero Python tests exist today.
- **CLI:** 280 fish files under `fish-functions/`, a large fraction of which
  call the control-panel JSON API directly (per `stack-cli-arr-fleet`,
  `stack-cli-discovery-import`, `stack-cli-plex-kometa`,
  `stack-cli-usenet-queue`, and related skills).
- **Deployment:** Docker, `uvicorn main:app` on port 8420, `pid: host` +
  `SYS_ADMIN`/`SYS_PTRACE` capabilities for Plex Health's D-state
  introspection and host-lazy-umount, bind mounts for `/data`, `/logs`,
  `/host-proc`, `/host-sys-fuse`.

## Goals

1. Swap FastAPI for Django + Django REST Framework as the backend framework.
2. Rebuild the browser UI as server-rendered Django templates + htmx,
   dense-dashboard-card visual style (confirmed via visual companion mockup:
   4-across monospace stat cards, status dot per service, thin log strip —
   denser than a typical admin dashboard, card structure kept from the
   "Dashboard/Cards" direction).
3. Redesign the JSON API as a clean, versioned contract (`/api/v2/*`) that the
   fish CLI migrates onto — not a verbatim port of the FastAPI-era paths.
4. Preserve all existing data in `/data/control-panel.db` — zero data loss.
5. Ship a full pytest-django + DRF `APIClient` test suite, 80%+ coverage
   (CLAUDE.md's floor), covering models, serializers, API views, and template
   views (including htmx partial responses).
6. Update every doc that references the current backend: `STACK.md`,
   `README.md`, `PLANS.md`, mark `.claude/plans/evolved-control-panel-backend.plan.md`
   superseded.

## Non-Goals

- No side-by-side/incremental cutover — single branch, cut over once green.
- No attempt to preserve existing itsdangerous-signed sessions — forced
  re-login on deploy is accepted.
- No change to `docker-compose.yml`'s privilege model (`pid: host`, `cap_add`,
  `security_opt`, volume mounts) beyond the container's `CMD`.

## Architecture

### Django project layout

One Django app per current service directory (18 apps: `arr`, `radarr`,
`sonarr`, `prowlarr`, `cleanuparr`, `nzbdav`, `plex`, `posters`, `catalog`,
`queue`, `auth`, `ratings`, `seerr`, `letterboxd`, `mdblist`, `watchstate`,
`host`, `host_actions`). Each app owns:

- `models.py` (where the app owns data — most don't; models concentrate in a
  shared `core` app matching the current 10-model set)
- `services.py` — the ported business logic (arr_client, plex_client,
  nzbdav_client, docker_client, host_helper_client calls), framework-agnostic
  so both the API views and the template views call the same functions
- `api/` — DRF serializers + `APIView`/`ViewSet` classes, mounted under
  `/api/v2/<app>/...`
- `views.py` — Django template views + htmx partial-fragment views, mounted
  under `/<app>/...` for the browser UI
- `urls.py` — two routers per app (`api_urls.py`, `urls.py`)

A shared `core` app holds the 10 ORM models, the ported httpx client wrappers,
and shared response/error helpers. Root `urls.py` includes each app's
`api_urls` under `/api/v2/` and `urls` under `/`.

### Data layer

Django models get field-for-field parity with the existing SQLAlchemy models,
using `Meta.db_table` to match today's table names exactly. `makemigrations`
generates the initial migration; `migrate --fake-initial` applies it against
the existing `/data/control-panel.db` without touching data (schema already
matches — no `ALTER` needed). Alembic retires; Django's migration system owns
schema changes going forward.

### Auth

- **Browser sessions:** Django's native session framework (DB- or
  cache-backed) replaces the itsdangerous cookie scheme. Existing sessions do
  not carry over — users log in again once after deploy.
- **Service auth:** `X-Api-Key` header checked against `ApiKey.key_hash`
  (argon2), via a custom DRF `authentication_classes` entry. A combined
  `IsAuthenticatedOrServiceKey` permission class mirrors today's
  `current_user_or_service` FastAPI dependency, used across both the `/api/v2/`
  DRF views and any protected template views.

### JSON API (`/api/v2/*`) — for the fish CLI

Redesigned, not ported verbatim: endpoint shapes/naming follow the new
per-app `services.py` structure rather than preserving FastAPI-era paths.
Response envelope (`{"ok": bool, "message": str, "time": "HH:MM:SS", ...}`)
is preserved so the shape stays predictable, but exact paths change per app.
This is the CLI's contract — `fish-functions/*.fish` get updated to call the
new paths (function names/signatures the user types stay stable; only the
HTTP calls inside them change).

### Browser UI

Django templates + htmx, one template per current SPA "page" (Overview, Arr
Fleet, Host, Plex, Letterboxd, MDBList, Settings, etc.). Visual style
confirmed via mockup: dense card grid (4 cards/row), monospace stat lines per
card (queue/missing/cutoff/last-run counts), status dot, thin nav bar, log
strip below the grid. Navigation between pages is full page load; within a
page, live data (queue tables, health status) and actions (search, unstick,
blocklist, sync-now) are htmx partial swaps — no full reload for those.

All current client-side JS (`fleet.js`, `auth.js`, `sparkline.js`,
`palette.js`, `overview.js`, etc. — ~2900 lines) is retired and rewritten
from scratch as part of the template system; nothing is ported as-is.

### Testing

pytest-django + DRF `APIClient`. Per app: model tests, serializer tests,
`/api/v2/` endpoint tests (happy path, auth-rejected, error branches), and
template-view tests (rendered HTML assertions + htmx partial-response
assertions). 80%+ coverage gate via `pytest --cov`, matching CLAUDE.md.

### Deployment

`gunicorn config.wsgi:application` replaces `uvicorn main:app` (sync WSGI
workers match the fully-sync codebase). Same port 8420, same Dockerfile COPY
pattern, same docker-compose block — only `CMD` and `requirements.txt`
change. `pid: host`, `cap_add`, `security_opt`, and all volume mounts are
untouched (Plex Health / host-lazy-umount features depend on them regardless
of framework).

### CLI migration

`fish-functions/*.fish` files that call the control-panel API get their HTTP
calls repointed at `/api/v2/*`. Scope: every function referenced by
`stack-cli-arr-fleet`, `stack-cli-discovery-import`, `stack-cli-plex-kometa`,
`stack-cli-system-maintenance`, `stack-cli-usenet-queue`, and
`stack-cli-infra-ops` skills — this needs an inventory pass during
implementation planning to enumerate the exact file list, since 280 fish
files exist total and not all touch the control-panel.

### Docs

- `STACK.md`, `README.md`, `PLANS.md` control-panel sections rewritten
- `.claude/plans/evolved-control-panel-backend.plan.md` marked superseded
  (its FastAPI-era decisions no longer apply)
- This spec is the design of record for the migration

## Open Risks / Follow-ups for the Implementation Plan

- **Scale:** 114 endpoints to redesign + 18 template pages to build from
  scratch + up to ~280 fish files to audit and possibly update. This is not a
  single implementation plan — the writing-plans phase should decompose this
  into sequential phases (e.g. Phase 1: Django project skeleton + data layer +
  auth; Phase 2: `/api/v2/` per app; Phase 3: template UI per app; Phase 4:
  CLI migration; Phase 5: docs + cutover).
- **htmx partial contract:** needs its own convention (which endpoints return
  full pages vs `hx-target` fragments) defined early so all 18 apps follow it
  consistently — worth nailing down in Phase 1 before fanning out to the rest.
- **Zero prior test coverage** means writing tests is net-new work across the
  whole surface, not a port — budget accordingly.

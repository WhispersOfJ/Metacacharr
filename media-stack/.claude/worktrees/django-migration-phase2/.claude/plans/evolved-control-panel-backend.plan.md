# Implementation Plan: Evolved Control-Panel Backend

**Recovered:** 2026-08-04, from pre-compaction session transcript (originally produced via `/ecc:plan`, approved with "yes, proceed", then execution deferred with "start it next session").

## Requirements Restatement

Replace the current `control-panel` (single 5,872-line `app.py`, 139 endpoints, no auth, flat-file settings, monolithic) with an evolved backend that is:
- **Architecturally modular** — services-first, not one file
- **Database-backed** — real schema/migrations, not JSON blobs in `/data`
- **Authenticated** — real login, no longer LAN-trust-only
- **Extensible** — new integrations register in, don't get hand-inserted into a growing file

Replaces the current app in place; old `app.py` retired once parity is reached.

## Pattern Grounding (from the current codebase)

| Category | Source | Pattern to keep |
|---|---|---|
| Integration style | `app.py` (139 `@app.*` routes, ~35 comment-delimited sections) | Each external service (Radarr, Plex, NzbDAV, Bazarr, Tautulli...) already has a de facto boundary — just not an enforced one. This maps directly onto the top-level `CLAUDE.md`'s own "Architecture — services-first" rule already adopted for this repo. |
| Docker access | `docker_client = docker.from_env()`, used for restart/exec/inspect across every integration | Keep a single shared docker-client module other services import, don't duplicate |
| Security | `verify_same_origin` middleware, the `LOOPBACK_IPS`/bridge-gateway check fixed under `/cso` | This logic needs to evolve *into* real auth, not sit alongside it — same threat model, stronger mechanism |
| Settings | `settings_store.py` — atomic JSON write, `DEFAULTS` dict | Replace with real DB-backed settings table; keep the "safe atomic write" discipline as a migration-safety principle, not the JSON-file mechanism itself |
| Tests | `tests/` (pytest, `conftest.py`, mocks docker.sock/httpx) | Same test doubles, same mocking discipline — carries over directly to the new structure |

No existing pattern in this codebase for: auth, a database layer, or a plugin/module loader — stating this explicitly rather than inventing a fake precedent.

## Architecture

```
control-panel/
├── main.py                 # app factory, mounts routers, startup/shutdown
├── core/
│   ├── db.py                # SQLite engine/session (SQLAlchemy)
│   ├── docker_client.py      # shared docker.from_env(), moved out of app.py
│   ├── security.py           # session auth, password hashing, current-user dependency
│   └── settings.py           # DB-backed settings (replaces settings_store.py)
├── models/                  # SQLAlchemy models: User, Settings, ApiKey, AuditLog
├── migrations/               # Alembic
├── services/                 # one directory per integration, self-registering
│   ├── radarr/  {router.py, client.py}
│   ├── sonarr/  {router.py, client.py}
│   ├── plex/    {router.py, client.py}
│   ├── nzbdav/  {router.py, client.py}
│   ├── bazarr/  ...
│   ├── tautulli/ ...
│   ├── host/     {router.py}   # fleet, restart, mount checks
│   └── auth/     {router.py}   # login/logout/session
├── static/                    # same frontend, updated to call new auth-aware endpoints
└── tests/
```

**Plugin/extensibility mechanism:** each `services/<name>/router.py` exports a FastAPI `APIRouter` plus a `SERVICE_META` dict (label, health-check fn). `main.py` auto-discovers every `services/*/router.py` at startup (`importlib`, no manual registration list) and mounts it — adding a new integration means adding a new directory, not editing a central file. This directly satisfies the "extensibility" axis.

**Auth mechanism:** single-admin login to start (matches current single-operator reality), session cookie signed server-side, `current_user` FastAPI dependency gates every mutating route. `User` model designed for more than one row from day one (so "multi-user" later is a data problem, not an architecture change), but only one admin account provisioned initially — no invented multi-tenant complexity that isn't asked for yet.

**Database:** SQLite via SQLAlchemy + Alembic migrations. Not Postgres — this stays a single-host appliance, adding a Postgres container is unjustified complexity for one operator's dashboard. Alembic gives real migrations without the operational cost of a second database service.

## Files to Change

| File/Dir | Action | Why |
|---|---|---|
| `control-panel/main.py` | CREATE | New app entrypoint, router auto-discovery |
| `control-panel/core/*.py` | CREATE | Shared db/docker/security/settings modules |
| `control-panel/models/*.py` | CREATE | SQLAlchemy models |
| `control-panel/migrations/` | CREATE | Alembic setup + initial migration |
| `control-panel/services/<name>/*.py` | CREATE (×~15) | One per integration, ported from `app.py` sections |
| `control-panel/app.py` | DELETE (final phase only) | Retired once every route has a service-module equivalent and parity is verified |
| `control-panel/settings_store.py` | DELETE (final phase) | Superseded by `core/settings.py` + DB |
| `control-panel/static/js/*.js` | UPDATE | Add login flow, handle 401s, no other behavior change |
| `docker-compose.yml` | UPDATE | New entrypoint command (`uvicorn main:app`), same volumes/caps/ports — security posture from the `/cso` fix must be preserved or re-verified under the new auth model |
| `requirements.txt` | UPDATE | Add `sqlalchemy`, `alembic`, `passlib`/`argon2-cffi`, `itsdangerous` (or equivalent session lib) |
| `tests/` | UPDATE | Mirror new service structure, same mocking approach |

## Tasks (phased — each phase ships working, not half-built)

### Phase 1 — Scaffolding + auth (foundation everything else depends on)
- **Action:** stand up `main.py`, `core/db.py`, `core/security.py`, `User`/`Settings` models, Alembic init, login/logout routes, session-cookie middleware.
- **Mirror:** `verify_same_origin`'s threat model (docker.sock access = high blast radius) — auth must be at least as strong as that check, ideally strictly stronger.
- **Validate:** `pytest tests/test_auth.py` — login succeeds/fails correctly, protected route 401s without a session, 200s with one.

### Phase 2 — Port host/fleet + settings (highest-traffic, most-used routes)
- **Action:** move `docker_client`, fleet listing, container restart, `/api/settings` into `core/` + `services/host/`. This is what the recurring health-check loop and `stack-*` fish commands hit constantly — get it right first, under real use, before touching lower-traffic integrations.
- **Mirror:** existing fleet/restart logic in `app.py` lines ~316-500ish, ported not rewritten-from-scratch.
- **Validate:** existing `stack-status`/`stack-cli-infra-ops` fish commands against the new backend; full `docker compose ps` sanity sweep.

### Phase 3 — Port the *Arr integrations (Radarr/Sonarr/Prowlarr/Bazarr)
- **Action:** these are the routes the recurring health-check cron and `arr-importblocked-triage`/`docker-dns-networking-gotchas` operational knowledge depend on. Port queue/health/blocklist/manual-import endpoints service-by-service, verify each against the live stack before moving to the next.
- **Validate:** run the actual "Full stack health check" prompt against the new backend before calling this phase done — it's the closest thing to a real integration test this app has.

### Phase 4 — Port remaining integrations (Plex, NzbDAV, Tautulli, Wrapperr, Maintainerr, Checkrr, Prefetcharr, Lingarr, Kometa, poster-sync, backups)
- **Action:** same pattern, service-by-service. Lower risk — lower traffic, less operationally load-bearing than Phase 2/3.
- **Validate:** one live exercise per service (e.g. trigger a Plex scan, check a Tautulli stat) plus `pytest`.

### Phase 5 — Cutover + retirement
- **Action:** point `docker-compose.yml`'s `control-panel` service at `main:app`, force-recreate, verify full stack health. Delete `app.py`/`settings_store.py` only after a full day of the new backend running the actual recurring health-check loop without incident.
- **Validate:** the same full-stack health check, plus a manual pass through every `stack-*` fish command.

## Validation (run at the end of every phase, not just Phase 5)

```bash
docker compose build control-panel
docker compose up -d --force-recreate control-panel
pytest control-panel/tests/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8420/healthz
# then the actual recurring health-check prompt, live, against the running container
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Downtime during migration breaks the live health-check loop | High if done as one big-bang cutover | Phased plan above exists specifically to avoid this — each phase ships working, verified against real usage before the next starts |
| Auth breaks the docker.sock-adjacent security posture in a new way | Medium | Auth must be reviewed with the same rigor as the `/cso`-found Host-header bug — plan a dedicated security pass before Phase 5 cutover, not after |
| Losing an edge case from 139 hand-written endpoints during the port | Medium-High | Port section-by-section against the existing code, not a rewrite-from-memory; each phase's validation step is a live exercise, not just unit tests |
| SQLite write contention under the FUSE-mount-adjacent load this app already handles | Low | This app is low-write-volume (settings, session, audit log) — the heavy I/O (Plex/Arr APIs) stays HTTP calls to other containers, not DB writes |
| Frontend (`static/js/*.js`) silently breaks against new auth-gated endpoints | Medium | Phase 1 must include a minimal working login UI before any other route is ported, so every subsequent phase is tested through the real frontend, not just curl |

## Estimated Complexity: **HIGH**

This is a full rewrite of a 5,872-line, 139-endpoint, zero-auth application into a modular, database-backed, authenticated, plugin-extensible one — realistically multiple sessions of work, not a single sitting. Phase 1+2 alone (auth + the most-used routes) is a substantial session on its own.

## Acceptance
- [ ] Every one of the 139 current routes has a ported equivalent, verified live
- [ ] Login required for every mutating route; read-only health endpoints reviewed case-by-case (the recurring health-check loop needs a service account, not manual login, per cycle)
- [ ] `docker-compose.yml`'s security posture (docker.sock, `pid: host`, caps) re-reviewed under the new auth model, not just carried over blindly
- [ ] `app.py`/`settings_store.py` deleted only after Phase 5's live-day verification

## Note on current repo state vs. this plan

Since this plan was written, `settings_store.py` and `static/js/settings.js` (mentioned as DELETE/UPDATE targets above) were already committed as part of `8822d7b feat: add persisted settings and rack-console redesign to control-panel`. Re-check their current shape before Phase 1 — the plan's file list may need a small refresh, not a rewrite.

# Metacache

[![CI](https://github.com/WhispersOfJ/Metacacharr/actions/workflows/ci.yml/badge.svg)](https://github.com/WhispersOfJ/Metacacharr/actions/workflows/ci.yml)
[![Docker](https://github.com/WhispersOfJ/Metacacharr/actions/workflows/docker.yml/badge.svg)](https://github.com/WhispersOfJ/Metacacharr/actions/workflows/docker.yml)

An ARR-app companion that caches movie/TV metadata locally so Plex refreshes from a
fast local server instead of hammering TMDB/TVDB over the internet. Implements Plex's
**Custom Metadata Provider** API (PMS 1.43+), which natively lets you point Plex at any
HTTP metadata server.

See [DESIGN.md](DESIGN.md) for the full architecture, API contract, and roadmap.

## Status: M0–M3 shipped

- `GET /movie` and `GET /tv` serve the MediaProvider definitions Plex needs to register
  the providers ("Add Provider").
- **Movies end to end (M1):** `POST /library/metadata/matches` (search, external-GUID
  pinning, ranked manual "Fix Match" lists), `GET /library/metadata/{ratingKey}` (full
  metadata incl. cast/crew and content rating), and `GET /library/metadata/{ratingKey}/images`.
  All TMDB traffic flows through the local cache (single-flight, TTL, ETag revalidation,
  stale-if-error, 429 retry-with-backoff) and artwork URLs are rewritten to the local
  `/img/{hash}` endpoint.
- **TV end to end (M2):** shows, seasons, and episodes — match by title/year or by
  season/episode index / air date (structure-gated scoring), GUID pinning for all
  three kinds, full metadata with `parentTitle`/`grandparentTitle` + `parentIndex`,
  and the paged hierarchy endpoints `GET …/{ratingKey}/children` and
  `…/grandchildren` (`X-Plex-Container-Size` / `-Start`). Cast/crew (`Person[]`,
  `Role[]`, `Director[]`, `Writer[]`) and content ratings (`X-Plex-Country`-aware)
  ship for both movies and TV.
- **TVDB fallback (M2+):** when TMDB lacks an episode (or a whole season's episodes),
  the TVDB v4 provider (optional `Metacache__Tvdb__ApiKey`) supplies it — episode
  metadata falls back to TVDB via the show's `tvdb_id`, and episode matching augments
  from the full TVDB episode list. Login token stays in memory; data flows through the
  same gateway (24 h TTL, histogram `provider="api4.thetvdb.com"`).
- `GET /healthz` liveness check.
- Admin surface: `GET /cache/stats` (cache sizes) and `POST /cache/purge` (expired-row
  cleanup), returning `{ "removed": n }`.
- **Manual match pins (M4):** override a match permanently — `POST /admin/overrides`
  pins a tmdb rating key to a title/guid, consulted before any upstream search on
  every Plex refresh; auto matches that find zero candidates are captured under
  `GET /admin/unmatched` and can be pinned in one click
  (`POST /admin/unmatched/{key}/pin`), so repeated Fix Matches become one-time fixes.
- **Queryable cache index:** `GET /items` searches the warmed library by title
  (`q`), kind, guid (`?guid=imdb://tt0088763` resolves first) and freshness, and
  `GET /guid/lookup` translates any `imdb://`/`tmdb://`/`tvdb://` GUID to all its
  equivalents (cache-backed — repeats are pure cache hits). Every tool in the stack
  can query Metacache instead of TMDB.
- Image cache: artwork stored locally and served from `GET /img/{hash}` (content-
  addressed, per-file + total caps with oldest-first eviction, self-healing refetch).
- Rating-key, GUID, and match-scoring utilities (movies, shows, seasons, episodes) with
  tests.
- **Cache core** (DESIGN.md §7): SQLite store (`upstream_cache` / `items` / `urls`),
  keyed single-flight dedupe, ETag revalidation, TTL expiry, stale-if-error serving,
  and per-request header forwarding (used for TMDB Bearer auth) — fully unit-tested.
- **Cache warming (M3):** `POST /warm/movies` (Radarr), `/warm/shows` (Sonarr), and
  `/warm/all` turn the ARR libraries into the cache inventory — every movie/show/
  season/episode is fetched through the cached provider services and its artwork is
  pulled into the local image cache, with concurrency limits and a status endpoint.
  A nightly scheduled warm (`Metacache:Warm`) runs `/warm/all` automatically, and
  `POST /webhook/radarr` + `/webhook/sonarr` warm single items the moment Sonarr or
  Radarr reports a new import (point their webhook settings at these URLs).
- **Metrics dashboard (M3):** `GET /metrics` reports cache hit rate (live request
  counters), per-kind item counts, upstream-cache size, and disk usage (image files
  + SQLite DB); `GET /metrics/prometheus` renders the same data for scraping, and
  `monitoring/metacache-alerts.yml` ships Prometheus alerting rules (host down,
  low hit rate, disk usage, warm failures).

The ARR proxy face (M4) is next — see DESIGN.md §12.

## Requirements

- .NET 10 SDK (`dotnet`), or Docker.

## Run

```bash
dotnet run --project src/Metacache.Host
# → listening on http://127.0.0.1:8765
```

### Configuration

| Setting | Default | Notes |
|---|---|---|
| `Metacache__BindAddress` | `127.0.0.1` | Set to `0.0.0.0` to expose on the LAN (required for Plex on another machine) |
| `Metacache__Port` | `8765` | Provider URL port |
| `Metacache__DataPath` | `data/metacache.db` | SQLite cache file (created on first run) |
| `Metacache__Matching__*` | (see `appsettings.json`) | Match-policy weights/thresholds, e.g. `Metacache__Matching__AutoMatchThreshold=0.75` |
| `Metacache__Images__*` | `data/images`, 20 MB, 10 GB | Image cache dir, per-file cap (`MaxFileBytes`), total cap (`MaxTotalBytes`) |
| `Metacache__Tmdb__ApiKey` | *(none)* | **Required for M1.** Your TMDB API Read Access Token **or** legacy v3 API key. With `Auth=Bearer`/`Auto` the key never appears in URLs, cache keys, or logs. Get one at themoviedb.org → Settings → API |
| `Metacache__Tmdb__Auth` | `Auto` | `Auto` probes once and picks `Bearer` (API Read Access Token) or `Query` (legacy v3 key); force either with `Bearer`/`Query`. In `Query` mode the cache key is still computed from the secret-free URL |
| `Metacache__Tmdb__BaseUrl` / `ImageBaseUrl` | TMDB v3 / `t/p/original` | Upstream endpoints (override for proxies) |
| `Metacache__Tvdb__ApiKey` | *(none)* | **TVDB v4 API key** — powers the episode fallback/augmentation: when TMDB lacks an episode (or all episodes of a season), TVDB supplies it. The key is used only for a login POST; the token stays in memory and never touches the cache DB. Get one at thetvdb.com → Settings → API |
| `Metacache__Tvdb__BaseUrl` | `https://api4.thetvdb.com` | TVDB v4 endpoint (override for proxies) |
| `Metacache__Arr__RadarrUrl` / `RadarrApiKey` | *(none)* | Radarr instance + API key for `/warm/movies` (blank URL disables the source) |
| `Metacache__Arr__SonarrUrl` / `SonarrApiKey` | *(none)* | Sonarr instance + API key for `/warm/shows` (blank URL disables the source) |
| `Metacache__Arr__Concurrency` | `4` | How many items a warm run processes in parallel |
| `Metacache__Warm__Enabled` | `true` | Nightly scheduled warm on/off |
| `Metacache__Warm__ScheduleTime` | `03:00` | Wall-clock time for the nightly warm (`HH:mm`) |

Env vars override `appsettings.json`, e.g.:

```bash
Metacache__BindAddress=0.0.0.0 Metacache__Port=8765 dotnet run --project src/Metacache.Host
```

### Docker

```bash
docker build -t metacache .
docker run -d --name metacache --network host metacache
# binds 0.0.0.0:8765 (configurable via Metacache__Port)
```

### Monitoring stack (Docker Compose)

`monitoring/` ships a full stack: the host, Prometheus scraping `/metrics/prometheus`
with the alerting rules loaded, and a pre-wired Grafana (datasource + a 10-panel
Metacache dashboard auto-provisioned).

```bash
cp monitoring/.env.example monitoring/.env   # set METACACHE_TMDB_APIKEY (required)
docker compose -f monitoring/docker-compose.yml up -d --build
# → Metacache :8765 · Prometheus :9090 · Grafana :3000 (admin / GRAFANA_ADMIN_PASSWORD)
```

The dashboard overlays the same metrics as the built-in page (hit rate, latency
p50/p95 per provider, items by kind, warm status, disk usage, rate-limited
responses); alerts fire through the rules in `monitoring/metacache-alerts.yml`.

## CI/CD

`.github/workflows/` ships two pipelines:

- **CI** (`ci.yml`) — every push/PR: restore (cached), `dotnet format` as a C# style
gate, Release build with **warnings as errors**, xUnit run with coverage artifact, and
`dotnet list package --vulnerable` as a **NuGet CVE gate** (fails on any direct or
transitive package with a known vulnerability).
- **Docker** (`docker.yml`) — builds the image (BuildKit cache), pushes to
`ghcr.io/whispersofj/metacacharr` on `main` and `v*` tags, and gates every run on
**Trivy CVE scans**: the image (HIGH/CRITICAL, fixable only) and IaC config
(Dockerfile/compose misconfigs, e.g. non-root USER). SARIF findings upload to GitHub
code scanning. A **nightly schedule** rebuilds against the latest patched base images
and re-scans, so base-image CVEs surface without waiting for a code change. Trivy runs
as the official `aquasec/trivy` image — the `aquasec/trivy-action` GitHub Action was
supply-chain compromised in 2026 (CVE-2026-26189 + tag force-push), so it is not used.

The image runs as a **non-root user** (`APP_UID`, container-escape hardening). If you
upgraded an existing deployment, its named volume was created by the old root-running
container — fix ownership once before rebuilding:

```bash
docker run --rm -v metacache-data:/data alpine chown -R 1654:1654 /data
# (verify the volume name with: docker volume ls | grep metacache)
```

## Provider endpoints

| Endpoint | Purpose |
|---|---|
| `POST /library/metadata/matches` | Match — body: `{ "type": 1–4, "title": …, "year": …, "guid": …, "parentTitle": …, "grandparentTitle": …, "index": …, "parentIndex": …, "date": …, "filename": …, "manual": 0/1, "includeAdult": 0/1, "includeChildren": 0/1 }` (`type`: 1=movie, 2=show, 3=season, 4=episode). Auto returns the single best match (or empty → Plex shows Fix Match); `manual: 1` returns a ranked list |
| `GET /library/metadata/{ratingKey}` | Full metadata for a movie (`tmdb-movie-105`), show (`tmdb-show-15260`), season (`tmdb-season-15260-1`), or episode (`tmdb-episode-15260-1-1`) — `Guid[]`, `Genre[]`, `Image[]`, `Rating[]`, `Country[]`, `Studio[]`, cast/crew, content rating; artwork points at `/img/{hash}` |
| `GET /library/metadata/{ratingKey}/children` | Seasons of a show / episodes of a season, paged |
| `GET /library/metadata/{ratingKey}/grandchildren` | All episodes of a show, paged |
| `GET /library/metadata/{ratingKey}/images` | All image assets for the item |
| `GET /library/search` / `GET /library/recentlyAdded` | **Library browse, entirely from cache:** search the warmed index by `title`/`kind`/`year` or list the most recently added — Plex-shaped containers with `?width=185` thumbs (paged via `X-Plex-Container-Size`/`Start`) |
| `POST /warm/movies` / `/warm/shows` / `/warm/all` | Pre-populate the cache from Radarr/Sonarr; returns the run summary (or 409 while another warm is running) |
| `POST /webhook/radarr` / `/webhook/sonarr` | Event-driven warm: warm the one movie/show named by the ARR webhook payload (`eventType: Test` → `{ "result": "ok" }`) |
| `POST /webhook/plex` | **Predictive warm:** on playback start, resolves the played item and pre-fetches it, the next episodes (incl. next-season priming on a finale), and up to 3 similar titles — so the next autoplay is a cache hit (other events → `{ "result": "ignored" }`) |
| `GET /warm/status` | Live warmer state: `{ isRunning, lastResult }` |
| `GET /metrics` | Cache hit rate, per-kind item counts, upstream size, disk usage (JSON) |
| `GET /metrics/prometheus` | Same metrics in Prometheus text exposition format (`_total` counters, `kind`/`provider` labels, request-duration histogram, TMDB rate-limit gauges + 429 counter) for scraping |
| `GET /dashboard` | Minimal live dashboard: polls `/metrics` and renders hit rate, per-kind bars, and disk usage with a hit-rate sparkline overlaying live polling vs the last 120 Prometheus scrapes (self-contained HTML, no external assets) |
| `GET /img/{hash}?width=N` | **Sized image variants:** locally-resized JPEG thumbnails (`width` ∈ 92/154/185/342/500/780/1280, longest-side bound), cached on disk — originals smaller than the request are served unmodified |

Localization via the `X-Plex-Language` header (or query param) is passed through to
TMDB and used for the match language tiebreak; `X-Plex-Country` picks the content
rating. TMDB responses are cached with TTLs (search 12 h, details 24 h), so a full
library refresh touches upstream once per item, and refreshes after that hit the
cache entirely.

## Registering the providers in Plex

1. Plex Media Server 1.43+ (custom metadata providers must be enabled).
2. Settings → Metadata Agents → **Add Provider**, enter
   `http://<metacache-host>:8765/movie` (and again with `/tv` for the TV provider).
3. **Add Agent**, name it, and make Metacache the Primary provider for a library.
4. Create/assign a library using that agent. Requests are logged to the Metacache
   console.

> **Security:** the provider API is unauthenticated (Plex does not send auth yet).
> Keep it on your LAN, and use a firewall rule if you must expose it further.

## Tests

```bash
dotnet test
```

## Project layout

```
src/Metacache.Core/Cache/     SQLite store, single-flight, upstream gateway, item cache
src/Metacache.Core/Providers/  TMDB client (search/find/details through the cache)
src/Metacache.Core/Matching/   match scoring, title normalization, filename parsing
src/Metacache.Plex/            Plex provider API: wire models, catalog, rating keys,
                               match parser, movie + TV provider services, mappers,
                               cache warmer, endpoints
src/Metacache.Host/            ASP.NET Core host, config, logging
tests/Metacache.Host.Tests/    integration + unit tests (provider API, cache core, matching)
```

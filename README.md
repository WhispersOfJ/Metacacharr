# Metacache

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
  stale-if-error) and artwork URLs are rewritten to the local `/img/{hash}` endpoint.
- **TV end to end (M2):** shows, seasons, and episodes — match by title/year or by
  season/episode index / air date (structure-gated scoring), GUID pinning for all
  three kinds, full metadata with `parentTitle`/`grandparentTitle` + `parentIndex`,
  and the paged hierarchy endpoints `GET …/{ratingKey}/children` and
  `…/grandchildren` (`X-Plex-Container-Size` / `-Start`). Cast/crew (`Person[]`,
  `Role[]`, `Director[]`, `Writer[]`) and content ratings (`X-Plex-Country`-aware)
  ship for both movies and TV.
- `GET /healthz` liveness check.
- Admin surface: `GET /cache/stats` (cache sizes) and `POST /cache/purge` (expired-row
  cleanup), returning `{ "removed": n }`.
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
- **Metrics dashboard (M3):** `GET /metrics` reports cache hit rate (live request
  counters), per-kind item counts, upstream-cache size, and disk usage (image files
  + SQLite DB).

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
| `Metacache__Arr__RadarrUrl` / `RadarrApiKey` | *(none)* | Radarr instance + API key for `/warm/movies` (blank URL disables the source) |
| `Metacache__Arr__SonarrUrl` / `SonarrApiKey` | *(none)* | Sonarr instance + API key for `/warm/shows` (blank URL disables the source) |
| `Metacache__Arr__Concurrency` | `4` | How many items a warm run processes in parallel |

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

## Provider endpoints

| Endpoint | Purpose |
|---|---|
| `POST /library/metadata/matches` | Match — body: `{ "type": 1–4, "title": …, "year": …, "guid": …, "parentTitle": …, "grandparentTitle": …, "index": …, "parentIndex": …, "date": …, "filename": …, "manual": 0/1, "includeAdult": 0/1, "includeChildren": 0/1 }` (`type`: 1=movie, 2=show, 3=season, 4=episode). Auto returns the single best match (or empty → Plex shows Fix Match); `manual: 1` returns a ranked list |
| `GET /library/metadata/{ratingKey}` | Full metadata for a movie (`tmdb-movie-105`), show (`tmdb-show-15260`), season (`tmdb-season-15260-1`), or episode (`tmdb-episode-15260-1-1`) — `Guid[]`, `Genre[]`, `Image[]`, `Rating[]`, `Country[]`, `Studio[]`, cast/crew, content rating; artwork points at `/img/{hash}` |
| `GET /library/metadata/{ratingKey}/children` | Seasons of a show / episodes of a season, paged |
| `GET /library/metadata/{ratingKey}/grandchildren` | All episodes of a show, paged |
| `GET /library/metadata/{ratingKey}/images` | All image assets for the item |
| `POST /warm/movies` / `/warm/shows` / `/warm/all` | Pre-populate the cache from Radarr/Sonarr; returns the run summary (or 409 while another warm is running) |
| `GET /warm/status` | Live warmer state: `{ isRunning, lastResult }` |
| `GET /metrics` | Cache hit rate, per-kind item counts, upstream size, disk usage |

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

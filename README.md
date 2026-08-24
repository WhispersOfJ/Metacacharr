# Metacache

An ARR-app companion that caches movie/TV metadata locally so Plex refreshes from a
fast local server instead of hammering TMDB/TVDB over the internet. Implements Plex's
**Custom Metadata Provider** API (PMS 1.43+), which natively lets you point Plex at any
HTTP metadata server.

See [DESIGN.md](DESIGN.md) for the full architecture, API contract, and roadmap.

## Status: M0–M1 shipped

- `GET /movie` and `GET /tv` serve the MediaProvider definitions Plex needs to register
  the providers ("Add Provider").
- **Movies end to end (M1):** `POST /library/metadata/matches` (search, external-GUID
  pinning, ranked manual "Fix Match" lists), `GET /library/metadata/{ratingKey}` (full
  metadata), and `GET /library/metadata/{ratingKey}/images`. All TMDB traffic flows
  through the local cache (single-flight, TTL, ETag revalidation, stale-if-error) and
  artwork URLs are rewritten to the local `/img/{hash}` endpoint.
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

TV support (M2), cache warming (M3) and the ARR proxy face (M4) are next — see
DESIGN.md §12.

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
| `Metacache__Tmdb__ApiKey` | *(none)* | **Required for M1.** Your TMDB API Read Access Token — sent as an `Authorization: Bearer` header so it never appears in URLs, cache keys, or logs. Get one at themoviedb.org → Settings → API |
| `Metacache__Tmdb__BaseUrl` / `ImageBaseUrl` | TMDB v3 / `t/p/original` | Upstream endpoints (override for proxies) |

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

## Provider endpoints (M1)

| Endpoint | Purpose |
|---|---|
| `POST /library/metadata/matches` | Match — body: `{ "type": 1, "title": …, "year": …, "guid": …, "filename": …, "manual": 0/1, "includeAdult": 0/1 }`. Auto returns the single best match (or empty → Plex shows Fix Match); `manual: 1` returns a ranked list |
| `GET /library/metadata/{ratingKey}` | Full metadata for a movie, e.g. `tmdb-movie-105` — includes `Guid[]`, `Genre[]`, `Image[]`, `Rating[]`, `Country[]`, `Studio[]`; artwork points at `/img/{hash}` |
| `GET /library/metadata/{ratingKey}/images` | All image assets for the item |

Localization via the `X-Plex-Language` header (or query param) is passed through to
TMDB and used for the match language tiebreak. TMDB responses are cached with TTLs
(search 12 h, movie details 24 h), so a full library refresh touches upstream once per
movie, and refreshes after that hit the cache entirely.

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
                               match parser, movie provider service, endpoints
src/Metacache.Host/            ASP.NET Core host, config, logging
tests/Metacache.Host.Tests/    integration + unit tests (provider API, cache core, matching)
```

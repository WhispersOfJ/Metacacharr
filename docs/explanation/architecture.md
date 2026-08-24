# Architecture Overview

> How all the pieces of Metacache fit together.

## High-Level Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │                Metacache                     │
                    │                                             │
  Plex ──────────► │  Provider API (8765)                        │
                    │  ├─ /movie, /tv         (provider defs)     │
                    │  ├─ /library/metadata/* (match + metadata)  │
                    │  ├─ /img/{hash}         (artwork)           │
                    │  └─ /library/search     (browse)            │
                    │                                             │
  Radarr/Sonarr ─► │  ARR Proxy (443, opt-in)                    │
                    │  └─ Transparent HTTPS reverse proxy         │
                    │                                             │
  Webhooks ──────► │  /webhook/{radarr,sonarr,plex}              │
                    │                                             │
                    │  ┌─────────────────────────────────────┐   │
                    │  │         Cache Layer                  │   │
                    │  │  SQLite (upstream_cache + items +    │   │
                    │  │  urls + match_overrides + unmatched) │   │
                    │  │                                      │   │
                    │  │  SingleFlight (per-key dedup)        │   │
                    │  │  ETag revalidation                   │   │
                    │  │  Stale-if-error serving              │   │
                    │  │  429 retry-with-backoff              │   │
                    │  └─────────────────────────────────────┘   │
                    │                                             │
                    │  ┌─────────────────────────────────────┐   │
                    │  │      Upstream Providers              │   │
                    │  │  TMDB (movies + shows)               │   │
                    │  │  TVDB (episode fallback)             │   │
                    │  │  Radarr/Sonarr (inventory)           │   │
                    │  └─────────────────────────────────────┘   │
                    │                                             │
                    │  ┌─────────────────────────────────────┐   │
                    │  │      Warming Engine                  │   │
                    │  │  Bulk warm (Radarr/Sonarr inventory) │   │
                    │  │  Event-driven (webhooks)             │   │
                    │  │  Predictive (playback-start)         │   │
                    │  │  Nightly scheduled                   │   │
                    │  │  Multi-language                       │   │
                    │  └─────────────────────────────────────┘   │
                    │                                             │
                    │  ┌─────────────────────────────────────┐   │
                    │  │      Admin + Dashboard               │   │
                    │  │  /dashboard (interactive)            │   │
                    │  │  /ui/* (10 specialized pages)        │   │
                    │  │  /metrics + /metrics/prometheus       │   │
                    │  │  Bearer token auth                    │   │
                    │  └─────────────────────────────────────┘   │
                    └─────────────────────────────────────────────┘
```

## Request Flow

### Plex Metadata Request

1. Plex sends `GET /library/metadata/tmdb-movie-550?language=de`
2. `ProviderEndpoints` parses the rating key and language
3. `MovieProviderService.GetMovieMetadataAsync` is called
4. The TMDB client fetches with `?language=de` through the `UpstreamCache`
5. `UpstreamCache` checks SQLite → hit? serve. miss? fetch from TMDB.
6. Response is mapped to Plex format and returned

### Warm Request

1. `POST /warm/all` triggers `CacheWarmer.WarmAllAsync`
2. Warmer fetches movie list from Radarr via `ArrClient`
3. For each movie × each configured language:
   a. Fetch metadata from TMDB (through `UpstreamCache`)
   b. Fetch credits, release dates, images
   c. Store as `CachedItem` in the `items` table
   d. Store artwork in the image cache
4. Progress is tracked in `WarmProgress` for the UI

### ARR Proxy Request

1. Radarr resolves `api.themoviedb.org` → Metacache IP (DNS override)
2. Radarr connects to Metacache:443 with HTTPS + SNI
3. `ProxyMiddleware` reconstructs the full upstream URL
4. `UpstreamCache` serves from cache or fetches from real API
5. Response returned to Radarr (identical to real API)

## Key Design Decisions

### Why SQLite?

- **Zero dependencies** — runs anywhere .NET runs
- **WAL mode** — concurrent reads while warming writes
- **Single file** — easy backup, easy migration
- **Sufficient performance** — metadata is small, reads dominate

### Why a Transparent Proxy (not just a cache)?

Radarr/Sonarr hardcode their metadata endpoints — no pluggable backend. The only way to intercept their calls is a transparent proxy with DNS override. This eliminates **all** duplicate API calls, not just Plex's.

### Why Single-Flight?

Concurrent requests for the same URL (e.g. multiple Plex clients refreshing simultaneously) would all hit upstream. Single-flight ensures one request per unique URL — others wait for the first result.

### Why ETag Revalidation?

TMDB supports `If-None-Match` / `If-Modified-Since`. On revalidation:
- 304 (Not Modified) → refresh TTL, zero bandwidth
- 200 (Changed) → store new body, update TTL

This means a library refresh with no changes costs almost nothing.

### Why Stale-if-Error?

When upstream is down (WAN outage, TMDB maintenance), Metacache serves the last known good response. This makes the library work offline — the core value proposition.

## Data Flow Diagrams

### Image Caching

```
Plex → GET /img/{hash}?width=185
  │
  ├─ Variant exists on disk? → serve JPEG
  │
  └─ Original exists on disk?
      ├─ Resize to width=185 (single-flighted)
      │  └─ Store variant atomically (temp + move)
      └─ Serve variant
          └─ Neither? → fetch from upstream → store original → resize → serve
```

### Match Scoring

```
Plex → POST /library/metadata/matches { title, year, guid, filename }
  │
  ├─ Consult match_overrides → pin found? → return pinned result
  │
  └─ Search TMDB
      ├─ Movie: SearchMoviesAsync(title, year)
      └─ TV: SearchShowsAsync(title) or FindAsync(guid)
          │
          └─ Score each result:
              score = titleScore × 0.40
                    + yearScore × 0.20
                    + guidScore × 0.25
                    + filenameScore × 0.15
              │
              ├─ auto + score ≥ 0.75 → return best
              └─ manual or score < 0.75 → return ranked list
```

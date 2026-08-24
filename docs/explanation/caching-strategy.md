# Caching Strategy

> How Metacache's cache works: ETag revalidation, stale-if-error, single-flight, and TTL management.

## Three-Layer Cache

Metacache has three distinct cache layers:

### 1. Upstream Cache (`upstream_cache` table)

Stores raw HTTP responses from TMDB/TVDB. Content-addressed by SHA-256 of the URL.

- **TTL:** 12h (search), 24h (details)
- **Revalidation:** ETag / If-Modified-Since
- **Stale-if-error:** Serves expired content when upstream fails
- **Size:** Bounded by SQLite + image disk usage

### 2. Item Cache (`items` table)

Normalized metadata entries for browse index and search. Per-language entries with `(id, lang)` primary key.

- **TTL:** 24h
- **Purpose:** Powers `/library/search`, `/admin/items`, browse endpoints
- **Populated by:** Cache warmer (bulk + event-driven)

### 3. Image Cache (`urls` table + `data/images/`)

Content-addressed artwork storage with size variants.

- **TTL:** 7 days
- **Size cap:** 10 GB total, 20 MB per file
- **Eviction:** LRU (oldest first when over cap)
- **Variants:** Original + resized JPEGs (width: 92, 154, 185, 342, 500, 780, 1280)

## ETag Revalidation

When a cached entry expires, Metacache doesn't immediately delete it. Instead:

1. **Send conditional request** with `If-None-Match: {etag}` and `If-Modified-Since: {lastModified}`
2. **Upstream responds:**
   - `304 Not Modified` → Content unchanged. Refresh TTL, return cached body. **Zero bandwidth.**
   - `200 OK` → Content changed. Store new body + new ETag, update TTL.
3. **Key insight:** A library refresh with no metadata changes costs almost nothing — just HTTP HEAD-sized requests.

## Stale-if-Error

When upstream fails (transport error, 5xx, rate limit), Metacache serves the last known good response:

```
Upstream fails → cached entry exists? → serve stale content
                                     → no cache? → throw error
```

**Guards:**
- `ServeStaleOnError` (default: true) — can be disabled
- `MaxStaleAge` (default: null = unbounded) — hard ceiling on stale age
- A stale response is served with `X-Cache-Source: Stale` header

**Why this matters:** If TMDB goes down at 2 AM and your Plex auto-scans at 3 AM, the library still refreshes successfully from cached data. Users never see "metadata unavailable."

## Single-Flight Deduplication

When multiple requests arrive for the same URL simultaneously:

```
Request 1 → starts upstream fetch
Request 2 → joins Request 1's task (waits)
Request 3 → joins Request 1's task (waits)
Request 1 completes → all three get the same result
```

**Key:** `SingleFlight.RunAsync(key, factory)` ensures one in-flight request per cache key. Concurrent callers share the result.

**Why this matters:** Without single-flight, a Plex library scan with 500 movies could trigger 500 simultaneous TMDB requests. With single-flight, it's one request per unique URL.

## 429 Retry with Backoff

When TMDB rate-limits Metacache (HTTP 429):

1. **Check Retry-After header** — if present, wait that duration
2. **Exponential backoff** — base × 2^attempt (default base: 2s)
3. **Cap** — max 30s per retry wait
4. **Max retries** — 2 by default (configurable via `CachePolicy.MaxRetries`)
5. **Count** — each 429 is counted in the `/metrics/prometheus` rate-limit gauge

**Why this matters:** Rate-limited requests wait out the window instead of failing or serving stale.

## TTL Table

| Content | TTL | Rationale |
|---------|-----|-----------|
| Search results | 12 hours | Titles change rarely, but new results appear |
| Metadata details | 24 hours | Details change occasionally (ratings, episodes) |
| Images | 7 days | Artwork changes very rarely |
| Items (browse index) | 24 hours | Matches the metadata TTL |

## Cache Key Design

### Upstream cache keys

```
key = SHA-256(normalized_url)
```

**Normalization:**
- API keys stripped from URLs (never stored in DB)
- Query parameters sorted for consistency
- Case-insensitive host matching

### Item cache keys

```
key = (id, lang)  -- PRIMARY KEY
```

Examples:
- `("movie-550", "en-US")` — Inception in English
- `("movie-550", "de-DE")` — Inception in German
- `("show-15260", "fr-FR")` — Adventure Time in French

### Match override keys

Computed from the Plex match hint:
- Movies: `movie-{normalized_title}-{year}`
- Shows: `show-{normalized_title}-{year}`
- Seasons: `season-{parent_title}-{year}`
- Episodes: `episode-{grandparent_title}-{year}`

When Plex sends a GUID, the override key is the GUID itself (so a guid-keyed pin fires on every refresh).

## Eviction Policy

When the image cache exceeds `MaxTotalBytes`:

1. Query oldest 10 URLs by `stored_at`
2. Delete each file from disk
3. Remove from `urls` table
4. Repeat until under cap

This is LRU-style eviction — the least recently stored images are evicted first.

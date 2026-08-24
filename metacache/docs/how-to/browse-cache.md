# How to Browse the Cache

> Search, filter, and inspect cached metadata items.

## Cache Browser UI

Open: `http://METACACHE_IP:8765/ui/cache-diff`

Features:
- **Search by title** — case-insensitive search
- **Filter by kind** — movie, show, season, episode, or all
- **Filter by freshness** — fresh only, stale only, or any
- **Poster preview** — see artwork inline
- **Detail panel** — click any item for full metadata

## API: Search Items

```bash
# Search all items
curl "http://localhost:8765/admin/items"

# Search by title
curl "http://localhost:8765/admin/items?q=inception"

# Filter by kind
curl "http://localhost:8765/admin/items?kind=movie"

# Filter by freshness
curl "http://localhost:8765/admin/items?fresh=true"

# Combine filters
curl "http://localhost:8765/admin/items?q=inception&kind=movie&fresh=true&limit=10"
```

Response:
```json
{
  "total": 1,
  "items": [
    {
      "id": "movie-550",
      "kind": "movie",
      "title": "Inception",
      "year": 2010,
      "thumb": "/img/abc123",
      "sourceId": "550",
      "fetchedAt": "2026-08-24T10:00:00Z",
      "expiresAt": "2026-08-25T10:00:00Z",
      "fresh": true
    }
  ]
}
```

## API: Single Item Detail

```bash
curl http://localhost:8765/admin/items/movie-550
```

Returns the full `CachedItem` record with JSON metadata.

## API: Upstream Cache

```bash
# Get stats + eviction candidates
curl "http://localhost:8765/admin/upstream?limit=20"
```

## API: Database Info

```bash
curl http://localhost:8765/admin/database
```

Returns entry counts and byte sizes for all tables.

## Freshness Explained

Items are "fresh" when `expiresAt > now`. The default TTL is:
- **Search results:** 12 hours
- **Metadata details:** 24 hours
- **Images:** 7 days

When an item expires:
1. The next Plex refresh revalidates with ETags (304 = no change, TTL refreshed)
2. If upstream is down, stale content is served (stale-if-error)
3. The freshness is updated automatically

## Cache Freshness Heatmap

Open: `http://METACACHE_IP:8765/ui/freshness`

Shows a visual heatmap:
- **Green:** Fresh items (within TTL)
- **Amber:** Stale items (expired but within stale-if-error window)
- **Red:** Expired items (past stale window)

Includes an "Expiring Soon" table showing items that will expire in the next 24 hours.

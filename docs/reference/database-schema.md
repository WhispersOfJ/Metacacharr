# Database Schema

> SQLite schema for the Metacache database (version 4).

## Overview

Metacache uses a single SQLite database with WAL mode for concurrent reads. The schema version is tracked via `PRAGMA user_version` and migrations are applied in-place on startup.

## Tables

### `upstream_cache`

Raw HTTP responses from upstream APIs (TMDB, TVDB). Content-addressed by URL hash.

```sql
CREATE TABLE IF NOT EXISTS upstream_cache (
    key         TEXT PRIMARY KEY,       -- SHA-256 hex of the request URL
    url         TEXT NOT NULL,          -- Original request URL
    status_code INTEGER NOT NULL,       -- HTTP status code
    content_type TEXT,                  -- Content-Type header
    body        BLOB NOT NULL,          -- Response body
    fetched_at  TEXT NOT NULL,          -- ISO 8601 timestamp
    expires_at  TEXT NOT NULL,          -- ISO 8601 expiry timestamp
    etag        TEXT,                   -- ETag header for revalidation
    last_modified TEXT,                 -- Last-Modified header
    hits        INTEGER NOT NULL DEFAULT 0  -- Cache hit counter
);
```

**Indexes:**
- `ix_upstream_expires` on `expires_at` (for TTL expiry queries)

---

### `items`

Normalized metadata items, keyed by `id + lang`. Used for browse index and search.

```sql
CREATE TABLE IF NOT EXISTS items (
    id          TEXT NOT NULL,          -- Rating key (e.g. "movie-550")
    kind        TEXT NOT NULL,          -- movie, show, season, episode
    source      TEXT NOT NULL,          -- Provider source (e.g. "tmdb")
    source_id   TEXT NOT NULL,          -- Source-specific ID
    lang        TEXT NOT NULL,          -- Language code (e.g. "en-US")
    json        TEXT NOT NULL,          -- Full metadata JSON
    fetched_at  TEXT NOT NULL,          -- ISO 8601 timestamp
    expires_at  TEXT NOT NULL,          -- ISO 8601 expiry timestamp
    etag        TEXT,                   -- ETag for revalidation
    title       TEXT,                   -- Normalized title (for search)
    year        INTEGER,               -- Release year (for search)
    thumb       TEXT,                   -- Rewritten thumbnail path
    PRIMARY KEY (id, lang)
);
```

**Indexes:**
- `ix_items_source` on `source_id`
- `ix_items_kind_lang` on `(kind, lang)`
- `ix_items_title` on `title` (for LIKE searches)

**Schema migrations:**
- v1 → v2: Added `match_overrides` and `unmatched` tables
- v2 → v3: Added `title`, `year` columns to `items`
- v3 → v4: Added `thumb` column to `items`

---

### `urls`

Image/asset URLs, content-addressed by SHA-256 hash.

```sql
CREATE TABLE IF NOT EXISTS urls (
    hash        TEXT PRIMARY KEY,       -- SHA-256 hex of the original URL
    url         TEXT NOT NULL,          -- Original image URL
    path        TEXT NOT NULL,          -- Local file path
    content_type TEXT,                  -- MIME type
    size        INTEGER NOT NULL,       -- File size in bytes
    stored_at   TEXT NOT NULL           -- ISO 8601 timestamp
);
```

---

### `match_overrides`

Persisted match overrides (pins). Created by the Fix Match UI or API.

```sql
CREATE TABLE IF NOT EXISTS match_overrides (
    key         TEXT PRIMARY KEY,       -- Match hint key (e.g. "movie-inception-2010")
    kind        TEXT NOT NULL,          -- movie, show, season, episode
    target      TEXT NOT NULL,          -- Pinned TMDB ID (e.g. "tmdb-movie-550")
    notes       TEXT,                   -- Optional description
    created_at  TEXT NOT NULL           -- ISO 8601 timestamp
);
```

---

### `unmatched`

Captured auto-match failures (zero-candidate matches).

```sql
CREATE TABLE IF NOT EXISTS unmatched (
    key         TEXT PRIMARY KEY,       -- Match hint key
    kind        TEXT NOT NULL,          -- movie, show, season, episode
    title       TEXT,                   -- Item title
    year        INTEGER,               -- Release year
    hint_json   TEXT NOT NULL,          -- Full MatchHint JSON
    recorded_at TEXT NOT NULL,          -- ISO 8601 timestamp
    count       INTEGER NOT NULL DEFAULT 1  -- Recurrence count
);
```

## Common Queries

### Check cache freshness

```sql
SELECT COUNT(*) FROM upstream_cache WHERE expires_at > datetime('now');
```

### Find items by title

```sql
SELECT * FROM items WHERE title LIKE '%inception%' AND kind = 'movie';
```

### Get cache stats

```sql
SELECT
    (SELECT COUNT(*) FROM upstream_cache) AS upstream_entries,
    (SELECT SUM(LENGTH(body)) FROM upstream_cache) AS upstream_bytes,
    (SELECT COUNT(*) FROM items) AS item_entries,
    (SELECT COUNT(*) FROM urls) AS url_entries;
```

### Find stale entries

```sql
SELECT * FROM upstream_cache WHERE expires_at < datetime('now') ORDER BY fetched_at;
```

### Purge expired

```sql
DELETE FROM upstream_cache WHERE expires_at < datetime('now');
```

## Migration Strategy

Migrations run on every startup using `PRAGMA user_version`:

1. Read current version
2. Apply ALTER TABLE steps (each guarded by `pragma_table_info` column check)
3. Update version number

This is idempotent — re-running the same version applies no changes.

## Backup

```bash
# Hot backup (WAL mode safe)
sqlite3 data/metacache.db ".backup data/metacache-backup.db"

# Or copy the file while Metacache is running (WAL mode safe)
cp data/metacache.db data/metacache-backup.db
```

# API Reference

> Complete reference for all Metacache HTTP endpoints.

**Base URL:** `http://METACACHE_IP:8765`

**Authentication:** Bearer token (when `Metacache:Auth:ApiKey` is set). See [Configure Auth](../how-to/configure-auth.md).

---

## Provider Endpoints

These endpoints implement the Plex Custom Metadata Provider API.

### `GET /`

Returns the root service document.

**Response:** Plain text listing available providers.

---

### `GET /movie`

Returns the movie provider definition (Plex reads this to register the agent).

**Response:** `application/json`
```json
{
  "Name": "Metacache Movie Provider",
  "Protocol": "http",
  "ProtocolVersion": "3",
  "Agent": "tv.plex.agents.custom.metacache.movie",
  "Plugins": [],
  "Icon": "..."
}
```

---

### `GET /tv`

Returns the TV provider definition.

**Response:** Same structure as `/movie` but for TV.

---

### `POST /library/metadata/matches`

Search for matches. Called by Plex during "Fix Match" and auto-match.

**Request body:**
```json
{
  "type": 1,
  "title": "Inception",
  "year": 2010,
  "guid": "imdb://tt1375666",
  "parentTitle": null,
  "grandparentTitle": null,
  "index": null,
  "parentIndex": null,
  "date": null,
  "filename": "Inception.2010.1080p.mkv",
  "manual": 0,
  "includeAdult": 0,
  "includeChildren": 0
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | int | 1=movie, 2=show, 3=season, 4=episode |
| `title` | string | Item title |
| `year` | int? | Release year |
| `guid` | string? | External GUID (IMDB, TMDB, TVDB) |
| `manual` | int | 0=auto, 1=manual Fix Match |
| `filename` | string? | Source filename |

**Response:** `application/json` — `MetadataContainer` with ranked matches.

When `manual=1`, returns all candidates ranked by score. When `manual=0`, returns the single best match (or empty if below threshold → Plex shows Fix Match UI).

---

### `GET /library/metadata/{ratingKey}`

Returns full metadata for a movie, show, season, or episode.

**Path parameters:**
| Parameter | Example | Description |
|-----------|---------|-------------|
| `ratingKey` | `tmdb-movie-550` | Plex rating key |

**Query parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `X-Plex-Language` | string | Language code (e.g. `de`, `fr`) |
| `X-Plex-Country` | string | Country code for content ratings |

**Response:** `application/json` — `MetadataContainer` with full metadata including:
- `Guid[]` — External IDs
- `Genre[]`, `Country[]`, `Studio[]`
- `Role[]`, `Director[]`, `Writer[]` — Cast/crew
- `Rating[]` — Content ratings
- `Image[]` — Artwork (pointing to local `/img/{hash}`)

---

### `GET /library/metadata/{ratingKey}/children`

Returns seasons of a show, or episodes of a season. Paged via `X-Plex-Container-Size` and `X-Plex-Container-Start` headers.

---

### `GET /library/metadata/{ratingKey}/grandchildren`

Returns all episodes of a show. Paged.

---

### `GET /library/metadata/{ratingKey}/images`

Returns all image assets for the item.

---

## Library Browse Endpoints

### `GET /library/search`

Search the warmed cache index.

**Query parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `title` | string | — | Case-insensitive title search |
| `kind` | string | `movie,show` | Filter by kind |
| `year` | int? | — | Exact year match |
| `X-Plex-Container-Start` | int | 0 | Offset |
| `X-Plex-Container-Size` | int | 20 | Page size |

**Response:** Plex-shaped `MediaContainer` with `Metadata[]`.

---

### `GET /library/recentlyAdded`

Returns most recently warmed items (newest first). Same paging as `/library/search`.

---

## Image Endpoints

### `GET /img/{hash}`

Serves cached artwork by content hash.

**Query parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `width` | int | (original) | Resize to this width (longest side). Allowed: 92, 154, 185, 342, 500, 780, 1280 |

**Response:** Image bytes with appropriate `Content-Type`.

---

## Cache Admin Endpoints

**🔒 Requires auth** (when `Metacache:Auth:ApiKey` is set)

### `GET /cache/stats`

Returns cache statistics.

**Response:**
```json
{
  "upstreamEntries": 1234,
  "upstreamBytes": 52428800,
  "itemEntries": 847,
  "urlEntries": 2345
}
```

---

### `POST /cache/purge`

Deletes all expired entries.

**Response:**
```json
{ "removed": 42 }
```

---

## Admin Endpoints

**🔒 Requires auth**

### `GET /admin/items`

Search cached items.

**Query parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | — | Title search (case-insensitive LIKE) |
| `kind` | string | — | Filter: movie, show, season, episode |
| `fresh` | bool? | — | Filter by freshness |
| `limit` | int | 50 | Max results (1–500) |

---

### `GET /admin/items/{id}`

Returns a single cached item by ID.

---

### `GET /admin/upstream`

Returns upstream cache stats and eviction candidates.

**Query parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Max eviction candidates to return |

---

### `POST /admin/purge/selective`

Selective purge with options.

**Request body:**
```json
{
  "expired": true,
  "imageBytes": 5368709120
}
```

| Field | Type | Description |
|-------|------|-------------|
| `expired` | bool | Purge expired entries |
| `imageBytes` | long | Evict oldest images until under this byte cap |

---

### `GET /admin/database`

Returns database summary (entry counts + byte sizes).

---

### `GET /admin/overrides`

Lists all match overrides.

---

### `POST /admin/overrides`

Create a match override.

**Request body:**
```json
{
  "kind": "movie",
  "target": "tmdb-movie-550",
  "notes": "Correct match for Inception"
}
```

---

### `DELETE /admin/overrides/{key}`

Delete a match override.

---

### `GET /admin/unmatched`

Lists captured unmatched items (zero-candidate auto-matches).

---

### `POST /admin/unmatched/{key}/pin`

Pin an unmatched item as an override.

---

### `DELETE /admin/unmatched/{key}`

Delete a single unmatched entry.

---

### `DELETE /admin/unmatched`

Clear all unmatched entries.

---

## GUID Lookup

### `GET /guid/lookup`

Translate any GUID across providers.

**Query parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `guid` | string | Any GUID: `imdb://tt0088763`, `tmdb://550`, `tvdb://1234`, `tmdb-movie-550`, bare `tt0088763` or `550` |

**Response:**
```json
{
  "guid": "imdb://tt0088763",
  "kind": "movie",
  "title": "The Matrix",
  "year": 1999,
  "imdb": "tt0133093",
  "tmdb": "550",
  "tvdb": null,
  "tmdbId": 550,
  "itemId": "movie-550",
  "cached": true
}
```

---

## Warm Endpoints

**🔒 `POST` methods require auth**

### `GET /warm/status`

Returns live warmer state.

**Response:**
```json
{
  "isRunning": false,
  "lastResult": { "source": "all", "itemsWarmed": 847, ... },
  "completedAt": "2026-08-24T03:05:00Z"
}
```

---

### `GET /warm/progress`

Returns real-time progress during a warm run.

**Response (idle):**
```json
{ "isRunning": false }
```

**Response (running):**
```json
{
  "source": "movies",
  "totalItems": 500,
  "processedItems": 234,
  "imagesWarmed": 468,
  "errors": 0,
  "currentItem": "Inception",
  "startedAt": "2026-08-24T10:30:00Z",
  "elapsedSeconds": 12.5,
  "estimatedRemainingSeconds": 14.2,
  "percentComplete": 46.8
}
```

---

### `POST /warm/movies`

Warm all movies from Radarr. Returns 409 if already running.

### `POST /warm/shows`

Warm all shows from Sonarr. Returns 409 if already running.

### `POST /warm/all`

Warm everything. Returns 409 if already running.

---

## Webhook Endpoints

**🔒 Requires auth**

### `POST /webhook/radarr`

Warm a movie on Radarr import event.

**Request body:** Radarr webhook JSON (uses `movie.title`, `movie.year`, `movie.id`).

---

### `POST /webhook/sonarr`

Warm a show on Sonarr import event.

---

### `POST /webhook/plex`

Predictive warm on Plex playback start.

**Request body:** Plex webhook JSON (uses `event`, `Metadata[]`, `Guid[]`).

Only `event: media.play` triggers warming. Other events return `{ "result": "ignored" }`.

---

## Metrics Endpoints

### `GET /metrics`

Returns cache metrics as JSON.

---

### `GET /metrics/prometheus`

Returns metrics in Prometheus text exposition format for scraping.

---

## Proxy Endpoints

### `GET /proxy/status`

Returns proxy configuration and routed hostnames.

---

### `GET /proxy/ca-cert`

Downloads the local CA certificate (PEM format) for trust store installation.

---

## UI Pages

| URL | Page |
|-----|------|
| `/dashboard` | Main interactive dashboard |
| `/ui/setup` | Setup wizard |
| `/ui/warm-progress` | Real-time warm progress |
| `/ui/matches` | Fix Match panel |
| `/ui/freshness` | Cache freshness heatmap |
| `/ui/cache-diff` | Cache browser with poster previews |
| `/ui/warm-calendar` | Warm run history |
| `/ui/health` | Provider health dashboard |
| `/ui/guid` | GUID translation explorer |
| `/ui/overrides` | Match override editor |
| `/ui/register` | Plex registration helper |

---

## Health Check

### `GET /healthz`

Returns `ok` (plain text). Used for liveness probes.

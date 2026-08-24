# How to Translate GUIDs

> Use the GUID Explorer to convert between IMDB, TMDB, and TVDB identifiers.

## The Problem

Different tools use different IDs for the same content:
- **IMDB:** `tt0088763` (movies)
- **TMDB:** `550` (movies), `15260` (shows)
- **TVDB:** `1234` (shows)
- **Plex:** `tmdb-movie-550`, `tmdb-show-15260`

You need to translate between these when troubleshooting matches or querying the cache.

## Using the GUID Explorer UI

```
http://METACACHE_IP:8765/ui/guid
```

1. Paste any GUID (IMDB, TMDB, TVDB, or Plex rating key)
2. Click **Translate**
3. See all equivalents with cached status and links

### Example inputs

| Input | Resolves to |
|-------|-------------|
| `imdb://tt0088763` | TMDB 550 (The Matrix) |
| `tmdb://550` | IMDB tt0133093, TVDB — |
| `tvdb://1234` | TMDB show ID |
| `tmdb-movie-550` | Plex rating key for TMDB movie 550 |
| `tmdb-show-15260` | Plex rating key for TMDB show 15260 |

## Using the API

```bash
curl "http://localhost:8765/guid/lookup?guid=imdb://tt0088763"
```

Returns:
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

## How Resolution Works

1. **Parse the input:** Detect format (IMDB, TMDB, TVDB, Plex rating key, bare digits)
2. **Check local index:** See if the item is already warmed in the cache
3. **Query TMDB:** Use the `/find` endpoint to cross-reference
4. **Disambiguate:** Bare TMDB IDs are probed as show-first, then movie (the probed 404 is cached)

## Common Use Cases

### Find the TMDB ID for an IMDB ID

```bash
curl "http://localhost:8765/guid/lookup?guid=imdb://tt0133093"
# → tmdbId: 550
```

### Check if a TVDB ID is cached

```bash
curl "http://localhost:8765/guid/lookup?guid=tvdb://1234"
# → cached: true/false
```

### Translate a Plex rating key

```bash
curl "http://localhost:8765/guid/lookup?guid=tmdb-movie-550"
# → imdb: tt0133093, tmdb: 550
```

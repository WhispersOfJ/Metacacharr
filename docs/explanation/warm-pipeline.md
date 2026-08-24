# Explanation: Warm Pipeline

> How Metacache warms its cache through different triggers.

## Overview

Metacache supports three warming strategies:

1. **Bulk Warming** — Warm entire libraries from Radarr/Sonarr
2. **Webhook Warming** — Warm individual items on import events
3. **Predictive Warming** — Warm based on user behavior

## Bulk Warming

### Trigger

Manual or scheduled warm of entire libraries:

```bash
# Warm all movies
curl -X POST http://localhost:8765/warm/movies

# Warm all shows
curl -X POST http://localhost:8765/warm/shows

# Warm everything
curl -X POST http://localhost:8765/warm/all
```

### Flow

```
Warm Request → CacheWarmer → Radarr/Sonarr API → Fetch Metadata → Store in Cache
                              │
                              ├── Get all movies
                              ├── For each movie:
                              │   ├── Fetch from TMDB/TVDB
                              │   ├── Store metadata
                              │   ├── Fetch images
                              │   └── Store images
                              └── Return progress
```

### Implementation

```csharp
public async Task WarmMoviesAsync(CancellationToken ct)
{
    var movies = await _radarr.GetMoviesAsync(ct);
    foreach (var movie in movies)
    {
        await WarmItemAsync(movie.TmdbId, "movie", ct);
    }
}
```

## Webhook Warming

### Trigger

Events from Radarr/Sonarr/Plex:

```yaml
# Radarr webhook
POST http://metacache:8765/webhook/radarr
{
  "eventType": "Download",
  "movie": { "tmdbId": 123 }
}

# Sonarr webhook
POST http://metacache:8765/webhook/sonarr
{
  "eventType": "Download",
  "episodes": [{ "tvdbId": 456 }]
}

# Plex webhook
POST http://metacache:8765/webhook/plex
{
  "event": "library.new",
  "Metadata": { "guid": "plex://movie/..." }
}
```

### Flow

```
Webhook → Parse Payload → Extract IDs → Fetch Metadata → Store in Cache
                           │
                           ├── Radarr: tmdbId
                           ├── Sonarr: tvdbId
                           └── Plex: ratingKey → lookup → tmdbId
```

### Implementation

```csharp
app.MapPost("/webhook/radarr", async (CacheWarmer warmer, HttpContext context) =>
{
    var payload = await context.Request.ReadFromJsonAsync<RadarrWebhook>();
    if (payload.EventType == "Download")
    {
        await warmer.WarmItemAsync(payload.Movie.TmdbId, "movie", ct);
    }
});
```

## Predictive Warming

### Trigger

Plex playback events:

```yaml
# Plex webhook
POST http://metacache:8765/webhook/plex
{
  "event": "media.play",
  "Metadata": { "guid": "plex://movie/..." }
}
```

### Flow

```
Media Play → Parse Payload → Warm Played Item → Warm Related Items
                           │
                           ├── Next episodes (TV)
                           ├── Similar movies
                           └── Same collection
```

### Implementation

```csharp
app.MapPost("/webhook/plex", async (CacheWarmer warmer, HttpContext context) =>
{
    var payload = await context.Request.ReadFromJsonAsync<PlexWebhook>();
    if (payload.Event == "media.play")
    {
        // Warm the played item
        await warmer.WarmItemAsync(payload.Metadata.RatingKey, "movie", ct);
        
        // Warm next episodes (TV)
        if (payload.Metadata.Type == "episode")
        {
            await warmer.WarmNextEpisodesAsync(payload.Metadata, ct);
        }
    }
});
```

## Multi-Language Warming

### Configuration

```bash
WARM_LANG_0=en-US
WARM_LANG_1=de-DE
WARM_LANG_2=fr-FR
```

### Flow

```
Warm Request → For Each Language → Fetch Metadata → Store per Language
                           │
                           ├── en-US metadata
                           ├── de-DE metadata
                           └── fr-FR metadata
```

### Implementation

```csharp
public async Task WarmItemAsync(int tmdbId, string kind, CancellationToken ct)
{
    foreach (var lang in _options.Languages)
    {
        var metadata = await _tmdb.GetMovieAsync(tmdbId, lang, ct);
        await _cache.StoreItemAsync(tmdbId, kind, metadata, lang, ct);
    }
}
```

## Warm Progress Tracking

### Status Endpoint

```bash
curl http://localhost:8765/warm/status
```

Response:
```json
{
  "running": true,
  "processed": 150,
  "total": 500,
  "currentItem": "Inception (2010)",
  "imagesCached": 45,
  "errors": 2,
  "elapsed": "00:05:30",
  "eta": "00:12:00"
}
```

### Real-Time Updates

The dashboard shows real-time progress:

- **Progress Bar** — Processed / Total
- **Current Item** — Name of item being warmed
- **Speed** — Items per second
- **ETA** — Estimated time remaining

## Performance Considerations

### Rate Limiting

Metacache respects upstream rate limits:

- **TMDB** — 40 requests per 10 seconds
- **TVDB** — 100 requests per minute

### Concurrency

```yaml
Metacache__Arr__Concurrency: 4
```

Controls parallel requests to Radarr/Sonarr.

### Retry with Backoff

On 429 responses:

```csharp
if (response.StatusCode == 429)
{
    var retryAfter = response.Headers.RetryAfter?.Delta ?? TimeSpan.FromSeconds(1);
    await Task.Delay(retryAfter, ct);
    // Retry request
}
```

## Monitoring

### Prometheus Metrics

| Metric | Description |
|--------|-------------|
| `metacache_warm_items_total` | Total items warmed |
| `metacache_warm_duration_seconds` | Warm operation duration |
| `metacache_warm_errors_total` | Total warm errors |

### Grafana Dashboard

The warm dashboard shows:

- **Warm Rate** — Items warmed per minute
- **Error Rate** — Failed warm operations
- **Duration** — Time per warm operation
- **Progress** — Current warm progress

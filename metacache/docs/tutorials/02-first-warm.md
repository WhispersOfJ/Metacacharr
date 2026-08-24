# Tutorial: Your First Warm

> **Goal:** Understand how cache warming works, run a warm, and verify that Plex uses the cache.
>
> **Time:** ~10 minutes
>
> **Prerequisites:** [Getting Started](01-getting-started.md) completed

## What is Warming?

Cache warming pre-fetches metadata from TMDB/TVDB and stores it locally, so Plex never waits for upstream APIs during refresh. Without warming, the first Plex refresh pays the full API latency for every item.

## Running a Warm

### From the command line

```bash
# Warm everything (movies + shows)
curl -X POST http://localhost:8765/warm/all

# Warm just movies (requires Radarr configured)
curl -X POST http://localhost:8765/warm/movies

# Warm just shows (requires Sonarr configured)
curl -X POST http://localhost:8765/warm/shows
```

### From the UI

Open the **[Warm Progress page](http://localhost:8765/ui/warm-progress)** — click any warm button and watch the real-time progress bar with ETA.

### Checking warm status

```bash
curl http://localhost:8765/warm/status
```

Returns:
```json
{
  "isRunning": false,
  "lastResult": {
    "source": "all",
    "itemsWarmed": 847,
    "imagesWarmed": 1234,
    "missing": 0,
    "errors": 0,
    "elapsedSeconds": 42.5
  }
}
```

## What Gets Warmed

| Source | What it fetches |
|--------|----------------|
| **Radarr** (`/warm/movies`) | Every movie: metadata, credits, release dates, poster, backdrop |
| **Sonarr** (`/warm/shows`) | Every show: metadata, all seasons, all episodes, artwork |
| **Predictive** (`/webhook/plex`) | Played item + next episodes + 3 similar titles |

Each item is stored in the SQLite database with:
- Full metadata JSON (from TMDB API response)
- Rewritten artwork URLs pointing to local `/img/{hash}` endpoints
- Expiry timestamps for automatic stale-if-error fallback

## Verifying Cache Hits

After warming, refresh your Plex library. Then check the console output — you should see:

```
[info] Cache hit for /movie/550 (source: cache)
[info] Cache hit for /tv/15260 (source: cache)
```

Or check the **[Cache Freshness page](http://localhost:8765/ui/freshness)** — all items should show as "Fresh" (green).

## Nightly Automatic Warm

By default, Metacache runs `/warm/all` every night at 03:00. Configure the schedule:

```bash
Metacache__Warm__ScheduleTime=04:30  # Run at 4:30 AM
```

Or disable it entirely:

```bash
Metacache__Warm__Enabled=false
```

## Event-Driven Warm

Configure Radarr/Sonarr webhooks to warm individual items on import:

**Radarr:** Settings → Connect → Add → Webhook → URL: `http://YOUR_METACACHE:8765/webhook/radarr`

**Sonarr:** Settings → Connect → Add → Webhook → URL: `http://YOUR_METACACHE:8765/webhook/sonarr`

When a new item is imported, Metacache warms it immediately.

## Next Steps

- [Multi-Language Warming](03-multi-language.md) — Cache in multiple languages
- [Predictive Warming](../explanation/predictive-warming.md) — How playback-start events work

# How to Warm from the UI

> Trigger and monitor cache warming from the browser.

## Warm Progress Page

Open: `http://METACACHE_IP:8765/ui/warm-progress`

This page shows:
- **Progress bar** with percentage and current item name
- **Stats:** processed count, total, images warmed, errors
- **ETA:** estimated time remaining
- **Speed:** items per second
- **Activity log:** scrolling log of warm operations

### Buttons

| Button | What it does |
|--------|-------------|
| **Warm Movies** | Triggers `POST /warm/movies` (requires Radarr configured) |
| **Warm Shows** | Triggers `POST /warm/shows` (requires Sonarr configured) |
| **Warm All** | Triggers `POST /warm/all` (everything) |

## Warm Calendar

Open: `http://METACACHE_IP:8765/ui/warm-calendar`

Shows:
- Current warm status (Running/Idle)
- Last run summary (source, items, images, elapsed)
- Schedule time (nightly warm)
- History of recent warm runs
- Quick-trigger buttons

## Dashboard Warm Tab

The main [Dashboard](http://METACACHE_IP:8765/dashboard) has a **Warm** tab with:
- Warm trigger buttons
- Live status indicator (pulsing dot when running)
- Last run result card
- Activity log

## API Reference

### Check warm status

```bash
curl http://localhost:8765/warm/status
```

### Check warm progress (real-time)

```bash
curl http://localhost:8765/warm/progress
```

Returns:
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

### Trigger warm

```bash
# Warm everything
curl -X POST http://localhost:8765/warm/all

# Warm movies only
curl -X POST http://localhost:8765/warm/movies

# Warm shows only
curl -X POST http://localhost:8765/warm/shows
```

Returns 409 if another warm is already running.

## Nightly Scheduled Warm

By default, Metacache runs `/warm/all` at 03:00. Configure:

```bash
Metacache__Warm__ScheduleTime=04:30  # Run at 4:30 AM
Metacache__Warm__Enabled=false       # Disable scheduled warm
```

## Event-Driven Warm

Configure webhooks so warm runs automatically on import:

**Radarr:** `POST http://METACACHE:8765/webhook/radarr`
**Sonarr:** `POST http://METACACHE:8765/webhook/sonarr`
**Plex:** `POST http://METACACHE:8765/webhook/plex` (predictive warm on playback start)

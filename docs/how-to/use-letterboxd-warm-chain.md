# How to: Use Letterboxd Warm Chain

> Trigger Metacache warm after Letterboxd list sync adds movies.

## Overview

When movies are added to Radarr from a Letterboxd list, the control panel automatically triggers Metacache to warm those titles.

## Configuration

### Step 1: Set Environment Variables

Add to `.env`:

```bash
METACACHE_URL=http://metacache:8765
METACACHE_API_KEY=changeme  # Optional, for protected endpoints
```

### Step 2: Restart Control Panel

```bash
docker compose restart control-panel
```

## How It Works

1. Letterboxd list sync runs
2. Movies are added to Radarr
3. Control panel calls `POST /warm/movies` on Metacache
4. Metacache fetches metadata for new movies
5. Cache is ready before Plex refresh

## Verification

### Check Control Panel Logs

```bash
docker compose logs control-panel | grep metacache
```

### Check Metacache Logs

```bash
docker compose logs metacache | grep warm
```

### Check Cache

```bash
curl http://localhost:8765/items | jq '.[].title'
```

## Manual Trigger

To manually trigger warm after Letterboxd sync:

```bash
curl -X POST http://localhost:8765/warm/movies
```

## Troubleshooting

**Warm not triggering**
- Check METACACHE_URL is set in .env
- Verify control panel can reach Metacache: `docker exec control-panel curl http://metacache:8765/healthz`
- Check control panel logs: `docker compose logs control-panel`

**Movies not warming**
- Check Metacache logs: `docker compose logs metacache`
- Verify movies have TMDB IDs in Radarr
- Check Metacache is healthy: `curl http://localhost:8765/healthz`

**Slow warming**
- Check upstream API rate limits
- Reduce concurrent requests in Metacache config
- Monitor with Prometheus: `rate(metacache_warm_items_total[5m])`

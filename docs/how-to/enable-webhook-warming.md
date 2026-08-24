# How to: Enable Webhook Warming

> Auto-warm Metacache when new content is imported via Plex, Radarr, or Sonarr.

Metacache can automatically warm its cache when new content is imported. This ensures metadata and artwork are ready before Plex's next library refresh.

## Overview

There are three warming triggers:

1. **Plex Webhook** — Fires on `library.new` events (new imports)
2. **Radarr Webhook** — Fires on movie downloads
3. **Sonarr Webhook** — Fires on episode downloads

## Step 1: Configure Metacache URL

Add to your `.env` file:

```bash
METACACHE_URL=http://metacache:8765
METACACHE_API_KEY=changeme  # Optional, for protected endpoints
```

## Step 2: Enable Plex Webhook

### Option A: Via Plex Web App (Recommended)

1. Open Plex Web App
2. Go to Settings > Webhooks
3. Click "Add Webhook"
4. Enter URL: `http://127.0.0.1:9880/plex-webhook`
5. Save

**Note:** This requires Plex Pass. The webhook listener runs on the host at port 9880.

### Option B: Via Plex API

```bash
curl -X POST "http://localhost:32400/api/v2/webhooks" \
  -H "X-Plex-Token: $PLEX_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Metacache", "url": "http://127.0.0.1:9880/plex-webhook"}'
```

## Step 3: Enable Radarr Webhook

1. Open Radarr Web UI
2. Go to Settings > Connect
3. Click "+" to add a new connection
4. Select "Webhook"
5. Configure:
   - **Name**: Metacache
   - **URL**: http://metacache:8765/webhook/radarr
   - **Method**: POST
6. Save

## Step 4: Enable Sonarr Webhook

1. Open Sonarr Web UI
2. Go to Settings > Connect
3. Click "+" to add a new connection
4. Select "Webhook"
5. Configure:
   - **Name**: Metacache
   - **URL**: http://metacache:8765/webhook/sonarr
   - **Method**: POST
6. Save

## Step 5: Verify Webhooks

Test the Radarr webhook:

```bash
curl -X POST http://localhost:8765/webhook/radarr \
  -H "Content-Type: application/json" \
  -d '{"eventType": "Test"}'
```

Expected response: `{"status": "ok"}`

## Step 6: Test with Real Import

1. Add a movie to Radarr
2. Wait for download to complete
3. Check Metacache logs: `docker compose logs metacache`
4. Verify the item is cached: `curl http://localhost:8765/items?q=movie-title`

## How It Works

When a webhook fires:

1. Metacache receives the payload
2. It extracts the TMDB/TVDB ID
3. It fetches metadata from upstream providers
4. It stores the metadata in the local cache
5. Plex can now read from the fast local cache

## Troubleshooting

**Webhook not firing**
- Check Radarr/Sonarr logs for webhook errors
- Verify the URL is correct (use container names for Docker network)
- Test with curl (see Step 5)

**Warm not happening**
- Check Metacache logs: `docker compose logs metacache`
- Verify METACACHE_URL is set in .env
- Check if Metacache is healthy: `curl http://localhost:8765/healthz`

**Items not appearing in cache**
- Wait a few seconds for the warm to complete
- Check the items endpoint: `curl http://localhost:8765/items`
- Verify the TMDB/TVDB ID is correct

See [Troubleshooting Guide](troubleshoot-common-issues.md) for more.

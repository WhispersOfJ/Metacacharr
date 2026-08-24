# Tutorial: First-Time Setup

> Deploy the complete Metacacharr stack from scratch in about 30 minutes.

This tutorial walks you through deploying the unified Metacacharr stack, which combines Metacache (metadata cache) with Media-Stack (media acquisition and serving).

## Prerequisites

- Docker and Docker Compose installed
- A Plex Media Server account with Plex Pass (for webhooks)
- TMDB API key (free signup at https://www.themoviedb.org/settings/api)
- TVDB API key (optional, for TV metadata fallback)
- Usenet provider account (optional, for content acquisition)

## Step 1: Clone the Repository

```bash
git clone https://github.com/WhispersOfJ/Metacacharr.git
cd Metacacharr
```

## Step 2: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
# Required
PUID=1000
PGID=1000
TZ=America/New_York
HOST_IP=192.168.4.20  # Your server's IP

# Plex
PLEX_URL=http://192.168.4.20:32400
PLEX_TOKEN=your-plex-token

# API Keys
TMDB_KEY=your-tmdb-api-key
TVDB_KEY=your-tvdb-api-key  # Optional

# *arr Apps (get from each app's Settings > General > Security)
RADARR_API_KEY=your-radarr-api-key
SONARR_API_KEY=your-sonarr-api-key
PROWLARR_API_KEY=your-prowlarr-api-key
```

## Step 3: Start the Stack

```bash
docker compose up -d
```

This starts all 20+ services including:
- Metacache (metadata cache)
- Plex (media server)
- Radarr/Sonarr (media management)
- Prowlarr (indexer)
- NzbDAV (Usenet streaming)
- Prometheus/Grafana (monitoring)

## Step 4: Verify Services

```bash
# Check all services are healthy
docker ps --format "table {{.Names}}\t{{.Status}}"

# Test Metacache health
curl http://localhost:8765/healthz

# Test Radarr connection
curl http://localhost:7878/api/v3/system/status -H "X-Api-Key: $RADARR_API_KEY"
```

## Step 5: Register Metacache in Plex

1. Open Plex Web App
2. Go to Settings > Manage > Libraries
3. For each library, click "Edit" > "Advanced"
4. Under "Metadata Providers", add:
   - **Name**: Metacache
   - **URI**: http://192.168.4.20:8765

See [Connect Plex Providers](02-connect-plex-providers.md) for detailed instructions.

## Step 6: Warm Your Cache

```bash
# Warm movies
curl -X POST http://localhost:8765/warm/movies

# Warm TV shows
curl -X POST http://localhost:8765/warm/shows

# Or warm everything
curl -X POST http://localhost:8765/warm/all
```

## Step 7: Access Dashboards

| Service | URL |
|---------|-----|
| Metacache Dashboard | http://localhost:8765/dashboard |
| Control Panel | http://localhost:8420 |
| Grafana | http://localhost:3001 |
| Prometheus | http://localhost:9090 |

## Next Steps

- [Connect Plex Providers](02-connect-plex-providers.md) — Register Metacache as metadata provider
- [Enable Webhook Warming](../how-to/enable-webhook-warming.md) — Auto-warm on new imports
- [Configure Monitoring](04-monitor-with-grafana.md) — Set up dashboards and alerts

## Troubleshooting

If services don't start:
1. Check logs: `docker compose logs <service-name>`
2. Verify `.env` values are correct
3. Ensure ports are not in use: `netstat -tlnp | grep -E '8765|7878|8989|32400'`
4. See [Troubleshooting Guide](../how-to/troubleshoot-common-issues.md)

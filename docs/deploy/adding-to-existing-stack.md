# Deploy: Adding to Existing Stack

> Step-by-step guide to add Metacache to your running media-stack.

## Overview

This guide walks you through adding Metacache to an existing media-stack without disrupting your current services.

## Prerequisites

- Running media-stack with Docker Compose
- TMDB API key (free signup at https://www.themoviedb.org/settings/api)

## Step 1: Stop the Stack

```bash
cd ~/Claude/media-stack
docker compose down
```

## Step 2: Add Metacache Service

Edit `docker-compose.yml` and add before the `volumes:` section:

```yaml
  # ---------------------------------------------------------------------
  # Metacache - Custom Metadata Provider + Cache
  # ---------------------------------------------------------------------
  metacache:
    build:
      context: /path/to/metacache  # Adjust to your metacache path
      dockerfile: Dockerfile
    container_name: metacache
    networks: [stacknet]
    restart: unless-stopped
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    environment:
      TZ: ${TZ}
      Metacache__BindAddress: "0.0.0.0"
      Metacache__Port: "8765"
      Metacache__DataPath: "/app/data/metacache.db"
      Metacache__Upstream__BaseUrl: "https://api.themoviedb.org/3"
      Metacache__Upstream__ImageBaseUrl: "https://image.tmdb.org"
      Metacache__Tvdb__BaseUrl: "https://api.thetvdb.com"
      Metacache__Tvdb__ApiKey: ${TVDB_KEY:-}
      Metacache__Radarr__Url: "http://radarr:7878"
      Metacache__Radarr__ApiKey: ${RADARR_API_KEY:-}
      Metacache__Sonarr__Url: "http://sonarr:8989"
      Metacache__Sonarr__ApiKey: ${SONARR_API_KEY:-}
      Metacache__Warm__Languages__0: ${WARM_LANG_0:-en-US}
      Metacache__Auth__ApiKey: ${METACACHE_API_KEY:-}
    volumes:
      - metacache-data:/app/data
    ports:
      - "8765:8765"
    mem_limit: 1g
    mem_reservation: 256m
    cpus: 2
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:8765/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

Add the volume to `volumes:`:

```yaml
volumes:
  loki_data:
  metacache-data:
```

## Step 3: Add to Prometheus

Edit `config/prometheus/prometheus.yml`:

```yaml
  # Metacache - Custom Metadata Provider
  - job_name: "metacache"
    metrics_path: "/metrics/prometheus"
    static_configs:
      - targets: ["metacache:8765"]
```

## Step 4: Update Environment

Add to `.env`:

```bash
# Metacache
METACACHE_URL=http://metacache:8765
METACACHE_API_KEY=changeme
WARM_LANG_0=en-US
```

## Step 5: Fix Volume Permissions

```bash
docker volume create media-stack_metacache-data
docker run --rm -v media-stack_metacache-data:/data alpine chown -R 1654:1654 /data
```

## Step 6: Start Services

```bash
docker compose up -d metacache
```

## Step 7: Verify

```bash
# Check health
curl http://localhost:8765/healthz

# Check Prometheus
curl http://localhost:9090/api/v1/targets | grep metacache
```

## Step 8: Register in Plex

1. Open Plex Web App
2. Settings > Manage > Libraries
3. Edit each library > Advanced
4. Add Metadata Provider:
   - **Name**: Metacache
   - **URI**: http://192.168.4.20:8765

## Step 9: Warm Cache

```bash
curl -X POST http://localhost:8765/warm/all
```

## Optional: Enable Webhook Warming

See [Enable Webhook Warming](../how-to/enable-webhook-warming.md).

## Troubleshooting

**Metacache won't start**
- Check volume permissions (Step 5)
- Check logs: `docker compose logs metacache`

**Health check fails**
- Ensure curl is in the Docker image
- Check if port 8765 is in use

**Prometheus can't scrape**
- Verify metacache is on stacknet: `docker network inspect media-stack_stacknet`
- Check prometheus.yml syntax

See [Troubleshooting Guide](../how-to/troubleshoot-common-issues.md).

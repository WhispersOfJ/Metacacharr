# Tutorial: Add Metacache to Existing Stack

> Add Metacache to your running media-stack in 10 minutes.

If you already have a media-stack running, you can add Metacache without disrupting your existing services.

## Prerequisites

- Existing media-stack running with Docker Compose
- TMDB API key (free signup at https://www.themoviedb.org/settings/api)

## Step 1: Stop the Existing Stack

```bash
cd ~/Claude/media-stack
docker compose down
```

## Step 2: Add Metacache Service

Edit `docker-compose.yml` and add the metacache service before the `volumes:` section:

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

Add the volume to the `volumes:` section:

```yaml
volumes:
  loki_data:
  metacache-data:
```

## Step 3: Add Metacache to Prometheus

Edit `config/prometheus/prometheus.yml` and add:

```yaml
  # Metacache - Custom Metadata Provider
  - job_name: "metacache"
    metrics_path: "/metrics/prometheus"
    static_configs:
      - targets: ["metacache:8765"]
```

## Step 4: Update Environment Variables

Add to `.env`:

```bash
# Metacache
METACACHE_URL=http://metacache:8765
METACACHE_API_KEY=changeme
WARM_LANG_0=en-US
```

## Step 5: Fix Volume Permissions

The Metacache container runs as a non-root user (uid 1654). Fix the volume ownership:

```bash
docker volume create media-stack_metacache-data
docker run --rm -v media-stack_metacache-data:/data alpine chown -R 1654:1654 /data
```

## Step 6: Start the Stack

```bash
docker compose up -d
```

## Step 7: Verify Metacache

```bash
# Check health
curl http://localhost:8765/healthz

# Check Prometheus is scraping
curl http://localhost:9090/api/v1/targets | grep metacache
```

## Step 8: Register in Plex

1. Open Plex Web App
2. Go to Settings > Manage > Libraries
3. For each library, click "Edit" > "Advanced"
4. Under "Metadata Providers", add:
   - **Name**: Metacache
   - **URI**: http://192.168.4.20:8765

## Step 9: Warm Your Cache

```bash
curl -X POST http://localhost:8765/warm/all
```

## Optional: Enable Webhook Warming

To auto-warm when new content is imported, see [Enable Webhook Warming](../how-to/enable-webhook-warming.md).

## Troubleshooting

**Metacache won't start (exit code 139)**
- Fix volume permissions: `docker run --rm -v media-stack_metacache-data:/data alpine chown -R 1654:1654 /data`

**Health check fails**
- Ensure curl is installed in the Docker image (see Dockerfile)
- Check logs: `docker compose logs metacache`

**Prometheus can't scrape Metacache**
- Verify metacache service is on the same network: `docker network inspect media-stack_stacknet`
- Check prometheus.yml has the correct target

See [Troubleshooting Guide](../how-to/troubleshoot-common-issues.md) for more.

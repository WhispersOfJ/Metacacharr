# How to: Add Metacache Service

> Add the Metacache service to your docker-compose.yml.

## Step 1: Add Service Definition

Add before the `volumes:` section in `docker-compose.yml`:

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

## Step 2: Add Volume

Add to `volumes:` section:

```yaml
volumes:
  loki_data:
  metacache-data:
```

## Step 3: Update Context Path

Adjust `context:` to your metacache location:

```yaml
build:
  context: /home/user/Projects/metacache
  dockerfile: Dockerfile
```

## Step 4: Add Environment Variables

Add to `.env`:

```bash
METACACHE_URL=http://metacache:8765
METACACHE_API_KEY=changeme
WARM_LANG_0=en-US
```

## Step 5: Fix Permissions

```bash
docker volume create media-stack_metacache-data
docker run --rm -v media-stack_metacache-data:/data alpine chown -R 1654:1654 /data
```

## Step 6: Start Service

```bash
docker compose up -d metacache
```

## Step 7: Verify

```bash
# Check health
curl http://localhost:8765/healthz

# Check logs
docker compose logs metacache
```

## Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `Metacache__BindAddress` | `0.0.0.0` | Listen address |
| `Metacache__Port` | `8765` | Listen port |
| `Metacache__DataPath` | `/app/data/metacache.db` | SQLite database path |
| `Metacache__Radarr__Url` | — | Radarr API URL |
| `Metacache__Sonarr__Url` | — | Sonarr API URL |
| `Metacache__Tvdb__ApiKey` | — | TVDB API key |

## Troubleshooting

**Build fails**
- Check metacache path is correct
- Verify Dockerfile exists at that path
- Check Docker build context

**Port conflict**
- Check if port 8765 is in use: `netstat -tlnp | grep 8765`
- Change port mapping if needed

**Volume permission denied**
- Fix permissions (Step 5)
- Check container logs: `docker compose logs metacache`

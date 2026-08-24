# How to: Troubleshoot Common Issues

> Solutions for the most common Metacacharr problems.

## Metacache Issues

### Metacache won't start (exit code 139)

**Symptoms**: Container restarts repeatedly with exit code 139

**Cause**: Volume permissions mismatch

**Solution**:
```bash
docker compose stop metacache
docker run --rm -v media-stack_metacache-data:/data alpine chown -R 1654:1654 /data
docker compose start metacache
```

### Health check fails

**Symptoms**: Container shows "unhealthy" status

**Cause**: curl not installed in Docker image

**Solution**:
1. Add curl to Dockerfile:
```dockerfile
FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
```

2. Rebuild:
```bash
docker compose build metacache
docker compose up -d metacache
```

### SQLite Error 14: 'unable to open database file'

**Symptoms**: Metacache logs show SQLite error

**Cause**: DataPath misconfigured or volume not mounted

**Solution**:
1. Verify DataPath in docker-compose.yml:
```yaml
Metacache__DataPath: "/app/data/metacache.db"
```

2. Check volume mount:
```bash
docker volume inspect media-stack_metacache-data
```

3. Fix permissions (see above)

### Can't reach Radarr/Sonarr from Metacache

**Symptoms**: Metacache logs show connection errors

**Cause**: Services not on same network

**Solution**:
```bash
# Check network
docker network inspect media-stack_stacknet

# Test connectivity
docker exec metacache curl http://radarr:7878/ping
```

## Prometheus Issues

### Prometheus keeps restarting

**Symptoms**: Container shows "Restarting" status

**Cause**: Volume permissions or missing config

**Solution**:
```bash
# Fix permissions
docker compose stop prometheus
sudo chown -R 65534:65534 ./data/prometheus
docker compose start prometheus
```

### Targets showing "down"

**Symptoms**: Prometheus targets page shows targets as down

**Cause**: Network connectivity or configuration error

**Solution**:
1. Check target configuration:
```bash
curl http://localhost:9090/api/v1/targets | python3 -m json.tool
```

2. Test target manually:
```bash
curl http://metacache:8765/metrics/prometheus
```

3. Check network:
```bash
docker network inspect media-stack_stacknet
```

### No metrics from Metacache

**Symptoms**: Prometheus shows no metacache metrics

**Cause**: Scrape configuration missing or wrong path

**Solution**:
1. Verify prometheus.yml:
```yaml
- job_name: "metacache"
  metrics_path: "/metrics/prometheus"
  static_configs:
    - targets: ["metacache:8765"]
```

2. Reload Prometheus:
```bash
curl -X POST http://localhost:9090/-/reload
```

## Plex Issues

### Plex can't find Metacache provider

**Symptoms**: Plex doesn't show Metacache in metadata providers

**Cause**: Provider not registered or wrong URI

**Solution**:
1. Register provider:
   - Settings > Manage > Libraries > Edit > Advanced
   - Add Metadata Provider: `http://192.168.4.20:8765`

2. Verify Metacache is accessible:
```bash
curl http://localhost:8765/healthz
```

### Metadata not updating

**Symptoms**: Plex shows old metadata

**Cause**: Cache not warmed or provider not configured

**Solution**:
```bash
# Warm cache
curl -X POST http://localhost:8765/warm/all

# Refresh Plex library
curl "http://localhost:32400/library/sections/1/refresh" -H "X-Plex-Token: $PLEX_TOKEN"
```

## Network Issues

### Services can't communicate

**Symptoms**: Connection refused errors between services

**Cause**: Services not on same Docker network

**Solution**:
```bash
# Check all services are on stacknet
docker network inspect media-stack_stacknet | grep -A 5 "Containers"

# Restart network if needed
docker compose down
docker compose up -d
```

### DNS resolution fails

**Symptoms**: "No such host" errors

**Cause**: Docker DNS not working

**Solution**:
```bash
# Test DNS from container
docker exec metacache nslookup radarr

# Restart Docker daemon if needed
sudo systemctl restart docker
```

## Logging

### View service logs

```bash
# Real-time logs
docker compose logs -f metacache

# Last 100 lines
docker compose logs --tail 100 metacache

# All services
docker compose logs
```

### Query Loki logs

```bash
# In Grafana, go to Explore > Loki
# Query: {container_name="metacache"}
# Errors: {container_name="metacache"} |= "error"
```

## Getting Help

If these solutions don't work:

1. Check logs for specific error messages
2. Verify all environment variables in `.env`
3. Ensure all services are on the same network
4. Check Docker Compose syntax: `docker compose config`
5. Open an issue on GitHub with logs and configuration

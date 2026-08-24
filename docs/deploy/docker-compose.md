# Deploy with Docker Compose

> Full stack deployment with Prometheus + Grafana monitoring.

## Quick Start

```bash
cd monitoring/

# Configure
cp .env.example .env
# Edit .env: set TMDB_API_KEY, Radarr/Sonarr URLs + keys

# Start
docker compose up -d --build

# Open
# Metacache:  http://localhost:8765
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000 (admin / GRAFANA_ADMIN_PASSWORD)
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| `metacache` | 8765 (provider) + 443 (proxy) | Metadata cache |
| `prometheus` | 9090 | Metrics scraping |
| `grafana` | 3000 | Dashboard + alerts |

## Configuration

### Environment Variables

Create `monitoring/.env`:

```bash
# Required
TMDB_API_KEY=your-tmdb-token

# ARR sources (optional)
RADARR_URL=http://host.docker.internal:7878
RADARR_API_KEY=your-radarr-key
SONARR_URL=http://host.docker.internal:8989
SONARR_API_KEY=your-sonarr-key

# Grafana
GRAFANA_ADMIN_PASSWORD=your-secure-password
```

### Docker Compose File

The compose file (`monitoring/docker-compose.yml`) includes:

- **Metacache** with host networking
- **Prometheus** scraping `/metrics/prometheus` every 15s
- **Grafana** with auto-provisioned datasource + dashboard
- Alerting rules loaded from `metacache-alerts.yml`

## Volumes

```yaml
volumes:
  metacache-data:   # SQLite database + images
  prometheus-data:  # Prometheus time series
  grafana-data:     # Grafana dashboards + config
```

## Monitoring Stack

### Prometheus

Scrapes Metacache every 15 seconds. Configuration: `monitoring/prometheus.yml`.

View targets: http://localhost:9090/targets

### Alerting Rules

Loaded from `monitoring/metacache-alerts.yml`:

| Alert | Condition | Severity |
|-------|-----------|----------|
| `MetacacheDown` | Target unreachable 1min | critical |
| `MetacacheLowHitRate` | Hit rate < 80% for 5min | warning |
| `MetacacheHighDiskUsage` | Image disk > 8GB | warning |
| `MetacacheWarmFailed` | Warm errors > 0 | warning |
| `MetacacheRateLimited` | TMDB 429 responses | info |

### Grafana Dashboard

Pre-provisioned with 10 panels:
1. Hit rate (live)
2. Requests total
3. Cache hits vs misses
4. Items by kind
5. Upstream latency p50/p95
6. Image disk usage
7. Warm status
8. TMDB rate-limit remaining
9. Request duration histogram
10. Error rate

## Common Operations

### View logs

```bash
docker compose -f monitoring/docker-compose.yml logs -f metacache
```

### Restart

```bash
docker compose -f monitoring/docker-compose.yml restart metacache
```

### Stop

```bash
docker compose -f monitoring/docker-compose.yml down
```

### Stop and remove data

```bash
docker compose -f monitoring/docker-compose.yml down -v
```

## Troubleshooting

**Grafana shows "No data":**
- Check Prometheus: http://localhost:9090/targets (should be "UP")
- Verify Metacache: `curl http://localhost:8765/healthz`

**Prometheus can't reach Metacache:**
- Use `host.docker.internal` instead of `localhost` (Docker networking)
- Or use `network_mode: host` for Metacache

**Alerts not firing:**
- Check Prometheus rules: http://localhost:9090/alerts
- Verify rules file is mounted correctly

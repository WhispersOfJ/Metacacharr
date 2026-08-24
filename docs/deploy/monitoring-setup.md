# Deploy: Monitoring Setup

> Configure Prometheus and Grafana to monitor Metacache and the media-stack.

## Overview

Metacacharr includes a complete monitoring stack:
- **Prometheus** — Collects metrics from all services
- **Grafana** — Visualizes metrics with dashboards
- **Loki** — Aggregates logs from all containers
- **Promtail** — Ships logs to Loki

## Step 1: Verify Prometheus Configuration

Edit `config/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  scrape_timeout: 10s

scrape_configs:
  # Prometheus self-monitoring
  - job_name: "prometheus"
    static_configs:
      - targets: ["localhost:9090"]

  # Metacache - Custom Metadata Provider
  - job_name: "metacache"
    metrics_path: "/metrics/prometheus"
    static_configs:
      - targets: ["metacache:8765"]

  # NzbDAV streaming metrics
  - job_name: "nzbdav-exporter"
    static_configs:
      - targets: ["nzbdav-exporter:9200"]

  # Host metrics via node-exporter
  - job_name: "node-exporter"
    static_configs:
      - targets: ["host.docker.internal:9100"]

  # Container metrics via cAdvisor
  - job_name: "cadvisor"
    static_configs:
      - targets: ["cadvisor:8080"]
```

## Step 2: Start Monitoring Services

```bash
docker compose up -d prometheus grafana loki promtail
```

## Step 3: Fix Prometheus Permissions

Prometheus runs as nobody (uid 65534). Fix the data directory:

```bash
docker compose stop prometheus
sudo chown -R 65534:65534 ./data/prometheus
docker compose start prometheus
```

## Step 4: Import Grafana Dashboards

Metacache includes pre-built dashboards:

```bash
# Copy dashboards to Grafana provisioning
cp -r metacache/monitoring/grafana/dashboards/* config/grafana/dashboards/
```

## Step 5: Access Dashboards

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3001 | admin / media-stack-logging-secure-2026 |
| Prometheus | http://localhost:9090 | — |

## Metacache Metrics

Metacache exposes Prometheus metrics at `/metrics/prometheus`:

### Key Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `metacache_cache_hits_total` | Counter | Total cache hits |
| `metacache_cache_misses_total` | Counter | Total cache misses |
| `metacache_upstream_requests_total` | Counter | Total upstream requests |
| `metacache_upstream_duration_seconds` | Histogram | Upstream request duration |
| `metacache_warm_items_total` | Counter | Total items warmed |
| `metacache_warm_duration_seconds` | Histogram | Warm operation duration |

### Example Queries

```promql
# Cache hit rate
rate(metacache_cache_hits_total[5m]) / rate(metacache_cache_hits_total[5m] + metacache_cache_misses_total[5m])

# Upstream request rate
rate(metacache_upstream_requests_total[5m])

# Warm items per minute
rate(metacache_warm_items_total[5m]) * 60
```

## Grafana Dashboard

The Metacache dashboard shows:

- **Cache Hit Rate** — Percentage of requests served from cache
- **Upstream Requests** — Requests to TMDB/TVDB per minute
- **Warm Progress** — Items warmed over time
- **Error Rate** — Failed requests

## Loki Log Aggregation

Logs from all containers are shipped to Loki:

```bash
# Query logs in Grafana
{container_name="metacache"}

# Query errors
{container_name="metacache"} |= "error"

# Query by service
{job="metacache"}
```

## Alerting

### Prometheus Alerts

Create `config/prometheus/alerts.yml`:

```yaml
groups:
  - name: metacache
    rules:
      - alert: MetacacheDown
        expr: up{job="metacache"} == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Metacache is down"
          
      - alert: HighErrorRate
        expr: rate(metacache_upstream_errors_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate on Metacache upstream requests"
```

### Grafana Alerts

Configure in Grafana UI:
1. Alerting > Alert Rules
2. Create new rule
3. Set condition (e.g., cache hit rate < 80%)
4. Configure notification channel

## Troubleshooting

**Prometheus can't scrape Metacache**
- Check metacache is on stacknet: `docker network inspect media-stack_stacknet`
- Verify metrics endpoint: `curl http://localhost:8765/metrics/prometheus`

**Grafana dashboards not showing data**
- Check Prometheus data source is configured
- Verify Prometheus is scraping targets: `curl http://localhost:9090/api/v1/targets`

**Loki not receiving logs**
- Check Promtail is running: `docker compose logs promtail`
- Verify Loki is healthy: `curl http://localhost:3100/ready`

See [Troubleshooting Guide](../how-to/troubleshoot-common-issues.md).

# Tutorial: Monitoring Stack

> **Goal:** Deploy Metacache with Prometheus metrics and Grafana dashboards using Docker Compose.
>
> **Time:** ~10 minutes
>
> **Prerequisites:** Docker and Docker Compose installed

## What You Get

- **Metacache** on port 8765 (provider + admin + dashboard)
- **Prometheus** on port 9090 (scraping `/metrics/prometheus` every 15s)
- **Grafana** on port 3000 (pre-wired dashboard with 10 panels)
- **Alerting rules** for host-down, low hit-rate, disk usage, warm failures

## Quick Start

```bash
cd monitoring/

# Copy and edit the env file
cp .env.example .env
# Edit .env and set your TMDB API key

# Start the stack
docker compose up -d --build

# Open Grafana
open http://localhost:3000
# Login: admin / GRAFANA_ADMIN_PASSWORD (from .env)
```

## What's in the Stack

### Prometheus

Scrapes Metacache's `/metrics/prometheus` endpoint every 15 seconds. Configuration: `monitoring/prometheus.yml`.

### Alerting Rules

Defined in `monitoring/metacache-alerts.yml`:

| Alert | Condition | Severity |
|-------|-----------|----------|
| `MetacacheDown` | Target unreachable for 1 minute | critical |
| `MetacacheLowHitRate` | Hit rate < 80% for 5 minutes | warning |
| `MetacacheHighDiskUsage` | Image disk > 8 GB | warning |
| `MetacacheWarmFailed` | Warm errors > 0 | warning |
| `MetacacheRateLimited` | TMDB 429 responses detected | info |

### Grafana Dashboard

Pre-provisioned with 10 panels:

1. Hit rate (live)
2. Requests (total)
3. Cache hits vs misses
4. Items by kind (movie/show/season/episode)
5. Upstream latency p50/p95 per provider
6. Image disk usage
7. Warm status (last run)
8. TMDB rate-limit remaining
9. Request duration histogram
10. Error rate

## Customization

### Change Grafana password

Edit `monitoring/.env`:
```
GRAFANA_ADMIN_PASSWORD=your-secure-password
```

### Add alert receivers

Edit `monitoring/metacache-alerts.yml` to add email/Slack/PagerDuty receivers under `alertmanager` config.

### Change scrape interval

Edit `monitoring/prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'metacache'
    scrape_interval: 30s  # Default: 15s
```

## Troubleshooting

**Grafana shows "No data":**
- Check Prometheus targets: http://localhost:9090/targets
- Verify Metacache is running: `curl http://localhost:8765/healthz`

**Prometheus can't reach Metacache:**
- If using Docker networking, use the service name: `http://metacache:8765`
- If using `--network host`, use `http://localhost:8765`

**Alerts not firing:**
- Check Prometheus rules: http://localhost:9090/alerts
- Verify the rules file is loaded: look for "metacache" in the rules list

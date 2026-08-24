# How to: Update Prometheus Scrape Configuration

> Add Metacache to Prometheus scrape targets.

## Step 1: Edit prometheus.yml

Edit `config/prometheus/prometheus.yml` and add:

```yaml
  # Metacache - Custom Metadata Provider
  - job_name: "metacache"
    metrics_path: "/metrics/prometheus"
    static_configs:
      - targets: ["metacache:8765"]
```

## Step 2: Reload Prometheus

```bash
curl -X POST http://localhost:9090/-/reload
```

Or restart:

```bash
docker compose restart prometheus
```

## Step 3: Verify

```bash
# Check targets
curl http://localhost:9090/api/v1/targets | grep metacache

# Test metrics endpoint
curl http://localhost:8765/metrics/prometheus
```

## Configuration Options

| Option | Value | Description |
|--------|-------|-------------|
| `job_name` | `metacache` | Prometheus job name |
| `metrics_path` | `/metrics/prometheus` | Metacache metrics endpoint |
| `static_configs.targets` | `["metacache:8765"]` | Container name and port |

## Troubleshooting

**Target shows "down"**
- Check Metacache is running: `docker compose ps metacache`
- Verify network: `docker network inspect media-stack_stacknet`
- Test metrics manually: `curl http://metacache:8765/metrics/prometheus`

**No metrics appearing**
- Check Metacache logs: `docker compose logs metacache`
- Verify metrics endpoint: `curl http://localhost:8765/metrics/prometheus`
- Check Prometheus config syntax: `docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml`

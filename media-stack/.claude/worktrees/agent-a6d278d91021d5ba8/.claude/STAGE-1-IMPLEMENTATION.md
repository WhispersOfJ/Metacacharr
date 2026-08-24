# Stage 1 Implementation: Centralized Logging (Loki + Grafana + Promtail)

**Timeline:** 2 weeks  
**Risk:** Low (read-only logs, non-blocking)  
**Testing:** Straightforward (query logs via API/UI)  
**Rollback:** 5 minutes (delete containers, revert compose)

---

## Architecture

```
Docker Containers (all services)
         ↓
  Docker daemon (json-file logs)
         ↓ (also kept as redundant fallback)
  Promtail (log collector, scrapes docker socket)
         ↓
  Loki (log aggregation + storage, 30-day retention)
         ↓
  Grafana (search UI + dashboards + alerts)
         ↓
  Discord webhook (SLA alerts: errors, crashes, slow imports)
```

**Data flow:**
- Every container logs to docker json-file driver (kept as backup)
- Promtail reads those logs in real-time
- Loki deduplicates + indexes + stores (30 days = ~500MB disk)
- Grafana queries Loki for visualization + alerting
- Discord gets notified on CRITICAL events

---

## Week 1: Setup & Deployment

### Step 1: Create Configuration Files

#### 1.1 Loki Config

```bash
mkdir -p ./config/loki
```

**File:** `./config/loki/loki-config.yaml`

```yaml
auth_enabled: false

ingester:
  chunk_idle_period: 3m
  max_chunk_age: 1h
  max_streams_limit: 10000
  chunk_retain_period: 1m
  max_chunk_age: 200m

limits_config:
  enforce_metric_name: false
  reject_old_samples: true
  reject_old_samples_max_age: 168h
  ingestion_rate_mb: 100
  ingestion_burst_size_mb: 200
  retention_period: 720h  # 30 days

schema_config:
  configs:
    - from: 2026-01-01
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  filesystem:
    directory: /loki/chunks
  boltdb_shipper:
    active_index_directory: /loki/index
    shared_store: filesystem
  index_cache_validity: 5m

chunk_store_config:
  max_look_back_period: 0s

table_manager:
  retention_deletes_enabled: false
  retention_period: 0s

server:
  http_listen_port: 3100
  log_level: info
```

#### 1.2 Promtail Config

```bash
mkdir -p ./config/promtail
```

**File:** `./config/promtail/promtail-config.yaml`

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  # Docker container logs
  - job_name: docker
    static_configs:
      - targets:
          - localhost
        labels:
          job: docker
          __path__: /var/lib/docker/containers/*/*-json.log

    pipeline_stages:
      # Parse JSON from docker's logging driver
      - json:
          expressions:
            output: log
            stream: stream
            attrs: attrs

      # Extract container name from attrs
      - regex:
          expression: '"name":"(?P<container>[^"]+)"'

      # Add container label
      - labels:
          container:
          stream:

      # Extract log level (ERROR, WARN, INFO, etc)
      - regex:
          expression: '(?i)(ERROR|WARN|INFO|DEBUG|TRACE)'
          action: keep

      # Output final log line
      - output:
          source: output
```

#### 1.3 Grafana Datasource

```bash
mkdir -p ./config/grafana/provisioning/datasources
```

**File:** `./config/grafana/provisioning/datasources/loki.yaml`

```yaml
apiVersion: 1

datasources:
  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    isDefault: true
    editable: true
    jsonData:
      maxLines: 1000
```

### Step 2: Update docker-compose.yml

Add these services to your `docker-compose.yml`:

```yaml
# At the bottom of the services section

  loki:
    restart: unless-stopped
    image: grafana/loki:latest@sha256:PLACEHOLDER  # Capture digest after first deploy
    container_name: loki
    ports:
      - "3100:3100"
    volumes:
      - ./config/loki/loki-config.yaml:/etc/loki/loki-config.yaml:ro
      - ./data/loki:/loki
    command: -config.file=/etc/loki/loki-config.yaml
    environment:
      TZ: ${TZ}
    networks: [stacknet]
    mem_limit: 1g
    mem_reservation: 256m
    cpus: 2
    ulimits: *common-ulimits
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:3100/ready"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  promtail:
    restart: unless-stopped
    image: grafana/promtail:latest@sha256:PLACEHOLDER  # Capture digest after first deploy
    container_name: promtail
    volumes:
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./config/promtail/promtail-config.yaml:/etc/promtail/config.yaml:ro
    command: -config.file=/etc/promtail/config.yaml
    environment:
      TZ: ${TZ}
    networks: [stacknet]
    mem_limit: 512m
    mem_reservation: 64m
    cpus: 1
    ulimits: *common-ulimits
    depends_on:
      loki:
        condition: service_healthy
        restart: true
    # No healthcheck needed (Loki dependency covers readiness)

  grafana:
    restart: unless-stopped
    image: grafana/grafana:latest@sha256:PLACEHOLDER  # Capture digest after first deploy
    container_name: grafana
    ports:
      - "3001:3000"
    volumes:
      - ./config/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./data/grafana:/var/lib/grafana
    environment:
      TZ: ${TZ}
      GF_SECURITY_ADMIN_USER: ${GRAFANA_ADMIN_USER:-admin}
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-password123}
      GF_USERS_ALLOW_SIGN_UP: "false"
      GF_INSTALL_PLUGINS: grafana-piechart-panel
    networks: [stacknet]
    mem_limit: 512m
    mem_reservation: 128m
    cpus: 1
    ulimits: *common-ulimits
    depends_on:
      loki:
        condition: service_healthy
        restart: true
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:3000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

### Step 3: Create Data Directories

```bash
mkdir -p ./data/loki ./data/grafana
chmod 777 ./data/loki ./data/grafana
```

### Step 4: Update .env

Add Grafana credentials:

```bash
# .env (add these lines)
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=your-secure-password-here
```

### Step 5: Deploy

```bash
docker compose down
docker compose up -d loki promtail grafana

# Wait for healthy (3-5 minutes)
sleep 30
docker compose ps

# Verify Loki is receiving logs
curl -s 'http://localhost:3100/loki/api/v1/label/job/values' | jq .
# Should return: ["docker"]
```

---

## Week 2: Verification & Dashboards

### Verification Checklist

```bash
# 1. Loki ready
curl http://localhost:3100/ready
# Expected: 200 OK

# 2. Promtail scraping
curl -s 'http://localhost:3100/loki/api/v1/label/container/values' | jq .
# Expected: list of container names (prowlarr, radarr, sonarr, etc)

# 3. Query logs
curl -G 'http://localhost:3100/loki/api/v1/query' \
  --data-urlencode 'query={job="docker"}' | jq .
# Expected: logs from all containers

# 4. Grafana UI
open http://localhost:3001
# Login: admin / your-password
# Add Loki data source: http://loki:3100
```

### Create Dashboards

**Dashboard 1: Stack Overview**

In Grafana UI:
1. Create → Dashboard
2. Add Panels:
   - Panel 1: "Error Rate (last hour)"
     ```
     sum(rate({job="docker"} |= "ERROR" [1h])) by (container)
     ```
   - Panel 2: "Container Restarts"
     ```
     sum(rate({job="docker"} |= "restarting" [1h])) by (container)
     ```
   - Panel 3: "All Logs"
     ```
     {job="docker"}
     ```

**Dashboard 2: Import Tracking (Radarr/Sonarr)**

```
# Panel: "Failed Imports (last 24h)"
sum(count_over_time({container=~"radarr|sonarr"} |= "failed" [24h])) by (container)

# Panel: "Import Success Rate"
(
  sum(count_over_time({container=~"radarr|sonarr"} |= "imported" [24h]))
  /
  sum(count_over_time({container=~"radarr|sonarr"} |= "import" [24h]))
) * 100

# Panel: "Import Duration (last 10)"
{container=~"radarr|sonarr"} |= "import" | json duration | line_format "{{.duration}}"
```

**Dashboard 3: NzbDAV Health**

```
# Panel: "NzbDAV Errors"
{container="nzbdav"} |= "error"

# Panel: "Mount Status"
{container="nzbdav_rclone"} |= "mounted"

# Panel: "FUSE Operations"
{container="nzbdav_rclone"} |= "stat\|read\|write"
```

### Configure Alerts

In Grafana UI:
1. Alerts → Notification channels → New channel
2. Type: Discord
3. URL: Your Discord webhook (from Control Panel alerts)
4. Name: "media-stack-alerts"

Then create alert rules:

**Alert 1: Service Down**
- Query: `{job="docker", container=~"radarr|sonarr|prowlarr|nzbdav"}` returns no logs for 5 minutes
- Severity: CRITICAL
- Notify: Discord
- Message: `"Service {{ $labels.container }} is down!"`

**Alert 2: High Error Rate**
- Query: `sum(rate({job="docker"} |= "ERROR" [5m])) > 10`
- Severity: WARNING
- Notify: Discord

**Alert 3: NzbDAV Unhealthy**
- Query: `{container="nzbdav"} |= "unhealthy"`
- Severity: CRITICAL
- Notify: Discord

---

## Troubleshooting

### "Promtail not sending logs"
```bash
# Check Promtail connection to Loki
docker logs promtail | grep -i "error\|refused"

# Verify docker.sock permissions
ls -la /var/run/docker.sock
# Should be readable by everyone (666 or similar)

# Test Promtail manually
docker exec promtail promtail -config.file=/etc/promtail/config.yaml -print-config-stderr
```

### "Grafana shows no data"
```bash
# 1. Verify Loki datasource in UI
# Settings → Data Sources → Loki → Test

# 2. Check Loki storage
ls -la ./data/loki/
# Should have chunks/ and index/ subdirectories

# 3. Query via CLI
curl -G 'http://localhost:3100/loki/api/v1/query' \
  --data-urlencode 'query={job="docker"}' | jq '.data.result | length'
# Should be > 0
```

### "Logs truncated or missing"
```bash
# Check Loki retention
curl http://localhost:3100/api/prom/label/job/values
# Returns label values (should be ["docker"])

# Check volume space
df -h ./data/loki/
# Should have room to grow (target: 500MB/month)
```

### "High memory usage"
```bash
# Loki default ingestion is 100MB/s (overkill for this stack)
# Edit ./config/loki/loki-config.yaml:
# ingestion_rate_mb: 10  (reduced from 100)
# ingestion_burst_size_mb: 20  (reduced from 200)

docker compose up -d loki
```

---

## Success Criteria

- [ ] All 3 containers healthy: `docker compose ps loki promtail grafana`
- [ ] Loki receiving logs: `curl 'http://localhost:3100/loki/api/v1/label/container/values'` returns container list
- [ ] Grafana UI accessible: `curl http://localhost:3001/api/health` returns 200
- [ ] Can query logs: Grafana → Explore → {job="docker"} returns results
- [ ] Dashboards created and showing data
- [ ] Discord alerts configured and tested
- [ ] 30-day retention confirmed: Grafana shows logs from multiple days ago

---

## What's Next After Stage 1

Once logging is stable (24 hours of data):
1. Document any patterns discovered (slow imports, recurring errors)
2. Fine-tune dashboard queries based on real data
3. Adjust alert thresholds to reduce false positives

Then decide on Stage 2 (Secrets) or Stage 4 (Scanning).

---

## Command Reference

```bash
# Deploy
docker compose up -d loki promtail grafana

# Verify health
docker compose ps loki promtail grafana

# View logs
docker logs loki
docker logs promtail

# Query logs via CLI
QUERY='{container="radarr"}'
curl -G 'http://localhost:3100/loki/api/v1/query' \
  --data-urlencode "query=$QUERY" | jq .

# Access UIs
Grafana:  http://localhost:3001 (admin/password)
Loki API: http://localhost:3100/ready

# Cleanup (if needed)
docker compose down -v loki promtail grafana
rm -rf ./config/loki ./config/promtail ./config/grafana ./data/loki ./data/grafana
```

---

## Disk Usage Estimate

- **Loki indexes:** ~50MB/month
- **Loki chunks:** ~450MB/month (depends on log volume)
- **Grafana config:** ~10MB
- **Total:** ~500MB/month

At 30-day retention, disk footprint stabilizes around 1-2GB total.

If concerned about disk usage:
- Reduce retention_period in Loki config (default: 720h = 30 days)
- Example: 360h = 15 days, ~1GB total

---

## Timeline

- **Day 1:** Create configs, deploy containers
- **Day 2:** Verify logs flowing, test queries
- **Day 3-7:** Create dashboards, tune alert thresholds
- **Week 2:** Monitor for stability, document findings

**Go-live:** Declare Stage 1 complete when dashboards are populated and alerts have been tested.

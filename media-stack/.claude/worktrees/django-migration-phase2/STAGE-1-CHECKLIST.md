# Stage 1 Quick Start Checklist

**Goal:** Deploy Loki + Promtail + Grafana in next 2 hours  
**Complexity:** Low (mostly copy-paste configs)  
**Testing:** Straightforward (verify logs in Grafana UI)

---

## TODAY (30 minutes to deploy)

### Create Config Directories
```bash
cd /home/bear/Claude/media-stack
mkdir -p ./config/loki ./config/promtail ./config/grafana/provisioning/datasources
mkdir -p ./data/loki ./data/grafana
chmod 777 ./data/loki ./data/grafana
```

### Copy Loki Config
```bash
# File: ./config/loki/loki-config.yaml
cat > ./config/loki/loki-config.yaml << 'EOF'
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
  retention_period: 720h

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
EOF

```

### Copy Promtail Config
```bash
# File: ./config/promtail/promtail-config.yaml
cat > ./config/promtail/promtail-config.yaml << 'EOF'
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: docker
    static_configs:
      - targets:
          - localhost
        labels:
          job: docker
          __path__: /var/lib/docker/containers/*/*-json.log

    pipeline_stages:
      - json:
          expressions:
            output: log
            stream: stream
            attrs: attrs
      - regex:
          expression: '"name":"(?P<container>[^"]+)"'
      - labels:
          container:
          stream:
      - regex:
          expression: '(?i)(ERROR|WARN|INFO|DEBUG|TRACE)'
          action: keep
      - output:
          source: output
EOF
```

### Copy Grafana Datasource
```bash
# File: ./config/grafana/provisioning/datasources/loki.yaml
cat > ./config/grafana/provisioning/datasources/loki.yaml << 'EOF'
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
EOF
```

### Add to .env
```bash
cat >> .env << 'EOF'

# Stage 1: Centralized Logging
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=change-me-to-secure-password
EOF
```

### Add Services to docker-compose.yml

Append this to the bottom of the `services:` section in `docker-compose.yml`:

```yaml
  loki:
    restart: unless-stopped
    image: grafana/loki:latest
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
    image: grafana/promtail:latest
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

  grafana:
    restart: unless-stopped
    image: grafana/grafana:latest
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

### Deploy & Verify
```bash
# Deploy
docker compose up -d loki promtail grafana

# Wait for healthy (2-3 minutes)
sleep 30
docker compose ps

# Verify logs flowing
curl -s 'http://localhost:3100/loki/api/v1/label/container/values' | jq .
# Expected output: ["cleanuparr", "control-panel", "loki", ..., "watchtower"]

# Check Grafana health
curl http://localhost:3001/api/health
# Expected output: {"database":"ok","init":{"done":true},...}
```

---

## TOMORROW (1 hour - Access Grafana & query logs)

### Access Grafana UI
```bash
open http://localhost:3001
# Username: admin
# Password: (from .env GRAFANA_ADMIN_PASSWORD)
```

### Explore Logs
1. Left sidebar → Explore
2. Select data source: "Loki"
3. In query box, enter:
   ```
   {job="docker"}
   ```
4. Click "Run query"
5. Should see logs from all containers

### Test Container-Specific Queries
```
{container="radarr"}          # Only Radarr logs
{container="sonarr"} |= "error"  # Sonarr errors only
{job="docker"} |= "ERROR"     # All errors across stack
```

---

## WITHIN 1 WEEK (Create dashboards)

### Create Dashboard 1: Stack Overview
1. Grafana → Dashboards → Create Dashboard
2. Add Panel → Loki
3. Query: `{job="docker"} |= "ERROR"`
4. Title: "Errors (last 1h)"
5. Save

### Create Dashboard 2: Import Tracking
1. Add Panel
2. Query: `{container=~"radarr|sonarr"} |= "imported"`
3. Title: "Successful Imports"
4. Save

### Create Dashboard 3: NzbDAV Health
1. Add Panel
2. Query: `{container="nzbdav"}`
3. Title: "NzbDAV Logs"
4. Save

---

## Verification Checklist (mark as you go)

- [ ] Directories created (./config/loki, ./data/loki, etc)
- [ ] Loki config file in place
- [ ] Promtail config file in place
- [ ] Grafana datasource config in place
- [ ] .env updated with Grafana credentials
- [ ] docker-compose.yml updated (3 new services)
- [ ] Containers deployed: `docker compose up -d loki promtail grafana`
- [ ] All 3 containers healthy: `docker compose ps loki promtail grafana`
- [ ] Loki receiving logs: `curl 'http://localhost:3100/loki/api/v1/label/container/values'`
- [ ] Grafana UI accessible: http://localhost:3001
- [ ] Can query logs in Grafana Explore tab
- [ ] At least one dashboard created and showing data

---

## Command Summary (copy-paste friendly)

```bash
# 1. Create directories
mkdir -p ./config/loki ./config/promtail ./config/grafana/provisioning/datasources
mkdir -p ./data/loki ./data/grafana
chmod 777 ./data/loki ./data/grafana

# 2. Deploy
docker compose up -d loki promtail grafana

# 3. Wait for health
sleep 30
docker compose ps

# 4. Verify logs
curl -s 'http://localhost:3100/loki/api/v1/label/container/values' | jq .

# 5. Access Grafana
# http://localhost:3001 (admin / password from .env)

# 6. Query logs in Grafana Explore
# {job="docker"}
# {container="radarr"}
# {job="docker"} |= "ERROR"
```

---

## Next Step After Stage 1 is Stable

Once you have 24+ hours of log data and dashboards working:

1. Document any patterns (slow imports, recurring errors)
2. Adjust alert thresholds based on baseline
3. Commit all changes to git
4. Then decide: **Stage 2 (Secrets) or Stage 4 (Scanning)?**

---

## Support

If stuck:
1. Check logs: `docker logs loki`, `docker logs promtail`, `docker logs grafana`
2. Verify configs: `cat ./config/loki/loki-config.yaml` (check for syntax errors)
3. Test Loki API: `curl http://localhost:3100/ready`
4. Full troubleshooting in `.claude/STAGE-1-IMPLEMENTATION.md`

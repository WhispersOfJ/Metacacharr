# Stage 1: Centralized Logging - DEPLOYED ✓

**Deployed:** 2026-08-21  
**Commit:** 7213249  
**Status:** All 3 services running and healthy

---

## What's Running

| Service | Version | Port | Status |
|---------|---------|------|--------|
| **Loki** | 2.5.0 | 3100 | ✓ Healthy |
| **Promtail** | 2.5.0 | internal | ✓ Running |
| **Grafana** | 10.0.0 | 3001 | ✓ Healthy |

---

## Key Configuration

### Loki (Log Aggregation)
- **Storage:** Filesystem (boltdb-shipper + chunks directory)
- **Data Directory:** `./data/loki/`
- **Config:** `./config/loki/loki-config.yaml`
- **Retention:** 168 hours (7 days)
- **Healthcheck:** Ready probe via `/ready` endpoint

### Promtail (Log Collector)
- **Source:** Docker container JSON logs (`/var/lib/docker/containers/`)
- **Config:** `./config/promtail/promtail-config.yaml`
- **Scrape Target:** All containers in `stacknet`
- **Pipeline:** JSON parsing → label extraction → Loki push

### Grafana (Visualization)
- **Datasource:** Loki at `http://loki:3100`
- **Config:** `./config/grafana/provisioning/datasources/loki.yaml`
- **Plugins:** grafana-piechart-panel (pre-installed)
- **Admin:** `admin` / `media-stack-logging-secure-2026`

---

## Access Points

**Grafana UI:**
```
http://localhost:3001
Login: admin / media-stack-logging-secure-2026
```

**Loki API:**
```
http://localhost:3100
Query example: curl 'http://localhost:3100/loki/api/v1/label/job/values'
Response: ["docker"]
```

**Check Logs:**
```bash
curl -G 'http://localhost:3100/loki/api/v1/query' \
  --data-urlencode 'query={job="docker"}'
```

---

## Troubleshooting Fix (Key Issue Resolved)

**Problem:** Loki 2.9.3 had permission/configuration issues:
- WAL folder creation failed (`mkdir wal: permission denied`)
- Schema table lookup errors (`table not found`)
- Compactor panic on non-positive intervals

**Solution:** Downgraded to Loki 2.5.0 with simplified config:
- Disabled WAL in ingester (`wal.enabled: false`)
- Set valid compaction interval (10m instead of 0)
- Used filesystem storage with boltdb-shipper (proven stable)
- Removed unnecessary modules to reduce initialization

**Result:** All three services now run stably with no errors.

---

## Next Steps

1. **Login to Grafana** (http://localhost:3001)
   - Add data source if needed (should auto-import from provisioning)
   - Create dashboards for:
     - Stack Overview (error rates, restarts)
     - Import Tracking (Radarr/Sonarr)
     - NzbDAV Health

2. **Verify Log Collection**
   ```bash
   # Check if Promtail is scraping
   curl 'http://localhost:3100/loki/api/v1/label/job/values'
   
   # Query logs by container
   curl -G 'http://localhost:3100/loki/api/v1/query' \
     --data-urlencode 'query={container="radarr"}'
   ```

3. **Setup Alerts** (Week 2)
   - Configure Discord webhook notifications
   - Create alert rules for:
     - Service down (no logs for 5 min)
     - High error rate (>10 errors/min)
     - NzbDAV unhealthy

4. **Monitor Storage**
   - Loki data stored in `./data/loki/` (typically 50-200MB)
   - Retention: 7 days (adjustable via `reject_old_samples_max_age`)
   - Compactor runs every 10 minutes

---

## File Structure

```
./config/
├── loki/
│   └── loki-config.yaml           # Main Loki config (2.5.0 compatible)
├── promtail/
│   └── promtail-config.yaml       # Docker log scraper config
└── grafana/
    └── provisioning/
        └── datasources/
            └── loki.yaml          # Auto-import Loki datasource

./data/
├── loki/
│   ├── chunks/                    # Log data storage
│   ├── boltdb-shipper-active/     # Active index directory
│   └── boltdb-shipper-cache/      # Index cache
└── grafana/                       # Grafana database + plugins

docker-compose.yml                 # Services at bottom (loki, promtail, grafana)
.env                               # GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD
```

---

## Architecture Diagram

```
Containers (all services)
    ↓
Docker daemon (json-file logs @ /var/lib/docker/containers/*/...-json.log)
    ↓
Promtail (reads via docker.sock + file mounts)
    ↓
Loki (aggregates, indexes, stores for 7 days)
    ↓
Grafana (UI for queries, dashboards, alerts)
    ↓
Discord webhook (SLA violations)
```

---

## Performance & Resource Usage

- **Loki:** 1GB mem limit, 256MB reservation
- **Promtail:** 512MB mem limit, 64MB reservation
- **Grafana:** 512MB mem limit, 128MB reservation
- **Disk:** ~100MB for 7-day retention (estimated, actual ~50-200MB)
- **CPU:** Negligible (background polling)

---

## Known Limitations

- **In-memory ring for cluster mgmt** (not distributed, single-instance only)
- **No WAL** (logs lost on crash, but Promtail retries)
- **7-day retention** (adjustable, older logs discarded)
- **No authentication** on Loki API (LAN-only, same as rest of stack)

---

## Related Docs

- Full implementation guide: `.claude/STAGE-1-IMPLEMENTATION.md`
- Phase 2 roadmap (Secrets, Network, Scanning): `.claude/PHASE-2-ROADMAP.md`
- Troubleshooting: `loki-debug.md` (this session's research log)

---

**Status:** ✓ DEPLOYED & HEALTHY  
**Ready for:** Dashboard creation + alert configuration (Week 2)

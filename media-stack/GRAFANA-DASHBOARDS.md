# Grafana Dashboards for Media Stack Logging

**Status:** 2 dashboards deployed + integrated  
**Created:** 2026-08-21  
**Data Source:** Loki (localhost:3100)

---

## Dashboard Overview

### 1. Loki - Logs Overview

**Purpose:** General log viewing, error tracking, system health  
**Link:** http://localhost:3001/d/loki-logs-overview

**Panels:**

| Panel | Purpose | Query |
|-------|---------|-------|
| Error Rate by Container (pie) | Visual breakdown of which services produce most errors | Error count by container (5m) |
| ERROR Count (stat) | Quick glance at errors in last 5 minutes | All ERROR level logs |
| WARNING Count (stat) | Quick glance at warnings in last 5 minutes | All WARN level logs |
| INFO Count (stat) | Quick glance at info messages in last 5 minutes | All INFO level logs |
| Active Containers (stat) | How many containers logged in last 5 minutes | Distinct containers |
| Recent Logs (table) | Last 1000 log lines from all containers | Raw log table, JSON parsed |
| Log Rate by Container (timeseries) | Log volume trend over time | Rate of logs per minute |
| Error Rate by Container (timeseries) | Error trend over time (red line = bad) | ERROR log rate per minute |
| ERROR Logs Only (table) | All ERROR level logs from last 24h | Filtered error logs |
| Import Pipeline Logs (table) | Logs from Radarr/Sonarr/Prowlarr/Seerr | Import service logs |
| NzbDAV Logs (table) | All logs from download client | NzbDAV logs |

**Use Cases:**
- Spot check: "Are there any errors right now?" → Look at ERROR Count stat
- Investigation: "What went wrong with the import?" → Go to Import Pipeline Logs table
- Trending: "How often do we have errors?" → Watch Error Rate timeseries
- Deep dive: "What happened 3 hours ago?" → Adjust time range (top right), search logs

**Time Range:** Defaults to last 6 hours (adjustable)

---

### 2. Loki - Import Pipeline

**Purpose:** Focused view of import workflow (Radarr, Sonarr, Prowlarr, Seerr, NzbDAV)  
**Link:** http://localhost:3001/d/loki-import-pipeline

**Panels:**

| Panel | Purpose | Query |
|-------|---------|-------|
| Radarr Errors (stat) | Error count from movie importer (1h window) | Radarr ERROR count |
| Sonarr Errors (stat) | Error count from TV importer (1h window) | Sonarr ERROR count |
| NzbDAV Errors (stat) | Error count from download client (1h window) | NzbDAV ERROR count |
| Prowlarr Errors (stat) | Error count from indexer manager (1h window) | Prowlarr ERROR count |
| Error Rate Trend (timeseries) | 5-minute error rate trend over 24h | All 4 services, color-coded |
| Import Pipeline - ERROR Logs (table) | All errors from pipeline services (24h) | Radarr/Sonarr/Prowlarr/Seerr/NzbDAV ERROR logs |
| Import Pipeline - WARN Logs (table) | All warnings from pipeline services (24h) | Radarr/Sonarr/Prowlarr/Seerr/NzbDAV WARN logs |
| NzbDAV Full Logs (table) | All logs from NzbDAV (24h, all levels) | NzbDAV full log dump |

**Use Cases:**
- Daily check: "Did anything break overnight?" → Look at 4 error stat boxes
- Import failure: "Why didn't this movie/show import?" → Check ERROR Logs table
- Troubleshooting: "Is NzbDAV having issues?" → Go to NzbDAV Full Logs
- Long-term trending: "How stable is the pipeline?" → Watch Error Rate Trend over days

**Time Range:** Defaults to last 24 hours (adjustable)

---

## How to Use Dashboards

### Viewing Dashboards

1. **Login to Grafana**
   ```
   http://localhost:3001
   Username: admin
   Password: media-stack-logging-secure-2026
   ```

2. **Browse Dashboards**
   - Click "Dashboards" in left sidebar
   - Click "Loki - Logs Overview" or "Loki - Import Pipeline"

### Adjusting Time Range

All dashboards support time range adjustment:
- Click the time selector in top-right (e.g., "Last 6 hours")
- Common ranges: 30m, 1h, 6h, 24h, 7d
- Custom: Enter "From" and "To" dates

### Filtering Logs

#### Filter by Container (Logs Overview)
1. Top of dashboard: "Container" dropdown
2. Select one or more containers (e.g., radarr, sonarr)
3. All panels update automatically

#### Filter by Job
1. Top of dashboard: "Job" dropdown
2. Currently only "docker" is available
3. Useful if we add multiple log sources later

### Searching Logs

In any log table panel:
1. Click the table
2. Use Ctrl+F (browser find) to search within results
3. Or use Loki query language in dashboard editor

### Exporting Data

To export logs or metrics:
1. Click the three-dot menu (top right of a panel)
2. Select "Export" or "Download as CSV"
3. Or use "Copy" to copy to clipboard

---

## Understanding Log Levels

All logs are categorized by severity:

| Level | Color | Meaning | Action |
|-------|-------|---------|--------|
| ERROR | 🔴 Red | Service/operation failed | Investigate immediately |
| WARN | 🟠 Orange | Degraded behavior or potential issue | Monitor, fix soon |
| INFO | 🔵 Blue | Normal operation events | Reference only |
| DEBUG | ⚪ Gray | Detailed diagnostic info | Rarely needed |

**Examples:**
- Radarr ERROR: "Failed to import movie: connection timeout"
- Sonarr WARN: "API response slow (5s timeout)"
- NzbDAV INFO: "Downloaded 500 files in 2 minutes"

---

## Troubleshooting Dashboard Issues

### No Data in Panels

**Problem:** Panels show "No data" or are empty

**Causes & Fixes:**
1. **Loki datasource not connected**
   - Go to Grafana Settings → Data Sources
   - Check "Loki" datasource shows "Data source is working"
   - Fix: Ensure Loki container is running: `docker compose ps loki`

2. **Promtail not scraping logs**
   - Check Promtail is running: `docker compose ps promtail`
   - Check Promtail can read docker socket: `docker logs promtail | grep -i error`
   - Fix: Restart Promtail: `docker compose restart promtail`

3. **Time range has no logs**
   - Adjust time range: Expand "Last 6 hours" → "Last 24 hours"
   - Or check if services were recently deployed (fresh Loki has no history)
   - Fix: Wait for logs to accumulate or restart services to generate logs

4. **Query syntax error**
   - Click panel → "Edit" (pencil icon)
   - Check Loki query in "Query" section
   - Common issue: Missing quotes around label values
   - Fix: Use single quotes for strings: `{job="docker"}`

### Dashboard Won't Load

**Problem:** Dashboard shows 404 or "Not found"

**Causes & Fixes:**
1. **Dashboard not imported**
   - Run import script: `./scripts/import-grafana-dashboards.sh`
   - Or manually go to Dashboards → New → Import → upload JSON file

2. **Datasource missing**
   - Go to Grafana Settings → Data Sources
   - Ensure "Loki" datasource exists and is set as default
   - Fix: Re-import dashboards after creating datasource

### Queries Running Slowly

**Problem:** Dashboard panels take 30+ seconds to load

**Causes & Fixes:**
1. **Time range too large**
   - Adjust to "Last 6 hours" or "Last 24 hours" instead of "All time"
   - Queries over 7 days may be slow

2. **Query too broad**
   - Use more specific filters: `{job="docker", container="radarr"}` instead of `{job="docker"}`
   - Filter by level: `| level="ERROR"` instead of all levels

3. **Loki retention may be purging old data**
   - Loki currently retains 7 days of logs
   - Querying older data may query incomplete data
   - Check: `STAGE-1-DEPLOYED.md` for retention settings

### Logs Missing

**Problem:** Expected log lines don't appear in tables

**Causes:**
1. **Log lines don't match query filter**
   - Check exact container name: `{container="radarr"}` vs `{container="Radarr"}`
   - Check log level: Use `| level="ERROR"` to filter

2. **Logs already rotated (older than 7 days)**
   - Loki retains 7 days by default
   - Older logs are automatically deleted
   - Fix: Adjust retention in loki-config.yaml (requires restart)

3. **Promtail isn't scraping that container**
   - Check Promtail config: `config/promtail/promtail-config.yaml`
   - Verify container name matches: `docker ps | grep <name>`
   - Fix: Update Promtail config, restart: `docker compose restart promtail`

---

## Dashboard Customization

### Adding a New Panel

1. Open dashboard (e.g., "Loki - Logs Overview")
2. Click "Edit" (pencil icon, top right)
3. Click "Add panel" (top left)
4. Choose panel type: Table, Graph, Stat, etc.
5. Write Loki query (see examples below)
6. Click "Run queries" (Ctrl+Enter)
7. Adjust visualization options
8. Click "Save" (top right)

### Example Loki Queries

**All logs from a specific container:**
```
{job="docker", container="radarr"}
```

**Errors only:**
```
{job="docker"} | json | level="ERROR"
```

**Logs containing a specific word:**
```
{job="docker"} | json | keyword="timeout"
```

**Count of logs per container (5-minute intervals):**
```
rate({job="docker"} [5m])
```

**Errors per container:**
```
rate({job="docker"} | json | level="ERROR" [1m])
```

**Search across all fields (slower):**
```
{job="docker"} | "connection refused"
```

### Copying a Dashboard

To create a variant of an existing dashboard:
1. Open dashboard
2. Click three-dot menu (top right)
3. Click "Save as..."
4. Enter new name (e.g., "Loki - Radarr Only")
5. Edit as needed

---

## Performance & Limits

### Query Performance

| Query Type | Typical Speed | Notes |
|------------|---------------|-------|
| Simple filter (container) | <500ms | `{container="radarr"}` |
| Filter + JSON parse | <1s | `{container="radarr"} | json` |
| Error rate calculation | 1-3s | `rate({...} | level="ERROR" [5m])` |
| 24h time range | 1-5s | Depends on log volume |
| 7d time range | 5-30s | Large query, may timeout |

**Performance tips:**
- Use specific time ranges (6h better than 30d)
- Filter by container early: `{container="X"}` before `| json`
- Use `level="ERROR"` filter to reduce data
- Avoid regex queries (slow)

### Storage Usage

- Current: ~100-200MB for 7 days of logs
- Log retention: 168 hours (7 days, configured in loki-config.yaml)
- Growth rate: ~15-30MB per day (varies with service noise)

---

## Alerts (Future Enhancement)

Alerts can be configured per dashboard:

**Example alert:** "Notify if Radarr has >10 errors per hour"

Setup:
1. Open dashboard
2. Click "Alert" tab
3. Create alert rule with condition: `count(errors) > 10 per hour`
4. Set notification channel: Discord, email, etc.

This is a future enhancement; not yet configured.

---

## Accessing Dashboards from Outside LAN

**Grafana UI is LAN-only by default** (no external access for security)

To access from outside:
1. Configure reverse proxy (nginx, caddy, etc.)
2. Set up TLS/SSL certificate
3. Update firewall rules to allow traffic
4. Configure Grafana in .env: `GF_SERVER_DOMAIN` and `GF_SERVER_ROOT_URL`

**Not recommended without authentication layer** (use OAuth2, LDAP, etc.)

---

## Related Documentation

- **Loki deployment:** `STAGE-1-DEPLOYED.md`
- **Logging infrastructure:** `.claude/STAGE-1-IMPLEMENTATION.md`
- **Loki config:** `config/loki/loki-config.yaml`
- **Promtail config:** `config/promtail/promtail-config.yaml`

---

## Quick Reference

### Accessing Dashboards

```bash
# Open dashboards in browser
http://localhost:3001/d/loki-logs-overview          # Overview
http://localhost:3001/d/loki-import-pipeline        # Import Pipeline

# Or via Grafana UI:
# Click "Dashboards" → Select dashboard
```

### Re-importing Dashboards

```bash
# If dashboards are missing or broken
./scripts/import-grafana-dashboards.sh
```

### Checking Loki Health

```bash
# From host
curl http://localhost:3100/ready

# From Grafana (test datasource)
Grafana UI → Settings → Data Sources → Loki → "Test"
```

### View Loki Status in Grafana

```
Grafana UI → Settings → Data Sources → Loki
Should show: "Data source is working" in green
```

---

## Tips & Tricks

### Finding a Specific Error

1. Go to "Loki - Logs Overview" dashboard
2. Adjust time range to when error occurred
3. Go to "ERROR Logs Only" table
4. Use Ctrl+F (browser search) to find error message
5. Note the timestamp and container name

### Monitoring Import Success

1. Go to "Loki - Import Pipeline" dashboard
2. Watch the 4 error stat boxes (Radarr, Sonarr, NzbDAV, Prowlarr)
3. If all show "0" for last hour = healthy
4. If any show errors, click the "ERROR Logs" table for details

### Detecting Service Restarts

Restarts cause log gaps + "connection reset" errors:
1. Look for sudden 0-log period in "Log Rate by Container" graph
2. Then see spike of logs as service restarts
3. Check "Recent Logs" for restart-related messages

### Comparing Services

1. Go to "Error Rate Trend" graph
2. Legend shows all services color-coded
3. Easily spot which service has most errors

---

**Status:** ✓ DASHBOARDS DEPLOYED & READY  
**Last Updated:** 2026-08-21  
**Next:** Create alert rules + Discord notifications

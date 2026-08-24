# Cron Jobs Setup

Automate upstream monitoring and weekly CVE scans.

---

## Task 2: Upstream Release Monitoring

**Script:** `scripts/check-upstream-updates.sh`  
**Frequency:** Weekly (Mondays at 9 AM)  
**Purpose:** Check hotio, seerr-team, arabcoders for new releases; alert on Discord

### Setup

#### 1. Add to Crontab

```bash
# Edit your crontab
crontab -e

# Add this line (runs every Monday at 9 AM):
0 9 * * 1 cd /home/bear/Claude/media-stack && DISCORD_WEBHOOK_URL="$DISCORD_WEBHOOK_URL" bash scripts/check-upstream-updates.sh >> /var/log/media-stack-upstream-check.log 2>&1
```

#### 2. Alternative: Systemd Timer (Recommended)

Create `/etc/systemd/system/media-stack-upstream-check.service`:

```ini
[Unit]
Description=Media Stack Upstream Release Check
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=media-stack
WorkingDirectory=/home/bear/Claude/media-stack
EnvironmentFile=/home/bear/Claude/media-stack/.env
ExecStart=/bin/bash scripts/check-upstream-updates.sh
StandardOutput=journal
StandardError=journal
```

Create `/etc/systemd/system/media-stack-upstream-check.timer`:

```ini
[Unit]
Description=Weekly Media Stack Upstream Check
Requires=media-stack-upstream-check.service

[Timer]
OnCalendar=Mon *-*-* 09:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now media-stack-upstream-check.timer
sudo systemctl status media-stack-upstream-check.timer
```

Check logs:
```bash
sudo journalctl -u media-stack-upstream-check.service -f
```

### What It Does

1. **Checks for new versions:**
   - hotio: Radarr, Sonarr, Prowlarr
   - seerr-team: Seerr
   - arabcoders/codeassassin: Unpackerr, WatchState

2. **Stores version state** in `.upstream-versions.json`

3. **Alerts via Discord** if new version detected (only notifies on change, not every run)

4. **Enables Phase 2-3 remediation** when blockers are unblocked

### State File

Stored in `.upstream-versions.json`:
```json
{
  "last_checked": "2026-08-21 15:48:20",
  "hotio_radarr": "version-tag",
  "hotio_sonarr": "version-tag",
  "hotio_prowlarr": "version-tag",
  "seerr": "v1.2.3",
  "unpackerr": "version-tag",
  "watchstate": "v0.x.x"
}
```

### Manual Run

```bash
cd /home/bear/Claude/media-stack
DISCORD_WEBHOOK_URL="your-webhook-url" bash scripts/check-upstream-updates.sh
```

---

## Task 3: Weekly CVE Scanning

**Script:** `scripts/weekly-cve-scan.sh`  
**Frequency:** Weekly (Sundays at 2 AM)  
**Purpose:** Automated Trivy scan; track trend; alert on CVE surge

### Setup

#### 1. Add to Crontab

```bash
crontab -e

# Runs every Sunday at 2 AM:
0 2 * * 0 cd /home/bear/Claude/media-stack && DISCORD_WEBHOOK_URL="$DISCORD_WEBHOOK_URL" bash scripts/weekly-cve-scan.sh >> /var/log/media-stack-cve-scan.log 2>&1
```

#### 2. Alternative: Systemd Timer (Recommended)

Create `/etc/systemd/system/media-stack-cve-scan.service`:

```ini
[Unit]
Description=Media Stack Weekly CVE Scan
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
User=media-stack
WorkingDirectory=/home/bear/Claude/media-stack
EnvironmentFile=/home/bear/Claude/media-stack/.env
ExecStart=/bin/bash scripts/weekly-cve-scan.sh
StandardOutput=journal
StandardError=journal
```

Create `/etc/systemd/system/media-stack-cve-scan.timer`:

```ini
[Unit]
Description=Weekly Media Stack CVE Scan
Requires=media-stack-cve-scan.service

[Timer]
OnCalendar=Sun *-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now media-stack-cve-scan.timer
sudo systemctl status media-stack-cve-scan.timer
```

Check logs:
```bash
sudo journalctl -u media-stack-cve-scan.service -f
```

### What It Does

1. **Runs trivy scan** on all images in docker-compose.yml
2. **Counts CVEs** by severity (CRITICAL, HIGH, MEDIUM, LOW)
3. **Stores results** with timestamp in `.cve-scan-history/`
4. **Tracks trend** by comparing with previous scan
5. **Alerts on surge:**
   - **CRITICAL:** Any new CRITICAL CVE
   - **HIGH:** +10 or more HIGH CVEs
6. **Cleans up** scans older than 30 days
7. **Sends Discord alert** if surge detected

### State Files

Stored in `.cve-scan-history/`:
```
scan-20260821-154828.json    # Individual scan results
latest.json                  # Latest scan (for dashboard)
```

Scan file format:
```json
{
  "timestamp": "2026-08-21T15:48:28Z",
  "critical": 0,
  "high": 658,
  "medium": 774,
  "low": 407,
  "total": 1883
}
```

### Dashboard Integration

Update Grafana dashboard to use `/cve-scan-history/latest.json`:

1. Add data source: JSON API pointing to `.cve-scan-history/latest.json`
2. Create panels:
   - Current CVE counts (gauge per severity)
   - Trend graph (query scan history)
   - Alert threshold indicators

### Manual Run

```bash
cd /home/bear/Claude/media-stack
DISCORD_WEBHOOK_URL="your-webhook-url" bash scripts/weekly-cve-scan.sh
```

### View Scan History

```bash
# List all scans
ls -la .cve-scan-history/

# View latest scan
cat .cve-scan-history/latest.json | jq .

# View all scans (JSON array)
jq -s '.' .cve-scan-history/scan-*.json | head -50
```

---

## Environment Variables

Both scripts require `.env` to be present with:

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN
```

The scripts read this via:
- **Crontab:** Export before running
- **Systemd:** EnvironmentFile=.../env (auto-loads)

---

## Monitoring the Jobs

### Crontab Logs

```bash
# View cron execution
sudo tail -f /var/log/syslog | grep CRON

# View job logs
tail -f /var/log/media-stack-upstream-check.log
tail -f /var/log/media-stack-cve-scan.log
```

### Systemd Logs

```bash
# Both jobs
sudo journalctl -u media-stack-upstream-check.service -f
sudo journalctl -u media-stack-cve-scan.service -f

# Timer status
sudo systemctl list-timers media-stack-*
```

### Verify Execution

After first run, check:
- `.upstream-versions.json` - updated with new check time
- `.cve-scan-history/` - contains scan result with timestamp
- Discord channel - should have alert if changes detected

---

## Troubleshooting

### Script fails to run via cron

**Problem:** Works manually but not in cron

**Solutions:**
1. Check environment variables are set:
   ```bash
   crontab -e
   # At top, add:
   DISCORD_WEBHOOK_URL=https://...
   ```

2. Redirect output to see errors:
   ```bash
   0 9 * * 1 cd /home/bear/Claude/media-stack && bash scripts/check-upstream-updates.sh >> /var/log/upstream.log 2>&1
   ```

3. Check cron logs:
   ```bash
   sudo tail -50 /var/log/syslog | grep CRON
   ```

### Webhook URL not found

**Problem:** Discord alert not sending

**Solution:** Verify URL is in .env:
```bash
cat .env | grep DISCORD_WEBHOOK_URL
# Should show: DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

### Trivy fails: "no such file or directory"

**Problem:** Docker images don't exist

**Solution:** Run manually to test:
```bash
cd /home/bear/Claude/media-stack
bash scripts/weekly-cve-scan.sh
```

---

## Schedule Summary

| Task | Day | Time | Frequency |
|------|-----|------|-----------|
| Upstream Check | Monday | 9:00 AM | Weekly |
| CVE Scan | Sunday | 2:00 AM | Weekly |

Adjust times as needed by editing crontab or timer file.

---

## Next Steps

1. Choose crontab OR systemd (systemd recommended for reliability)
2. Set DISCORD_WEBHOOK_URL in .env
3. Enable/add the jobs
4. Run manually once to verify
5. Check Discord for confirmation messages
6. Monitor logs for 1-2 weeks

See main README for integration with Grafana dashboards.

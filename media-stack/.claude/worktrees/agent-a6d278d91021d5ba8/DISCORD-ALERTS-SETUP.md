# Discord Alerts Setup Guide

Real-time log alerts from Grafana/Loki to Discord. Catch errors, restarts, and missing logs before they become problems.

---

## 1. Create Discord Webhook

### In your Discord server:

1. Go to **Server Settings** → **Integrations** → **Webhooks**
2. Click **New Webhook**
3. Name it: `Media Stack Alerts` (or preferred name)
4. Select channel: Create or use existing `#media-stack-alerts`
5. Click **Copy Webhook URL**
6. Save it securely (next step)

**Webhook URL format:**
```
https://discord.com/api/webhooks/WEBHOOK_ID/WEBHOOK_TOKEN
```

---

## 2. Add to Environment

### Update `.env`:

```bash
# Find this line:
DISCORD_WEBHOOK_URL=changeme

# Replace with your webhook URL:
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN
```

### Verify in `.env.example` (already configured):
- ✓ `DISCORD_WEBHOOK_URL` present

---

## 3. Deploy

### Restart Grafana to load alert configuration:

```bash
docker compose up -d grafana
```

### Verify alerts are loaded:

```bash
# Check Grafana logs for alert provisioning
docker compose logs grafana | grep -i alert

# Expected output:
# grafana    | logger=alerting.provisioner ... provisioned alert rules
```

---

## 4. Configure Alert Channel in Grafana UI

**Until alerts are fully provisioned via YAML, manual setup:**

1. Open Grafana: http://localhost:3001
2. Go to **Alerting** → **Contact points**
3. Click **New contact point**
4. Configuration:
   - **Name:** Discord
   - **Contact point type:** Discord
   - **Webhook URL:** Paste your webhook URL
   - **Title:** Media Stack Alert (optional)
5. Click **Save contact point**

---

## 5. Test Alert

### Manual test from Grafana:

1. **Alerting** → **Contact points**
2. Select **Discord** contact point
3. Click **Test** button
4. Confirm message appears in Discord channel

### Test message should show:
```
🔔 Media Stack Alert
Test notification from Grafana
```

---

## 6. Alert Rules

Three default alert rules configured:

### Rule 1: Critical Errors
- **Trigger:** ERROR or FATAL keywords in logs
- **Check interval:** 5 minutes
- **Severity:** Critical
- **Action:** Immediate alert

### Rule 2: High Restart Rate
- **Trigger:** Multiple restarts in 10 minutes
- **Check interval:** 10 minutes
- **Severity:** Warning
- **Action:** Alert after 2 minutes of sustained restarts

### Rule 3: Service Not Logging
- **Trigger:** No logs from service in 10 minutes
- **Check interval:** 10 minutes
- **Severity:** Warning
- **Action:** Alert after 5 minutes with no logs

---

## 7. Customize Alerts

### Edit alert rules:

```bash
# File: config/grafana/provisioning/alerting/alert-rules.yaml
vim config/grafana/provisioning/alerting/alert-rules.yaml
```

### Common customizations:

**Change check interval:**
```yaml
interval: 5m  # Check every 5 minutes
```

**Change alert duration (wait before firing):**
```yaml
for: 2m  # Alert after 2 minutes of threshold breach
```

**Modify log query:**
```yaml
expression: 'count(count_over_time({job=~".+"} |= "CRITICAL" [5m])) by ()'
```

### Restart to apply changes:

```bash
docker compose restart grafana
```

---

## 8. View Alert History

In Grafana:

1. **Alerting** → **Alert rules**
2. Click an alert name to see history
3. View:
   - Alert state changes
   - When it fired/resolved
   - Last evaluation result

---

## 9. Troubleshooting

### Alert not firing?

1. **Check webhook URL:**
   ```bash
   curl -X POST https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN \
     -H 'Content-Type: application/json' \
     -d '{"content":"Test from curl"}'
   ```
   Should see message in Discord.

2. **Check Grafana logs:**
   ```bash
   docker compose logs grafana | grep -i "discord\|alert\|error"
   ```

3. **Verify alert rule is enabled:**
   - Grafana → **Alerting** → **Alert rules**
   - Toggle should be ON (blue)

### "Contact point not found"?

- Re-save contact point in Grafana UI (step 4)
- Or restart Grafana after updating .env

### Webhook URL format incorrect?

- Must be full URL: `https://discord.com/api/webhooks/ID/TOKEN`
- Not shortened or partial URL
- Check for trailing slashes (remove if present)

---

## 10. Next Steps

### Extend alerts:

- Add more log queries (stack-specific patterns)
- Create separate Discord channels per service
- Set up digest (daily summary instead of real-time)
- Add Prometheus metrics (CPU, memory, disk)

### Example: Add channel for Radarr errors only

```yaml
- name: Discord Radarr
  receivers:
    - uid: discord_radarr
      type: discord
      settings:
        url: ${DISCORD_RADARR_WEBHOOK_URL}
```

Then in alert rules:
```yaml
expression: 'count(count_over_time({job="radarr"} |= "error" [5m])) by ()'
```

---

## 11. Documentation Reference

| File | Purpose |
|------|---------|
| `.env` | Discord webhook URL (sensitive) |
| `docker-compose.yml` | Grafana config, environment pass-through |
| `config/grafana/provisioning/notificationchannels/discord.yaml` | Old-style notification channel (legacy) |
| `config/grafana/provisioning/alerting/contact-points.yaml` | Modern contact points |
| `config/grafana/provisioning/alerting/alert-rules.yaml` | Alert rule definitions |

---

## 12. Security Notes

⚠️ **Webhook URL is sensitive:**
- Never commit to git (in `.env` only, not `.env.example`)
- Rotate quarterly (delete old webhook, create new one)
- Log webhook access in Discord (audit trail)
- Restrict webhook to specific channel (already done if you selected one)

---

## Verification Checklist

- [ ] Discord server created / webhook created
- [ ] Webhook URL added to `.env`
- [ ] Grafana restarted: `docker compose up -d grafana`
- [ ] Alert rules loaded: Check Grafana logs
- [ ] Contact point configured in Grafana UI
- [ ] Test alert sent and received in Discord
- [ ] Alert rules visible in **Alerting** → **Alert rules**
- [ ] At least one rule enabled (toggle ON)

---

**Status:** ✅ Ready to deploy

When ready:
```bash
docker compose up -d grafana
# Wait 30s for health check
curl http://localhost:3001/api/health
```

Then test an alert via Grafana UI.

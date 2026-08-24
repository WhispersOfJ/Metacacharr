# Plex Media Server Setup

> PMS-specific configuration for Metacache integration.

## Requirements

- Plex Media Server **1.43+** (Custom Metadata Providers support)
- Custom Metadata Providers must be enabled in PMS settings

## Enabling Custom Metadata Providers

1. Open Plex Web App
2. Go to **Settings** (gear icon) → **Metadata Agents**
3. Ensure **Custom Metadata Providers** is toggled ON
4. If not visible, update PMS to 1.43+

## Adding Metacache as a Provider

### Movie Provider

1. Settings → Metadata Agents → **Add Provider**
2. Name: `Metacache Movie`
3. URL: `http://METACACHE_IP:8765/movie`
4. Click **Save**

### TV Provider

1. Settings → Metadata Agents → **Add Provider**
2. Name: `Metacache TV`
3. URL: `http://METACACHE_IP:8765/tv`
4. Click **Save**

## Assigning to Libraries

### New Library

1. Settings → Libraries → **Add Library**
2. Choose type (Movies or TV Shows)
3. In Advanced → **Metadata Agent**: select "Metacache Movie" or "Metacache TV"
4. Set Metacache as the **Primary** agent
5. Complete library setup

### Existing Library

1. Settings → Libraries → select library → **Edit**
2. Advanced → **Metadata Agent**: change to Metacache
3. Click **Save**
4. Click **Refresh Metadata** on the library

## Language Configuration

Plex sends `X-Plex-Language` with metadata requests. Metacache uses this to serve the right language variant.

To cache multiple languages, configure warming:

```bash
Metacache__Warm__Languages__0=en-US
Metacache__Warm__Languages__1=de-DE
Metacache__Warm__Languages__2=fr-FR
```

## Country Configuration

Plex sends `X-Plex-Country` for content ratings (e.g. "US", "GB"). Metacache uses this to return the correct content rating for the region.

## Webhook Integration

Configure Plex webhooks for predictive warming:

1. Settings → **Webhooks**
2. Add webhook: `http://METACACHE_IP:8765/webhook/plex`
3. (If auth enabled) Add header: `X-API-Key: your-api-key`

This enables predictive warming: when playback starts, Metacache pre-warms the played item + next episodes + similar titles.

## Troubleshooting

### "Custom Metadata Providers not available"

- Update PMS to 1.43+
- Check PMS version: Settings → General → About

### "Provider not found" after adding

- Verify Metacache is running: `curl http://METACACHE_IP:8765/healthz`
- Check the URL is correct (use LAN IP, not localhost)
- Ensure port 8765 is not blocked by firewall

### "Metadata not refreshing"

1. Click **Refresh Metadata** on the library (not just "Scan")
2. Check Metacache logs for errors
3. Verify the provider is set as **Primary** in library settings
4. Try: Settings → Libraries → select library → **Refresh All Metadata**

### "Wrong metadata matched"

Use the **[Fix Match panel](http://METACACHE_IP:8765/ui/matches)** to pin the correct TMDB match.

### "Slow refreshes"

- Run a warm first: `POST /warm/all`
- Check the **[Warm Progress](http://METACACHE_IP:8765/ui/warm-progress)** page
- Verify the cache has items: `GET /cache/stats`

## Multiple PMS Instances

Each PMS instance needs its own Metacache registration. You can:

1. Run one Metacache for all PMS instances (they share the cache)
2. Run separate Metacache instances per PMS (isolated caches)

Option 1 is recommended — the cache is shared and warming is more efficient.

## Docker + PMS

If PMS runs in Docker:

```bash
# Use the host network for Metacache
docker run -d --name metacache --network host \
  -e Metacache__Tmdb__ApiKey=YOUR_TOKEN \
  metacache

# PMS can reach Metacache at http://host.docker.internal:8765
# Or use the host IP
```

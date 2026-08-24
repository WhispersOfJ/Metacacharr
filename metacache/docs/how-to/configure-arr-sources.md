# How to Configure ARR Sources

> Connect Radarr and Sonarr so Metacache can warm your full library inventory.

## Why Connect Radarr/Sonarr?

Without ARR sources, you can only warm individual items via webhooks. With ARR sources configured, Metacache can:
1. Fetch the complete movie/show list from Radarr/Sonarr
2. Warm every item in bulk (metadata + artwork)
3. Run nightly scheduled warm
4. Track warm progress with item counts

## Configuration

### Radarr

```bash
Metacache__Arr__RadarrUrl=http://localhost:7878
Metacache__Arr__RadarrApiKey=YOUR_RADARR_API_KEY
```

### Sonarr

```bash
Metacache__Arr__SonarrUrl=http://localhost:8989
Metacache__Arr__SonarrApiKey=YOUR_SONARR_API_KEY
```

### Concurrency

```bash
Metacache__Arr__Concurrency=4  # Parallel warm requests (default: 4)
```

### appsettings.json

```json
{
  "Metacache": {
    "Arr": {
      "RadarrUrl": "http://localhost:7878",
      "RadarrApiKey": "your-radarr-api-key",
      "SonarrUrl": "http://localhost:8989",
      "SonarrApiKey": "your-sonarr-api-key",
      "Concurrency": 4
    }
  }
}
```

## Finding Your ARR API Keys

**Radarr:** Settings → General → API Key
**Sonarr:** Settings → General → API Key

## Docker Compose Example

```yaml
services:
  metacache:
    image: metacache
    network_mode: host
    environment:
      - Metacache__Tmdb__ApiKey=${TMDB_API_KEY}
      - Metacache__Arr__RadarrUrl=http://localhost:7878
      - Metacache__Arr__RadarrApiKey=${RADARR_API_KEY}
      - Metacache__Arr__SonarrUrl=http://localhost:8989
      - Metacache__Arr__SonarrApiKey=${SONARR_API_KEY}
```

## Webhook Setup (Event-Driven Warm)

In addition to bulk warming, configure webhooks for instant warm on import:

### Radarr

1. Settings → Connect → Add → **Webhook**
2. Name: `Metacache`
3. URL: `http://METACACHE_IP:8765/webhook/radarr`
4. (If auth enabled) Add header: `X-API-Key: your-api-key`
5. Events: `Download`

### Sonarr

1. Settings → Connect → Add → **Webhook**
2. Name: `Metacache`
3. URL: `http://METACACHE_IP:8765/webhook/sonarr`
4. (If auth enabled) Add header: `X-API-Key: your-api-key`
5. Events: `Download`

## Bulk Warm Commands

```bash
# Warm movies from Radarr
curl -X POST http://localhost:8765/warm/movies

# Warm shows from Sonarr
curl -X POST http://localhost:8765/warm/shows

# Warm everything
curl -X POST http://localhost:8765/warm/all
```

## Verification

After warming, check:

```bash
# Should show warmed items
curl http://localhost:8765/cache/stats

# Check warm history
curl http://localhost:8765/warm/status
```

## Troubleshooting

**"Radarr not configured" / "Sonarr not configured":**
- The URL or API key is blank. Verify both are set.

**401 Unauthorized from Radarr/Sonarr:**
- API key is wrong. Check Settings → General in the ARR app.

**Connection refused:**
- ARR app is not running, or URL is wrong.
- If using Docker, use the host IP, not `localhost`.

**Warm takes too long:**
- Increase concurrency: `Metacache__Arr__Concurrency=8`
- Check network latency to ARR apps

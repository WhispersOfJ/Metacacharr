# Reference: Integration Points

> How Metacache connects to Radarr, Sonarr, and Plex.

## Overview

Metacache integrates with the media-stack through several channels:

1. **Direct API Calls** — Metacache queries Radarr/Sonarr for library data
2. **Webhooks** — Radarr/Sonarr/Plex notify Metacache of new imports
3. **Network Communication** — All services communicate over Docker network

## Network Configuration

All services run on the `stacknet` bridge network:

```yaml
networks:
  stacknet:
    name: stacknet
```

Services reference each other by container name:
- `http://radarr:7878` — Radarr API
- `http://sonarr:8989` — Sonarr API
- `http://metacache:8765` — Metacache API

## Radarr Integration

### Configuration

```yaml
Metacache__Radarr__Url: "http://radarr:7878"
Metacache__Radarr__ApiKey: ${RADARR_API_KEY:-}
```

### API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v3/movie` | List all movies |
| `GET /api/v3/movie/{id}` | Get movie details |
| `GET /api/v3/movie/lookup/tmdb?tmdbId={id}` | Lookup by TMDB ID |

### Webhook Integration

Radarr sends webhooks to Metacache on events:

```yaml
Webhook URL: http://metacache:8765/webhook/radarr
```

Events handled:
- `Download` — Movie downloaded
- `MovieAdded` — Movie added to library
- `MovieDeleted` — Movie removed from library

## Sonarr Integration

### Configuration

```yaml
Metacache__Sonarr__Url: "http://sonarr:8989"
Metacache__Sonarr__ApiKey: ${SONARR_API_KEY:-}
```

### API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v3/series` | List all series |
| `GET /api/v3/series/{id}` | Get series details |
| `GET /api/v3/episode` | List episodes |
| `GET /api/v3/episode/{id}` | Get episode details |

### Webhook Integration

Sonarr sends webhooks to Metacache on events:

```yaml
Webhook URL: http://metacache:8765/webhook/sonarr
```

Events handled:
- `Download` — Episode downloaded
- `SeriesAdded` — Series added to library
- `SeriesDeleted` — Series removed from library

## Plex Integration

### Configuration

Metacache registers as a Custom Metadata Provider in Plex:

```
Provider Name: Metacache
Provider URI: http://192.168.4.20:8765
```

### API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `GET /library/metadata/{id}` | Get metadata for item |
| `GET /library/sections/{id}/all` | List all items in library |

### Webhook Integration

Plex sends webhooks to the listener script:

```bash
# Plex webhook URL
http://127.0.0.1:9880/plex-webhook
```

The listener forwards to Metacache:

```python
def warm_metacache(payload):
    """Send the Plex webhook payload to Metacache for predictive warming."""
    req = urllib.request.Request(
        f"{METACACHE_URL}/webhook/plex",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10):
        pass
```

## Letterboxd Integration

### Configuration

```yaml
METACACHE_URL=http://metacache:8765
METACACHE_API_KEY=changeme
```

### Flow

1. Letterboxd list sync adds movies to Radarr
2. Control panel triggers Metacache warm
3. Metacache fetches metadata for new movies

```python
# After movies are added to Radarr
if added and not dry_run:
    httpx.post(f"{METACACHE_URL}/warm/movies", headers=headers, timeout=5.0)
```

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `METACACHE_URL` | `http://metacache:8765` | Metacache API URL |
| `METACACHE_API_KEY` | — | API key for protected endpoints |
| `RADARR_API_KEY` | — | Radarr API key |
| `SONARR_API_KEY` | — | Sonarr API key |
| `TVDB_KEY` | — | TVDB API key |
| `WARM_LANG_0` | `en-US` | Primary language for warming |

### Docker Network

```yaml
networks:
  stacknet:
    name: stacknet
```

All services must be on `stacknet` to communicate.

## Troubleshooting

**Service can't reach another service**
- Verify both are on `stacknet`: `docker network inspect media-stack_stacknet`
- Check container names match configuration
- Test connectivity: `docker exec metacache curl http://radarr:7878/ping`

**Webhook not firing**
- Check Radarr/Sonarr webhook configuration
- Verify URL uses container names (not localhost)
- Test with curl: `curl -X POST http://localhost:8765/webhook/radarr -H "Content-Type: application/json" -d '{"eventType":"Test"}'`

**API key errors**
- Verify API keys in `.env` match Radarr/Sonarr settings
- Check Metacache logs: `docker compose logs metacache`

See [Troubleshooting Guide](../how-to/troubleshoot-common-issues.md).

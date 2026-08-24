# How to Configure Bearer Token Auth

> Protect admin and webhook endpoints with API key authentication.

## When to Use Auth

By default, all endpoints are unauthenticated (backward compatible). Set an API key when:
- Metacache is exposed on a LAN with untrusted devices
- You want to prevent accidental cache purges or override changes
- Webhook endpoints should only accept requests from your ARR apps

## Configuration

### Environment variable

```bash
Metacache__Auth__ApiKey=your-secret-token-here
```

### appsettings.json

```json
{
  "Metacache": {
    "Auth": {
      "ApiKey": "your-secret-token-here"
    }
  }
}
```

## Protected Endpoints

| Endpoint | Method | Requires Auth |
|----------|--------|---------------|
| `/admin/*` | ALL | ✅ |
| `/webhook/*` | POST | ✅ |
| `POST /warm/*` | POST | ✅ |
| `GET /warm/status` | GET | ❌ |

## Unprotected Endpoints

These remain public (no auth required):

- `GET /healthz` — Liveness probe
- `GET /movie`, `GET /tv` — Provider definitions (Plex needs these)
- `GET /library/*` — Provider API (Plex needs these)
- `GET /img/*` — Image serving (Plex needs these)
- `GET /cache/stats` — Read-only stats
- `GET /metrics`, `GET /metrics/prometheus` — Monitoring
- `GET /dashboard` — Dashboard UI
- `GET /items`, `GET /guid/lookup` — Query endpoints

## Sending the Token

### Authorization header (recommended)

```bash
curl -H "Authorization: Bearer your-secret-token-here" \
     http://localhost:8765/admin/overrides
```

### X-API-Key header (for webhook callers)

Some webhook integrations don't support custom Authorization headers. Use `X-API-Key` instead:

```bash
curl -H "X-API-Key: your-secret-token-here" \
     -X POST http://localhost:8765/webhook/radarr \
     -d '{"eventType":"Download"}'
```

## Security Notes

- Key comparison is **constant-time** (`CryptographicOperations.FixedTimeEquals`) to prevent timing attacks
- The key is never logged or included in cache keys
- Empty/null key = auth disabled (backward compatible)
- Generate a strong random token: `openssl rand -hex 32`

## Configuring ARR Webhooks with Auth

When auth is enabled, update your Radarr/Sonarr webhook URLs to include the key:

**Radarr:** Settings → Connect → Edit Webhook → URL:
```
http://METACACHE:8765/webhook/radarr
```
Add header: `X-API-Key: your-secret-token-here`

**Sonarr:** Same approach with `/webhook/sonarr`

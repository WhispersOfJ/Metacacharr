# Configuration Reference

> Every configuration key with type, default, and description.

## Environment Variable Format

All config keys use double-underscore separators:
```
Metacache__Section__Key=value
```

Nested sections use additional underscores:
```
Metacache__Matching__AutoMatchThreshold=0.75
```

## Server

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `Metacache:BindAddress` | string | `127.0.0.1` | Listen address. Set to `0.0.0.0` for LAN exposure |
| `Metacache:Port` | int | `8765` | HTTP listen port |
| `Metacache:DataPath` | string | `data/metacache.db` | SQLite database path (`:memory:` for tests) |

**Env:** `Metacache__BindAddress`, `Metacache__Port`, `Metacache__DataPath`

---

## TMDB

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `Metacache:Tmdb:ApiKey` | string | *(empty)* | **Required.** API Read Access Token or legacy v3 key |
| `Metacache:Tmdb:Auth` | string | `Auto` | `Auto` probes once; force `Bearer` or `Query` |
| `Metacache:Tmdb:BaseUrl` | string | `https://api.themoviedb.org/3` | TMDB API base URL |
| `Metacache:Tmdb:ImageBaseUrl` | string | `https://image.tmdb.org/t/p/original` | TMDB image base URL |

**Env:** `Metacache__Tmdb__ApiKey`, `Metacache__Tmdb__Auth`

**Auth modes:**
- `Auto` — Probes once with Bearer, falls back to Query if rejected
- `Bearer` — Uses `Authorization: Bearer {key}` header (key never in URLs)
- `Query` — Uses `?api_key={key}` query parameter (legacy v3)

---

## TVDB

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `Metacache:Tvdb:ApiKey` | string | *(empty)* | TVDB v4 API key |
| `Metacache:Tvdb:BaseUrl` | string | `https://api4.thetvdb.com` | TVDB API base URL |

---

## ARR Sources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `Metacache:Arr:RadarrUrl` | string | *(empty)* | Radarr instance URL (blank = disabled) |
| `Metacache:Arr:RadarrApiKey` | string | *(empty)* | Radarr API key |
| `Metacache:Arr:SonarrUrl` | string | *(empty)* | Sonarr instance URL (blank = disabled) |
| `Metacache:Arr:SonarrApiKey` | string | *(empty)* | Sonarr API key |
| `Metacache:Arr:Concurrency` | int | `4` | Parallel warm requests |

---

## Warming

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `Metacache:Warm:Enabled` | bool | `true` | Nightly scheduled warm on/off |
| `Metacache:Warm:ScheduleTime` | string | `03:00` | Wall-clock time for nightly warm (`HH:mm`) |
| `Metacache:Warm:Languages` | string[] | `["en-US"]` | Languages to warm (TMDB `language` param) |

**Env:** `Metacache__Warm__Languages__0=en-US`, `Metacache__Warm__Languages__1=de-DE`

---

## Images

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `Metacache:Images:Directory` | string | `data/images` | Image cache directory |
| `Metacache:Images:MaxFileBytes` | long | `20971520` (20 MB) | Max size per image file |
| `Metacache:Images:MaxTotalBytes` | long | `10737418240` (10 GB) | Total image cache size cap |

---

## Authentication

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `Metacache:Auth:ApiKey` | string? | `null` | Bearer token. Empty = auth disabled |

**Env:** `Metacache__Auth__ApiKey=your-secret-token`

---

## ARR Proxy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `Metacache:Proxy:Enabled` | bool | `false` | Enable the ARR proxy on port 443 |
| `Metacache:Proxy:HttpPort` | int | `443` | TLS listen port |
| `Metacache:Proxy:CertDirectory` | string | `data/certs` | Certificate storage directory |
| `Metacache:Proxy:BindAddress` | string | `0.0.0.0` | Proxy listen address |

### Custom Routes

```json
{
  "Metacache": {
    "Proxy": {
      "Routes": {
        "custom.api.example.com": "https://api.example.com/v2"
      }
    }
  }
}
```

---

## Match Scoring

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `Metacache:Matching:TitleWeight` | double | `0.40` | Weight for title similarity |
| `Metacache:Matching:YearWeight` | double | `0.20` | Weight for year match |
| `Metacache:Matching:GuidWeight` | double | `0.25` | Weight for GUID match |
| `Metacache:Matching:FilenameWeight` | double | `0.15` | Weight for filename match |
| `Metacache:Matching:AutoMatchThreshold` | double | `0.75` | Minimum score for auto-match |

---

## Logging

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `Logging:LogLevel:Default` | string | `Information` | Log level |
| `Logging:LogLevel:Microsoft` | string | `Warning` | ASP.NET log level |

---

## Full Example: appsettings.json

```json
{
  "Metacache": {
    "BindAddress": "0.0.0.0",
    "Port": 8765,
    "DataPath": "data/metacache.db",
    "Tmdb": {
      "ApiKey": "your-tmdb-token",
      "Auth": "Auto"
    },
    "Tvdb": {
      "ApiKey": "your-tvdb-key"
    },
    "Arr": {
      "RadarrUrl": "http://localhost:7878",
      "RadarrApiKey": "your-radarr-key",
      "SonarrUrl": "http://localhost:8989",
      "SonarrApiKey": "your-sonarr-key",
      "Concurrency": 4
    },
    "Warm": {
      "Enabled": true,
      "ScheduleTime": "03:00",
      "Languages": ["en-US", "de-DE"]
    },
    "Images": {
      "Directory": "data/images",
      "MaxFileBytes": 20971520,
      "MaxTotalBytes": 10737418240
    },
    "Auth": {
      "ApiKey": null
    },
    "Proxy": {
      "Enabled": false,
      "HttpPort": 443,
      "CertDirectory": "data/certs"
    },
    "Matching": {
      "AutoMatchThreshold": 0.75
    }
  }
}
```

## Full Example: Docker Compose

```yaml
services:
  metacache:
    build: .
    network_mode: host
    environment:
      - Metacache__BindAddress=0.0.0.0
      - Metacache__Port=8765
      - Metacache__Tmdb__ApiKey=${TMDB_API_KEY}
      - Metacache__Tmdb__Auth=Auto
      - Metacache__Tvdb__ApiKey=${TVDB_API_KEY}
      - Metacache__Arr__RadarrUrl=http://localhost:7878
      - Metacache__Arr__RadarrApiKey=${RADARR_API_KEY}
      - Metacache__Arr__SonarrUrl=http://localhost:8989
      - Metacache__Arr__SonarrApiKey=${SONARR_API_KEY}
      - Metacache__Warm__Languages__0=en-US
      - Metacache__Warm__Languages__1=de-DE
    volumes:
      - metacache-data:/app/data
volumes:
  metacache-data:
```

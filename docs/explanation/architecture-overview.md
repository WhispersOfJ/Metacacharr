# Explanation: Architecture Overview

> How the Metacacharr unified stack fits together.

## The Big Picture

Metacacharr combines two powerful systems into a single, cohesive media stack:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Metacacharr Stack                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐   │
│  │   Prowlarr   │────▶│ Radarr/Sonarr│────▶│    NzbDAV    │   │
│  │  (Indexer)   │     │  (Manager)   │     │  (Usenet)    │   │
│  └──────────────┘     └──────┬───────┘     └──────┬───────┘   │
│                              │                     │           │
│                              ▼                     ▼           │
│                    ┌──────────────────┐    ┌──────────────┐   │
│                    │    Metacache     │◀───│    Plex      │   │
│                    │ (Metadata Cache) │    │ (Media Server)│   │
│                    └──────────────────┘    └──────────────┘   │
│                              │                     │           │
│                              ▼                     ▼           │
│                    ┌──────────────────┐    ┌──────────────┐   │
│                    │   Prometheus     │    │   Clients    │   │
│                    │   (Metrics)      │    │  (Players)   │   │
│                    └──────────────────┘    └──────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Content Acquisition Flow

```
User Request → Seerr → Radarr/Sonarr → Prowlarr → NzbDAV → Plex
                                          │
                                          ▼
                                    Upstream Indexers
```

1. User requests content via Seerr
2. Radarr/Sonarr creates a download request
3. Prowlarr searches upstream indexers
4. NzbDAV streams the content via Usenet
5. Plex serves the content to clients

### 2. Metadata Flow

```
Plex Refresh → Metacache → TMDB/TVDB → Cache → Plex
                  ▲
                  │
            Webhooks (Radarr/Sonarr/Plex)
```

1. Plex requests metadata from Metacache
2. Metacache checks local cache
3. On miss, Metacache fetches from TMDB/TVDB
4. Metacache stores result in SQLite
5. Plex receives cached metadata

### 3. Warming Flow

```
Webhook Event → Metacache → Fetch Metadata → Store in Cache
     │
     ├── Plex library.new → Warm imported item
     ├── Radarr download → Warm downloaded movie
     └── Sonarr download → Warm downloaded episode
```

## Key Components

### Metacache (C#/.NET)

The metadata cache that makes Plex refreshes fast:

- **SQLite Store** — Local database for metadata and images
- **ETag Revalidation** — Efficient upstream fetching
- **Single-Flight** — Prevents duplicate requests
- **Stale-If-Error** — Serves cached data when upstream fails
- **Image Pipeline** — Content-addressed storage with size variants

### Media-Stack (Python/Django)

The media acquisition and serving stack:

- **Control Panel** — Web UI for managing the stack
- **ARR Apps** — Radarr/Sonarr for media management
- **NzbDAV** — Usenet streaming via WebDAV
- **Plex** — Media server for content delivery
- **Monitoring** — Prometheus/Grafana for observability

## Integration Points

### 1. Plex Webhook → Metacache Warm

When Plex imports new content, it fires a `library.new` webhook. The `plex-webhook-listener.py` script forwards this to Metacache:

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

### 2. Letterboxd Sync → Metacache Warm

When movies are added from Letterboxd lists, the control panel triggers a warm:

```python
# After movies are added to Radarr
if added and not dry_run:
    httpx.post(f"{METACACHE_URL}/warm/movies", headers=headers, timeout=5.0)
```

### 3. Prometheus Scraping

Prometheus scrapes Metacache metrics:

```yaml
- job_name: "metacache"
  metrics_path: "/metrics/prometheus"
  static_configs:
    - targets: ["metacache:8765"]
```

## Network Architecture

All services communicate over the `stacknet` bridge network:

```
┌─────────────────────────────────────────────────┐
│                  stacknet                        │
├─────────────────────────────────────────────────┤
│  metacache:8765  ─────┐                         │
│  radarr:7878     ─────┼────▶  Container DNS     │
│  sonarr:8989     ─────┤      (service names)    │
│  plex:32400      ─────┤                         │
│  nzbdav:3000     ─────┘                         │
│                                                 │
└─────────────────────────────────────────────────┘
```

Services reference each other by container name (e.g., `http://radarr:7878`).

## Data Storage

### Metacache Data

```
/app/data/
├── metacache.db          # SQLite database
└── images/               # Cached artwork
    ├── <hash1>.jpg
    ├── <hash2>.png
    └── ...
```

### Media-Stack Data

```
./config/
├── plex/                 # Plex configuration
├── radarr/               # Radarr configuration
├── sonarr/               # Sonarr configuration
└── ...

./media/
├── movies/               # Movie files
├── tv/                   # TV show files
└── ...
```

## Monitoring Architecture

```
┌─────────────────────────────────────────────────┐
│                 Monitoring Stack                 │
├─────────────────────────────────────────────────┤
│                                                 │
│  Prometheus ──scrape──▶ Metacache /metrics      │
│      │                   Radarr /metrics        │
│      │                   Sonarr /metrics        │
│      │                                         │
│      ▼                                         │
│  Grafana ──query──▶ Prometheus                  │
│      │                                         │
│      ▼                                         │
│  Dashboards                                    │
│                                                 │
└─────────────────────────────────────────────────┘
```

## Security Model

- **API Key Auth** — Protected endpoints require bearer token
- **Network Isolation** — Services communicate over internal network
- **Non-Root Containers** — Most services run as non-root
- **Capability Dropping** — Containers drop all capabilities

## Scalability Considerations

- **Metacache** — SQLite handles thousands of items efficiently
- **Plex** — Scales with CPU/RAM for transcoding
- **NzbDAV** — Streams on demand, no local storage needed
- **Monitoring** — Prometheus retention limits disk usage

## Future Directions

- **Multi-Language Caching** — Cache metadata in multiple languages
- **ARR Proxy** — Transparent HTTPS proxy for Radarr/Sonarr
- **Predictive Warming** — Warm based on watch history
- **Distributed Cache** — Share cache across multiple Plex instances

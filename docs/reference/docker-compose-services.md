# Reference: Docker Compose Services

> Complete list of all services in the Metacacharr stack with ports, volumes, and dependencies.

## Service Overview

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| **metacache** | Built from source | 8765 | Metadata cache + Plex provider |
| **plex** | plexinc/pms-docker | 32400 | Media server |
| **radarr** | ghcr.io/hotio/radarr | 7878 | Movie management |
| **sonarr** | ghcr.io/hotio/sonarr | 8989 | TV show management |
| **prowlarr** | ghcr.io/hotio/prowlarr | 9696 | Indexer management |
| **nzbdav** | ghcr.io/infinidysk/infinidysk | 3000 | Usenet streaming |
| **nzbdav_rclone** | rclone/rclone | — | FUSE mount sidecar |
| **seerr** | ghcr.io/hotio/seerr | 5055 | Request management |
| **control-panel** | Built from source | 8420 | Admin dashboard |
| **watchstate** | ghcr.io/arvida42/watchstate | 8705 | Watch state sync |
| **prometheus** | prom/prometheus | 9090 | Metrics collection |
| **grafana** | grafana/grafana | 3001 | Dashboards |
| **loki** | grafana/loki | 3100 | Log aggregation |
| **promtail** | grafana/promtail | — | Log shipping |
| **cadvisor** | gcr.io/cadvisor | 8080 | Container metrics |
| **node-exporter** | prom/node-exporter | 9100 | Host metrics |
| **watchtower** | containrrr/watchtower | — | Auto-updates |
| **unpackerr** | ghcr.io/hotio/unpackerr | — | Archive extraction |
| **cleanuparr** | ghcr.io/cleanuparr/cleanuparr | 11011 | Queue cleanup |
| **nzbdav-exporter** | Built from source | 9200 | NzbDAV metrics |

## Service Details

### Metacache

The metadata cache that sits between Plex and upstream providers.

```yaml
metacache:
  build:
    context: /path/to/metacache
    dockerfile: Dockerfile
  container_name: metacache
  networks: [stacknet]
  environment:
    Metacache__BindAddress: "0.0.0.0"
    Metacache__Port: "8765"
    Metacache__DataPath: "/app/data/metacache.db"
    Metacache__Radarr__Url: "http://radarr:7878"
    Metacache__Sonarr__Url: "http://sonarr:8989"
  volumes:
    - metacache-data:/app/data
  ports:
    - "8765:8765"
```

**Health check**: `curl -sf http://localhost:8765/healthz`

### Plex

The media server that serves content to clients.

```yaml
plex:
  image: plexinc/pms-docker:latest
  container_name: plex
  networks: [stacknet]
  environment:
    PLEX_CLAIM: ${PLEX_CLAIM:-}
    ADVERTISE_IP: "http://${HOST_IP}:32400"
  volumes:
    - ./config/plex:/config
    - /mnt/remote/nzbdav:/mnt/remote/nzbdav:rslave
    - ./media:/data
  ports:
    - "32400:32400"
```

**Health check**: `curl -sf http://localhost:32400/identity`

### Radarr

Movie management and acquisition.

```yaml
radarr:
  image: ghcr.io/hotio/radarr:release
  container_name: radarr
  networks: [stacknet]
  volumes:
    - ./config/radarr:/config
    - /mnt/remote/nzbdav:/mnt/remote/nzbdav:rslave
    - ./media/movies:/data/movies
  ports:
    - "7878:7878"
```

**Health check**: `curl -sf http://localhost:7878/ping`

### Sonarr

TV show management and acquisition.

```yaml
sonarr:
  image: ghcr.io/hotio/sonarr:release
  container_name: sonarr
  networks: [stacknet]
  volumes:
    - ./config/sonarr:/config
    - /mnt/remote/nzbdav:/mnt/remote/nzbdav:rslave
    - ./media/tv:/data/tv
  ports:
    - "8989:8989"
```

**Health check**: `curl -sf http://localhost:8989/ping`

### NzbDAV

Usenet streaming via WebDAV.

```yaml
nzbdav:
  build: ./usenet/nzbdav
  container_name: nzbdav
  networks: [stacknet]
  environment:
    NZBDAV_USENET_HOST: ${NZBDAV_USENET_HOST}
    NZBDAV_USENET_PORT: ${NZBDAV_USENET_PORT}
    NZBDAV_USENET_USER: ${NZBDAV_USENET_USER}
    NZBDAV_USENET_PASS: ${NZBDAV_USENET_PASS}
  volumes:
    - ./config/nzbdav:/config
    - ./data/nzbdav:/data
  ports:
    - "3000:3000"
```

**Health check**: `curl -sf http://localhost:3000/health`

## Networks

All services communicate over the `stacknet` bridge network:

```yaml
networks:
  stacknet:
    name: stacknet
```

## Volumes

| Volume | Purpose |
|--------|---------|
| `metacache-data` | SQLite database + image cache |
| `prometheus-data` | Time-series metrics |
| `loki-data` | Log storage |

## Resource Limits

| Service | Memory | CPUs |
|---------|--------|------|
| metacache | 1g | 2 |
| plex | 4g | 4 |
| radarr | 2g | 2 |
| sonarr | 2g | 2 |
| prometheus | 1g | 2 |
| grafana | 1g | 2 |

## Common Commands

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f metacache

# Restart a service
docker compose restart metacache

# Stop all services
docker compose down

# Rebuild after changes
docker compose build metacache
docker compose up -d metacache
```

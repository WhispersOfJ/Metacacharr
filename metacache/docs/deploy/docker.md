# Deploy with Docker

> Build and run Metacache as a Docker container.

## Quick Start

```bash
# Build the image
docker build -t metacache .

# Run with your TMDB API key
docker run -d --name metacache --network host \
  -e Metacache__Tmdb__ApiKey=YOUR_TOKEN \
  metacache
```

## Dockerfile

The Dockerfile uses a multi-stage build:

```dockerfile
# Build stage
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY . .
RUN dotnet publish src/Metacache.Host -c Release -o /app/publish

# Runtime stage
FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /app/publish .
RUN adduser --disabled-password --no-create-home appuser
USER appuser
ENTRYPOINT ["dotnet", "Metacache.Host.dll"]
```

## Configuration

All configuration is via environment variables:

```bash
docker run -d --name metacache --network host \
  -e Metacache__Tmdb__ApiKey=YOUR_TOKEN \
  -e Metacache__BindAddress=0.0.0.0 \
  -e Metacache__Port=8765 \
  -e Metacache__Arr__RadarrUrl=http://localhost:7878 \
  -e Metacache__Arr__RadarrApiKey=YOUR_RADARR_KEY \
  -e Metacache__Arr__SonarrUrl=http://localhost:8989 \
  -e Metacache__Arr__SonarrApiKey=YOUR_SONARR_KEY \
  -e Metacache__Warm__Languages__0=en-US \
  -e Metacache__Warm__Languages__1=de-DE \
  metacache
```

## Persistent Data

Mount volumes for the database and images:

```bash
docker run -d --name metacache --network host \
  -v metacache-data:/app/data \
  -e Metacache__Tmdb__ApiKey=YOUR_TOKEN \
  metacache
```

Or with bind mounts:

```bash
docker run -d --name metacache --network host \
  -v /path/to/data:/app/data \
  -e Metacache__Tmdb__ApiKey=YOUR_TOKEN \
  metacache
```

## Networking

### `--network host` (recommended)

Uses the host's network stack. Required for:
- Proxy port 443 (TLS)
- Reaching Radarr/Sonarr on localhost

```bash
docker run -d --name metacache --network host metacache
```

### Custom network

If Radarr/Sonarr are in Docker containers:

```bash
docker network create metacache-net
docker run -d --name metacache --network metacache-net metacache
docker run -d --name radarr --network metacache-net radarr/radarr
# Use container names as hostnames: Metacache__Arr__RadarrUrl=http://radarr:7878
```

## Health Check

```bash
docker exec metacache curl -s http://localhost:8765/healthz
# → ok
```

## Logs

```bash
docker logs metacache
docker logs -f metacache  # Follow
```

## Updating

```bash
docker pull metacache  # Or rebuild from source
docker stop metacache
docker rm metacache
# Re-run with the same volumes
```

## Troubleshooting

**Container exits immediately:**
```bash
docker logs metacache  # Check for configuration errors
```

**Can't reach from Plex:**
- Ensure `--network host` is used
- Or use `Metacache__BindAddress=0.0.0.0`

**Permission denied on data directory:**
- The container runs as `appuser` (UID varies)
- Fix: `chown -R 1654:1654 /path/to/data`

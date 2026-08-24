# How to: Fix Volume Permissions

> Resolve SQLite and TSDB permission errors in Docker containers.

## Problem

Containers fail to start with errors like:
- `SQLite Error 14: 'unable to open database file'`
- `permission denied` on `/prometheus/queries.active`

This happens when Docker volumes are owned by root but containers run as non-root users.

## Solution

### Metacache (uid 1654)

```bash
# Stop the container
docker compose stop metacache

# Fix volume ownership
docker run --rm -v media-stack_metacache-data:/data alpine chown -R 1654:1654 /data

# Restart
docker compose start metacache
```

### Prometheus (uid 65534)

```bash
# Stop the container
docker compose stop prometheus

# Fix volume ownership
sudo chown -R 65534:65534 ./data/prometheus

# Restart
docker compose start prometheus
```

### Loki (uid 10001)

```bash
# Stop the container
docker compose stop loki

# Fix volume ownership
docker run --rm -v media-stack_loki-data:/loki alpine chown -R 10001:10001 /loki

# Restart
docker compose start loki
```

## Prevention

When creating new volumes for non-root containers, pre-create them with correct ownership:

```bash
# Create volume with correct ownership
docker volume create media-stack_metacache-data
docker run --rm -v media-stack_metacache-data:/data alpine sh -c "chown -R 1654:1654 /data"
```

## Verify

```bash
# Check container is healthy
docker ps --format "table {{.Names}}\t{{.Status}}" | grep metacache

# Check logs for errors
docker compose logs metacache | tail -20
```

## Common UIDs

| Service | UID | Container User |
|---------|-----|----------------|
| Metacache | 1654 | APP_UID (aspnet image) |
| Prometheus | 65534 | nobody |
| Loki | 10001 | loki |
| Grafana | 472 | grafana |

## Troubleshooting

**Still getting permission errors**
- Check if the volume is bind-mounted instead of named
- Verify the UID matches the container's user
- Check Dockerfile for `USER` directive

**Can't chown as non-root**
- Use `sudo` for host directories
- Use `docker run --rm` for named volumes

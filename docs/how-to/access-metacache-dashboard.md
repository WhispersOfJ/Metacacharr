# How to: Access Metacache Dashboard

> Browse cached items, trigger warm, and monitor cache status.

## Step 1: Open Dashboard

Navigate to:

```
http://localhost:8765/dashboard
```

Or from another machine:

```
http://192.168.4.20:8765/dashboard
```

## Dashboard Tabs

### Metrics Tab

- **Cache Hit Rate** — Percentage of requests served from cache
- **Upstream Requests** — Requests to TMDB/TVDB per minute
- **Disk Usage** — Space used by cached images
- **Warm Status** — Current warm progress

### Items Tab

Search and browse cached items:

- **Search** — Filter by title
- **Kind** — Filter by type (movie, show, season, episode)
- **Freshness** — Filter by cache status (fresh, stale, expired)

### Cache Tab

- **Database Info** — Entry counts and byte sizes
- **Upstream Eviction** — Items that can be evicted
- **Purge Buttons** — Remove expired or oversized entries

### Warm Tab

- **Trigger Warm** — Start movie, show, or full warm
- **Progress Bar** — Real-time warm progress
- **Activity Log** — Scrolling log of warm operations

## API Endpoints

### Get Cache Stats

```bash
curl http://localhost:8765/cache/stats
```

Response:
```json
{
  "upstreamEntries": 1234,
  "upstreamBytes": 12345678,
  "itemEntries": 5678,
  "urlEntries": 9012
}
```

### Search Items

```bash
curl "http://localhost:8765/items?q=inception&kind=movie"
```

### Trigger Warm

```bash
# Warm movies
curl -X POST http://localhost:8765/warm/movies

# Warm shows
curl -X POST http://localhost:8765/warm/shows

# Warm all
curl -X POST http://localhost:8765/warm/all
```

### Get Warm Status

```bash
curl http://localhost:8765/warm/status
```

### Purge Cache

```bash
# Purge expired
curl -X POST http://localhost:8765/cache/purge

# Purge by size
curl -X POST http://localhost:8765/admin/purge/selective \
  -H "Content-Type: application/json" \
  -d '{"imageBytes": 1073741824}'
```

## Troubleshooting

**Dashboard not loading**
- Check Metacache is running: `docker compose ps metacache`
- Verify port is exposed: `netstat -tlnp | grep 8765`
- Check logs: `docker compose logs metacache`

**No items showing**
- Run a warm: `curl -X POST http://localhost:8765/warm/all`
- Wait for warm to complete
- Check items endpoint: `curl http://localhost:8765/items`

**Slow performance**
- Check SQLite database size
- Purge old items: `curl -X POST http://localhost:8765/cache/purge`
- Monitor with Prometheus

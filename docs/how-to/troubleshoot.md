# How to Troubleshoot

> Common issues and their solutions.

## Plex Can't Find the Provider

**Symptom:** "Add Provider" doesn't show Metacache, or Plex can't connect.

**Check:**
```bash
curl http://METACACHE_IP:8765/healthz
# Should return: ok

curl http://METACACHE_IP:8765/movie
# Should return JSON with provider definition
```

**Fixes:**
- Ensure Metacache is running and accessible from the Plex machine
- Use the server's LAN IP, not `localhost` (Plex is on a different machine)
- Check firewall isn't blocking port 8765
- Verify Plex has Custom Metadata Providers enabled (PMS 1.43+)

## Metadata Not Updating

**Symptom:** Plex shows stale metadata even after refresh.

**Check:**
```bash
curl http://localhost:8765/warm/status
# Check if lastResult shows recent activity

curl http://localhost:8765/cache/stats
# Check itemEntries count
```

**Fixes:**
- Click **Refresh Metadata** in Plex (not just "Scan")
- Check Metacache logs for errors during the refresh
- Verify the provider is set as **Primary** in library settings
- Try manually warming the item: `POST /warm/movies`

## High Upstream Call Count

**Symptom:** Metrics show many cache misses.

**Check:**
```bash
curl http://localhost:8765/metrics
# Check hits vs misses
```

**Fixes:**
- Run a full warm: `POST /warm/all`
- Check if items have expired (TTL too short)
- Increase TTL in config: `Metacache:Upstream:Ttl=48:00:00`
- Configure Radarr/Sonarr for automatic warm on import

## ARR Proxy Not Working

**Symptom:** Radarr/Sonarr still hitting upstream APIs.

**Check:**
```bash
# Verify DNS override
nslookup api.themoviedb.org
# Should return Metacache IP

# Verify proxy is listening
curl -k https://localhost:443/healthz
```

**Fixes:**
- Install the CA cert (see [ARR Proxy Setup](../tutorials/05-arr-proxy-setup.md))
- Verify DNS entries point to Metacache IP
- Check proxy is enabled: `Metacache__Proxy__Enabled=true`
- Verify certificates exist: `ls data/certs/`

## Rate Limiting (429 Errors)

**Symptom:** TMDB returning 429 Too Many Requests.

**Check:**
```bash
curl http://localhost:8765/metrics/prometheus | grep rate_limit
```

**Fixes:**
- The 429 retry-with-backoff handles this automatically
- Reduce warm concurrency: `Metacache__Arr__Concurrency=2`
- Warm during off-peak hours
- Check the **[Provider Health](http://localhost:8765/ui/health)** page for latency spikes

## Image Cache Full

**Symptom:** "ImageBytes" in metrics is high, images not loading.

**Check:**
```bash
curl http://localhost:8765/admin/database
```

**Fixes:**
- Purge with size cap: `POST /admin/purge/selective {"imageBytes": 5368709120}`
- Reduce max total: `Metacache:Images:MaxTotalBytes=5368709120`
- Check image directory size: `du -sh data/images/`

## Database Locked

**Symptom:** SQLite "database is locked" errors.

**Fixes:**
- Only one Metacache instance should access the database
- Check for zombie processes: `ps aux | grep metacache`
- If using Docker, ensure the data volume is not shared between containers

## Warm Stuck at "Running"

**Symptom:** `/warm/status` shows `isRunning: true` but no progress.

**Fixes:**
- The warm gate auto-releases after a timeout
- Restart Metacache: `docker restart metacache`
- Check logs for the stuck operation
- The warm may be waiting on a slow upstream response

## Logs Not Showing

**Symptom:** No output in the Metacache console.

**Fixes:**
- Set log level: `Logging:LogLevel:Default=Information`
- Docker: `docker logs metacache`
- Check that HTTP logging is enabled (it is by default)

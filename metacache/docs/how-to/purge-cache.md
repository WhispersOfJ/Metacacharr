# How to Purge the Cache

> Remove expired entries or free disk space by purging cached data.

## Purge Expired Entries

```bash
curl -X POST http://localhost:8765/cache/purge
```

Returns:
```json
{ "removed": 42 }
```

This deletes all entries past their TTL from the `upstream_cache` table.

## Selective Purge (Advanced)

```bash
# Purge only expired entries
curl -X POST http://localhost:8765/admin/purge/selective \
  -H "Content-Type: application/json" \
  -d '{"expired": true}'

# Purge until image cache is under 5 GB
curl -X POST http://localhost:8765/admin/purge/selective \
  -H "Content-Type: application/json" \
  -d '{"imageBytes": 5368709120}'
```

## From the Dashboard

1. Open the **[Dashboard](http://METACACHE_IP:8765/dashboard)**
2. Go to the **Cache** tab
3. Click **Purge expired entries** or **Purge all upstream**

## What Gets Purged

| Data | Where | Purge behavior |
|------|-------|----------------|
| Upstream API responses | `upstream_cache` table | Expired entries deleted |
| Metadata items | `items` table | NOT purged by /cache/purge (warm repopulates) |
| Images | `data/images/` directory | Evicted by size cap (oldest first) |
| URL entries | `urls` table | Evicted when total exceeds `MaxTotalBytes` |

## Image Cache Size Cap

The image cache has two limits (configurable):
- **Per-file cap:** `Metacache:Images:MaxFileBytes` (default: 20 MB)
- **Total cap:** `Metacache:Images:MaxTotalBytes` (default: 10 GB)

When the total exceeds the cap, the oldest images are evicted first (LRU).

## Nuclear Option: Purge Everything

```bash
# Delete all upstream cache entries
curl -X POST http://localhost:8765/admin/purge/selective \
  -H "Content-Type: application/json" \
  -d '{"expired": true, "imageBytes": 0}'
```

Then re-warm:
```bash
curl -X POST http://localhost:8765/warm/all
```

## When to Purge

| Situation | Action |
|-----------|--------|
| Disk full | Purge with image cap, or reduce `MaxTotalBytes` |
| Bad metadata | Purge expired, then re-warm |
| Changing languages | Purge expired, re-warm with new language config |
| Testing | Purge all, then warm fresh |

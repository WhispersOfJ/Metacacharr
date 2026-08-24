# How to Use the Dashboard

> Navigate the 4-tab interactive dashboard for metrics, items, cache management, and warm controls.

## Accessing the Dashboard

Open in your browser:
```
http://METACACHE_IP:8765/dashboard
```

Or use the **[10 UI Pages](http://METACACHE_IP:8765/ui/setup)** for specialized views.

## Tab: Metrics

The default view shows live cache metrics (auto-refreshes every 3 seconds):

| Metric | What it means |
|--------|---------------|
| **Hit rate** | % of requests served from cache (green > 90%, red < 50%) |
| **Requests** | Total requests since startup |
| **Cache hits** | Requests served from cache |
| **Misses** | Requests that hit upstream |
| **Upstream entries** | Cached API responses |
| **Cached items** | Warmed metadata entries |

The **sparkline** shows hit rate over time, with an overlay of Prometheus scrape data.

## Tab: Items

Search the warmed cache:

1. Enter a title (e.g. "Inception")
2. Select a kind (movie/show/all)
3. Select freshness (fresh/stale/any)
4. Click **Search**

Results show: ID, kind, title, year, source, fresh/stale badge, expiry date.

## Tab: Cache

Manage the cache:

- **Database info:** Entry counts and byte sizes
- **Purge expired:** Remove all expired entries
- **Purge all:** Delete all upstream cache entries
- **Upstream entries:** Table of eviction candidates (oldest entries)

## Tab: Warm

Control cache warming:

- **Warm Movies** — Trigger Radarr warm
- **Warm Shows** — Trigger Sonarr warm
- **Warm All** — Warm everything
- **Status dot:** Running (pulsing blue) or Idle (gray)
- **Last run result:** Items, images, errors, elapsed time
- **Activity log:** Scrolling log of warm operations

## Specialized UI Pages

| Page | URL | Purpose |
|------|-----|---------|
| Setup Wizard | `/ui/setup` | Step-by-step first-time setup |
| Warm Progress | `/ui/warm-progress` | Real-time progress bar with ETA |
| Fix Match | `/ui/matches` | Visual Fix Match with TMDB candidates |
| Cache Freshness | `/ui/freshness` | Heatmap of fresh/stale/expired items |
| Cache Browser | `/ui/cache-diff` | Search with poster preview cards |
| Warm Calendar | `/ui/warm-calendar` | Warm run history and schedule |
| Provider Health | `/ui/health` | Per-provider latency sparklines |
| GUID Explorer | `/ui/guid` | Translate GUIDs across IMDB/TMDB/TVDB |
| Override Editor | `/ui/overrides` | Pin/unpin match overrides |
| Plex Registration | `/ui/register` | One-click Plex setup guide |

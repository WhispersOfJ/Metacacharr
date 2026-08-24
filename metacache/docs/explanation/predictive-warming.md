# Predictive Warming

> How Metacache uses Plex playback events to pre-warm the cache before you need it.

## The Idea

When you start watching something, you're likely to:
1. Continue watching the next episode (TV)
2. Watch something similar (movie)

Predictive warming uses this pattern to pre-fetch metadata **before** Plex needs it, making the next refresh a cache hit.

## How It Works

### Plex Webhook → Metacache

1. Plex sends a `media.play` event to `POST /webhook/plex`
2. `PlexPlayParser` extracts: kind, title, year, GUIDs, season/episode numbers
3. `CacheWarmer.WarmPredictiveAsync` resolves and warms the item + related content

### Movie Playback

```
User plays "Inception" →
  1. Resolve TMDB ID (via GUID → title match fallback)
  2. Warm the movie fully (metadata + credits + artwork)
  3. Warm top 3 similar movies (metadata + artwork, no season crawl)
```

### Episode Playback

```
User plays "Breaking Bad" S01E05 →
  1. Resolve show TMDB ID (via GUID → title match)
  2. Warm the show card (metadata + artwork)
  3. Warm the played season (all episodes)
  4. Warm the played episode + next 3 episodes (autoplay queue)
  5. If season finale: prime next season's first 2 episodes
```

### Season Finale Priming

When you play the last episode of a season:
```
Played: S01E07 (season has 7 episodes) →
  1. Warm S01E07 + S01E08... (autoplay queue)
  2. Also warm S02E01 + S02E02 (next season priming)
```

This ensures the autoplay queue crosses the season boundary without paying upstream.

## Resolution Strategy

Before warming, the played item must be resolved to a TMDB ID:

1. **GUID resolution:** Parse `imdb://`, `tmdb://`, `tvdb://` from the webhook payload
2. **Title matching:** Search TMDB by title + year
3. **Fallback:** If unresolvable, report `missing: 1` and do nothing

## Cost Budget

Predictive warming is bounded to prevent excessive upstream calls:

| Item | Calls | Why |
|------|-------|-----|
| Played movie | 3–5 | Metadata + credits + release dates |
| Similar movies (×3) | 3–5 each | Metadata + artwork only |
| Played show card | 3–5 | Metadata + artwork |
| Played season | 1 | Season metadata |
| Played episode + next 3 | 1 each | Episode metadata |
| Next season priming (×2) | 1 each | Episode metadata |

**Total per play event:** ~15–25 upstream calls (all behind existing TTLs and single-flight).

## Configuration

No configuration needed — predictive warming is enabled by default when the webhook is configured.

### Set up the Plex webhook

1. Open Plex → **Settings → Webhooks**
2. Add webhook URL: `http://METACACHE_IP:8765/webhook/plex`
3. (If auth enabled) Add header: `X-API-Key: your-api-key`

### Events handled

| Event | Action |
|-------|--------|
| `media.play` | Predictive warm (described above) |
| `media.pause` | Ignored (`{ "result": "ignored" }`) |
| `media.stop` | Ignored |
| `media.scrobble` | Ignored |
| `test` | Ignored |

## Why Not Warm Everything?

Predictive warming is selective because:
1. **Rate limits** — warming everything on every play would exhaust TMDB quotas
2. **Relevance** — you're more likely to watch related content than random content
3. **Cost** — each warm costs upstream calls + disk writes
4. **Bounded** — similar titles capped at 3, next episodes at 3, priming at 2

## Interaction with Other Warm Sources

| Source | When | Scope |
|--------|------|-------|
| **Nightly** | 03:00 daily | Full library |
| **ARR webhook** | On import | Single item |
| **Predictive** | On playback | Item + related (15–25 calls) |
| **Manual** | On demand | Full or single source |

Predictive warming fills the gap between nightly warm and real-time playback. It ensures the **next** refresh is always a cache hit, even for items that weren't in the nightly warm.

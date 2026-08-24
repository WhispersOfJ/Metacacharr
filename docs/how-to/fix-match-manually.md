# How to Fix Match Manually

> Use the Fix Match panel to pin correct TMDB matches for items that Plex matched incorrectly.

## The Problem

Sometimes Plex matches a movie or show to the wrong TMDB entry. This happens with:
- Remakes (e.g. "The Maltese Falcon" 1931 vs 1941)
- Common titles (e.g. "Alien" might match the wrong entry)
- Items with multiple versions

## Using the Fix Match UI

### 1. Open the Fix Match Panel

```
http://METACACHE_IP:8765/ui/matches
```

### 2. Search for the Correct Title

1. Enter the correct title in the search box
2. Select the kind (Movie or Show)
3. Click **Search**

You'll see TMDB candidates with posters, titles, years, and match scores.

### 3. Pin the Correct Match

Click the correct candidate. This creates a **match override** that persists in the database.

### 4. Refresh in Plex

Go back to Plex → click **Fix Match** on the item → it should now show the correct match.

## Using the API Directly

### Pin an override

```bash
curl -X POST http://localhost:8765/admin/overrides \
  -H "Content-Type: application/json" \
  -d '{"kind":"movie","target":"tmdb-movie-550","notes":"Correct match for Inception"}'
```

### List all overrides

```bash
curl http://localhost:8765/admin/overrides
```

### Remove an override

```bash
curl -X DELETE http://localhost:8765/admin/overrides/movie-inception
```

## Understanding Override Keys

Override keys are computed from the Plex match hint:
- **Movies:** `movie-{title}-{year}` (normalized)
- **Shows:** `show-{title}-{year}`
- **Seasons:** `season-{parentTitle}-{year}`
- **Episodes:** `episode-{grandparentTitle}-{year}`

When Plex sends a match request, the override is consulted **before** any upstream search. If a pin exists, it's the authoritative answer.

## Unmatched Items

Items that find zero TMDB candidates are captured automatically:

1. View unmatched: `GET /admin/unmatched`
2. Pin from unmatched: `POST /admin/unmatched/{key}/pin`
3. Or use the **[Override Editor](http://localhost:8765/ui/overrides)** for a visual interface

## How Overrides Persist

Overrides are stored in the `match_overrides` SQLite table with:
- `key` — the match hint key
- `kind` — movie/show/season/episode
- `target` — the pinned TMDB ID (e.g. `tmdb-movie-550`)
- `notes` — optional description
- `created_at` — when the pin was created

They survive restarts and are consulted on every Plex refresh.

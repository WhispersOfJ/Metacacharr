# How Match Scoring Works

> Why Metacache's scoring algorithm works the way it does.

## The Problem

Plex needs to match items from its library to the correct TMDB entry. This is surprisingly hard because:

1. **Multiple items share titles** — "The Matrix" has a movie, sequels, and a video game
2. **Titles vary** — "The Inception" vs "Inception" vs "Inception (2010)"
3. **Plex provides imperfect hints** — sometimes just a title, sometimes a GUID, sometimes a filename
4. **Different content types** — movies, shows, seasons, episodes all need different matching strategies

## Design Goals

1. **High precision for auto-match** — when confident, return one result (no Fix Match UI)
2. **Good recall for manual match** — when uncertain, show ranked candidates
3. **GUID-first resolution** — when Plex provides an IMDB/TMDB ID, use it directly
4. **Graceful degradation** — works with just a title, just a filename, or just a GUID

## Algorithm Design

### Weighted Scoring

Each match hint contributes a weighted score:

```
score = title × 0.40 + year × 0.20 + guid × 0.25 + filename × 0.15
```

**Why these weights?**
- **Title (40%):** The most reliable signal. If the title matches exactly, it's almost certainly the right item.
- **GUID (25%):** When Plex provides an external ID, it's highly reliable — but not all items have GUIDs.
- **Year (20%):** Disambiguates remakes and reboots. "Batman" (1989) ≠ "Batman" (2022).
- **Filename (15%):** Useful for library imports where Plex parses the filename. Less reliable than title.

### Threshold Design

- **Auto-match ≥ 0.75:** High confidence → return one result
- **Below 0.75:** Show Fix Match UI with ranked candidates

**Why 0.75?** Too high (0.90) → too many false negatives (real matches not auto-matched). Too low (0.60) → false positives (wrong items auto-matched). 0.75 balances precision and recall.

### Title Normalization

Raw title comparison fails because:
- "The Matrix" ≠ "matrix" (case)
- "Inception" ≠ "Inception" (accents)
- "A New Hope" ≠ "New Hope" (articles)

**Normalization pipeline:**
1. Lowercase
2. Strip articles (The, A, An) from the beginning
3. Remove accents (é → e)
4. Remove non-alphanumeric characters
5. Trim whitespace

### GUID Resolution

When Plex provides a GUID:
1. Parse the format (`imdb://`, `tmdb://`, `tvdb://`)
2. Look up the TMDB ID via the `/find` endpoint
3. If found, give a perfect score (1.0) for that GUID component
4. Other candidates get 0.0 for that GUID

**Why GUID-first?** When available, it's the most reliable signal. A movie with `imdb://tt1375666` is unambiguously Inception.

### Filename Parsing

Filenames encode metadata:
- `Inception.2010.1080p.BluRay.mkv` → title: "Inception", year: 2010
- `The.Matrix.1999.REMASTERED.720p.mkv` → title: "The Matrix", year: 1999

**Parsing rules:**
1. Split on `.` and `_`
2. Detect year (4-digit number in 1900–2099)
3. Detect resolution (1080p, 720p, etc.) — not part of title
4. Remaining tokens → title

## TV Matching

TV content adds complexity because shows have seasons and episodes.

### Season Matching

Hints: `parentTitle` (show name), `parentIndex` (season number)

1. Match show by title or GUID
2. Match season by number
3. Title similarity is a tiebreaker

### Episode Matching

Hints: `grandparentTitle` (show name), `index` (episode number), `date` (air date)

1. Match show by title or GUID
2. Match episode by number
3. Match by air date (proximity score)
4. Title similarity is a tiebreaker

### Structure-Gated Scoring

When season/episode index is provided, the scorer "gates" on structure:
- Must match the show (by title or GUID)
- Must match the season number
- Must match the episode number

This prevents a movie from matching an episode, or a show from matching a season.

## Edge Cases

### Remakes

"The Maltese Falcon" exists in 1931 and 1941. Year matching (±1 year) disambiguates:
- Plex hint: title="The Maltese Falcon", year=1941
- 1931 version: yearScore = 0.0 (mismatch)
- 1941 version: yearScore = 1.0 (exact)

### Common Titles

"Alien" has movies, TV series, and games. GUID matching (when available) is decisive:
- If Plex provides `imdb://tt0078748`, the match is unambiguous
- Without GUID, title matching returns all "Alien" entries ranked by year and popularity

### Missing Hints

When Plex provides only a title (no year, no GUID, no filename):
- titleScore is the only signal
- Other components contribute 0.50 (neutral)
- Result is the most title-similar entry

## Tuning the Algorithm

The weights and threshold are configurable:

```bash
Metacache__Matching__TitleWeight=0.50       # Increase title importance
Metacache__Matching__AutoMatchThreshold=0.80 # More conservative auto-match
```

**When to tune:**
- Too many false auto-matches → increase threshold
- Good matches not auto-matching → decrease threshold
- Year mismatches winning → increase year weight
- GUID matches ignored → ensure guidWeight ≥ 0.25

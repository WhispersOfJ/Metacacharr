# Match Scoring Reference

> Technical reference for the match scoring algorithm.

## Overview

When Plex sends a match request (auto-match or Fix Match), Metacache searches TMDB and ranks results using a weighted scoring algorithm. The score determines which result is returned as the "best match."

## Score Formula

```
score = titleScore × titleWeight
      + yearScore × yearWeight
      + guidScore × guidWeight
      + filenameScore × filenameWeight
```

## Component Scores

### Title Score (`titleWeight: 0.40`)

Measures similarity between the Plex title and TMDB result title.

| Method | Score | Example |
|--------|-------|---------|
| Exact match (case-insensitive) | 1.00 | "Inception" = "Inception" |
| Normalized match | 0.95 | "The Inception" = "Inception" |
| Contains match | 0.80 | "Inception (2010)" contains "Inception" |
| Fuzzy match (Levenshtein) | 0.0–0.7 | "Incepshun" ≈ "Inception" |
| No match | 0.00 | "Batman" ≠ "Inception" |

**Normalization:** Articles (The, A, An) are stripped, accents removed, case-insensitive.

### Year Score (`yearWeight: 0.20`)

Matches the release year.

| Condition | Score |
|-----------|-------|
| Exact year match | 1.00 |
| ±1 year | 0.50 |
| No year provided | 0.50 (neutral) |
| Year mismatch (>1 year) | 0.00 |

### GUID Score (`guidWeight: 0.25`)

Matches external GUIDs (IMDB, TMDB, TVDB).

| Condition | Score |
|-----------|-------|
| GUID matches exactly | 1.00 |
| GUID provided but no match | 0.00 |
| No GUID provided | 0.50 (neutral) |

### Filename Score (`filenameWeight: 0.15`)

Extracts title/year from the source filename and compares.

| Condition | Score |
|-----------|-------|
| Filename title matches | 1.00 |
| Filename contains title | 0.70 |
| Filename year matches | 0.50 (bonus) |
| No filename | 0.50 (neutral) |

## Thresholds

### Auto-Match Threshold (`AutoMatchThreshold: 0.75`)

- Score ≥ 0.75: Auto-match returns the single best result
- Score < 0.75: Auto-match returns empty → Plex shows Fix Match UI
- When `manual=1`: All candidates returned regardless of score

### Configuration

```bash
Metacache__Matching__AutoMatchThreshold=0.70  # Lower = more aggressive auto-match
Metacache__Matching__TitleWeight=0.50          # Increase title importance
```

## TV Season/Episode Matching

For TV content, additional hints are used:

### Season Matching
- `parentTitle` (show name) → title score
- `parentIndex` (season number) → exact match bonus

### Episode Matching
- `grandparentTitle` (show name) → title score
- `index` (episode number) → exact match bonus
- `date` (air date) → date proximity score

### Structure-Gated Scoring

When season/episode index is provided, the scorer gates on structure:
1. Must match the show (by title or GUID)
2. Must match the season number
3. Must match the episode number
4. Title similarity is a tiebreaker

## Score Output

The API returns scores as decimals (0.0–1.0):

```json
{
  "Metadata": [
    {
      "ratingKey": "tmdb-movie-550",
      "title": "Inception",
      "year": 2010,
      "score": 0.92
    },
    {
      "ratingKey": "tmdb-movie-12345",
      "title": "Inception: The Game",
      "year": 2010,
      "score": 0.45
    }
  ]
}
```

## Tuning Guide

| Symptom | Adjustment |
|---------|------------|
| Too many false auto-matches | Increase `AutoMatchThreshold` to 0.85 |
| Good matches not auto-matching | Decrease `AutoMatchThreshold` to 0.65 |
| Wrong title matching | Increase `TitleWeight`, decrease others |
| Year mismatches winning | Increase `YearWeight` |
| GUID matches ignored | Ensure `GuidWeight` is ≥ 0.25 |

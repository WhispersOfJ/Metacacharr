# Tutorial: Multi-Language Warming

> **Goal:** Configure Metacache to warm and serve metadata in multiple languages.
>
> **Time:** ~5 minutes
>
> **Prerequisites:** [Getting Started](01-getting-started.md) completed

## Why Multi-Language?

Plex serves metadata in the language your users prefer. If you have German, French, or Spanish users, warming only in English means their first refresh pays the full upstream latency for localized metadata.

Multi-language warming pre-fetches metadata in each configured language, so every Plex refresh is a cache hit regardless of language.

## Configuration

### Environment variables

```bash
# Warm in English, German, and French
Metacache__Warm__Languages__0=en-US
Metacache__Warm__Languages__1=de-DE
Metacache__Warm__Languages__2=fr-FR
```

### appsettings.json

```json
{
  "Metacache": {
    "Warm": {
      "Languages": ["en-US", "de-DE", "fr-FR"]
    }
  }
}
```

### Docker Compose

```yaml
services:
  metacache:
    image: metacache
    environment:
      - Metacache__Warm__Languages__0=en-US
      - Metacache__Warm__Languages__1=de-DE
      - Metacache__Warm__Languages__2=fr-FR
```

## How It Works

When you run a warm, Metacache:

1. For each item (movie/show/season/episode):
   - Fetches metadata from TMDB with `?language=en-US`
   - Stores as `CachedItem(id, lang="en-US")`
   - Fetches metadata from TMDB with `?language=de-DE`
   - Stores as `CachedItem(id, lang="de-DE")`
   - Fetches metadata from TMDB with `?language=fr-FR`
   - Stores as `CachedItem(id, lang="fr-FR")`
2. Artwork (posters, backdrops) is shared — images don't change per language
3. The items table uses `PRIMARY KEY (id, lang)`, so each language gets its own row

## How Plex Gets the Right Language

When Plex requests metadata, it sends `X-Plex-Language: de` (or whatever language the user selected). Metacache's provider services pass this through to the cache lookup, which retrieves the matching language variant.

If the requested language isn't cached, Metacache falls back to the TMDB API with that language parameter — it's a cache miss, but the response is still cached for next time.

## Cost vs Benefit

Each additional language approximately doubles the warm time and storage for metadata (but not for images). For a library with 500 movies:

| Languages | Warm time | Storage |
|-----------|-----------|---------|
| 1 (en-US) | ~30s | ~2 MB |
| 2 (en-US + de-DE) | ~60s | ~4 MB |
| 3 (en-US + de-DE + fr-FR) | ~90s | ~6 MB |

The benefit is that **every Plex refresh** for any language is a cache hit — no upstream calls.

## Recommended Languages

Configure the languages your Plex users actually use. Common choices:

- **English-only:** `["en-US"]` (default)
- **English + one European language:** `["en-US", "de-DE"]`
- **Multilingual household:** `["en-US", "de-DE", "fr-FR", "es-ES"]`

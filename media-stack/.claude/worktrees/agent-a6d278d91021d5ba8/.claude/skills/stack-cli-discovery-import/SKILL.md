---
name: stack-cli-discovery-import
description: Exact fish CLI command reference for IMDb/MDBList rating lookups and bulk-adding films/shows to Radarr/Sonarr from Letterboxd, MDBList, Trakt, TMDB, or generic list URLs, against this stack's Control Panel. Use whenever the user asks to add a Letterboxd film/list/watchlist/collection/filmography to Radarr, import an MDBList or Trakt list, add a TMDB studio/keyword list, add a generic hosted list as an import list, or look up a title's rating from the terminal. Trigger phrases: "add this letterboxd list to radarr", "import my letterboxd watchlist", "add this mdblist to radarr and sonarr", "what's this movie's imdb rating", "add this director's filmography", "add this trakt list to sonarr", "add this tmdb company/keyword list to radarr".
---

# Stack CLI: Discovery & List Import

<skill_scope skill="stack-cli-discovery-import">
This is a command reference, not an operational tool: it exists so the exact fish function name, argument order, flags, and known limitations for every rating-lookup and list-import terminal command in this stack are already known, without reading the fish source fresh each time. Every command here is a thin fish wrapper around Control Panel's own HTTP API (`http://192.168.4.20:8420`), which does the actual scraping/API calls server-side - no extra container is needed for any of this. The real behavior lives in `control-panel/main.py` plus `services/ratings/router.py` (rating lookups), `services/letterboxd/router.py`, and `services/arr/router.py` (`/api/mdblist/import-list` and the `add-from-letterboxd*` routes) - `app.py` is retired dead code, not the live source.
</skill_scope>

## Calling convention

<calling_convention>
The rating lookups (`stack-rating-imdb`, `stack-rating-mdblist`) are one-line `__stack_api GET <path>` calls.

Every list-import command (`stack-mdblist-import` and all `stack-letterboxd-radarr-*` commands) shares the same flag set and body shape: they use fish's `argparse` to accept `--no-search`, `--no-monitor`, `--dry-run`, and (list-shaped ones only) `--limit N`, build a JSON body (`url`/`list_url`, `search`, `monitored`, `dry_run`, optionally `limit`), and POST it via `__stack_api`. All three flags default to the safe/complete behavior when omitted: search **on**, monitored **on**, dry-run **off**. Pass `--dry-run` first when trying an unfamiliar list to see what *would* be added without writing anything.

None of these read a `STACK_HOST_IP` environment variable - the Control Panel URL is a literal hardcoded string in every function. Both rating lookups use the standalone `OMDB_KEY`/`MDBLIST_KEY` secrets already configured in this stack's `.env` - no separate account or key is needed. (These used to be read live off Kometa's own `config.yml`; promoted to standalone `.env` secrets when Kometa was removed entirely - see CLAUDE.md's History.)

The "add-a-list-source" commands (`stack-radarr-import-list`, `stack-sonarr-import-custom-list`, `stack-tmdb-import-company`, `stack-tmdb-import-keyword`, `stack-trakt-import-list`) are a simpler family than the Letterboxd ones above: each just POSTs a Radarr/Sonarr native import-list config (`implementation`, `name`, `fields`) to `/api/arr/<app>/import-list/add`, rather than scraping anything. They only take `--no-search`, not the full `--no-monitor`/`--dry-run`/`--limit` set - same on/off default (search **on** unless `--no-search` is passed), just a narrower flag set since there's no scrape step to preview with `--dry-run`. Use `stack-arr-list-implementations` (see the `stack-cli-arr-fleet` skill) to see every implementation type an app's build supports before reaching for one of these.
</calling_convention>

## Command reference

<command_reference>
| Command | Args | What it does |
|---|---|---|
| `stack-rating-imdb` | `<imdb-id>` | A title's IMDb rating via OMDb. |
| `stack-rating-mdblist` | `<imdb-id>` | A title's MDBList score, plus its IMDb sub-rating if MDBList has one. |
| `stack-mdblist-import` | `<mdblist-list-url> [--no-search] [--no-monitor] [--dry-run] [--limit N]` | Imports an MDBList list, routing movies to Radarr and TV shows to Sonarr in one call. Works on any public MDBList list, including their mirrors of common IMDb lists (search mdblist.com for e.g. "imdb top 250") - this is the workaround for the fact that IMDb's own list pages sit behind a Cloudflare-class bot challenge and can't be scraped directly. |
| `stack-radarr-import-list` | `<list-url> <display-name> [--no-search]` | Adds a hosted Radarr-list-format JSON URL as a Radarr import list (`RadarrListImport`) - community-curated lists published in that exact schema, distinct from `stack-sonarr-import-custom-list`'s generic form. |
| `stack-sonarr-import-custom-list` | `<base-url> <display-name> [--no-search]` | Adds a generic JSON/RSS feed as a Sonarr import list (`CustomImport`) - for any curated series list hosted as a URL that isn't covered by a dedicated implementation (Trakt/IMDb/Plex/Simkl). |
| `stack-tmdb-import-company` | `<tmdb-company-id> <display-name> [--no-search]` | Adds a studio's filmography as a Radarr import list (`TMDbCompanyImport`) - find the company id from a TMDB URL like `themoviedb.org/company/2` (A24). |
| `stack-tmdb-import-keyword` | `<tmdb-keyword-id> <display-name> [--no-search]` | Adds a TMDB keyword-filtered list as a Radarr import list (`TMDbKeywordImport`) - e.g. keyword id 4565 is "time travel". Find ids via a movie page's Keywords section (no public numeric-lookup UI on TMDB). |
| `stack-trakt-import-list` | `<radarr\|sonarr> <trakt-username> <trakt-listname> <display-name> [--no-search]` | Adds a public Trakt list as an import list (`TraktListImport`). Reuses whichever app already has a Trakt OAuth token from an existing list (this stack's Radarr has DCAU/DCEU lists, Sonarr has Top250TV/True Crime already authenticated) - no fresh "Authenticate with Trakt" pass needed unless neither app has one yet, in which case add one list manually through the app's own UI first and every command here can piggyback on it after. |
| `stack-letterboxd-radarr` | `<film-url> [--no-search] [--no-monitor] [--dry-run]` | Scrapes one film's TMDb id off its Letterboxd page and adds it to Radarr. |
| `stack-letterboxd-radarr-list` | `<list-url> [--no-search] [--no-monitor] [--limit N] [--dry-run]` | Same technique applied to a custom list (`letterboxd.com/<user>/list/<slug>/`) - scrapes every film's slug off the paginated grid (max 10 pages / 720 films), then each film's own page for its TMDb id. |
| `stack-letterboxd-radarr-watchlist` | `<user-watchlist-url> [--no-search] [--no-monitor] [--limit N] [--dry-run]` | Same technique applied to a user's watchlist. |
| `stack-letterboxd-radarr-watched` | `<user-films-url> [--no-search] [--no-monitor] [--limit N] [--dry-run]` | Same technique applied to a user's watched-films page. |
| `stack-letterboxd-radarr-collection` | `<collection-url> [--no-search] [--no-monitor] [--limit N] [--dry-run]` | Same technique applied to a film collection (`letterboxd.com/films/in/<slug>/`). **Known limitation:** this specific path is gated by an actual Cloudflare JS challenge, not just header sniffing - confirmed live, a bare user-agent gets a real "Just a moment..." page. A full browser-shaped header set passes most of the time but not reliably; an intermittent fetch failure here is this known issue, not a bug in the command - retry. |
| `stack-letterboxd-radarr-filmography` | `<role> <slug> [--no-search] [--no-monitor] [--limit N] [--dry-run]` | Adds a person's whole filmography by crew role (`actor`, `director`, `writer`, `producer`, `editor`, `cinematography`, `composer`, and others - roles aren't hardcoded, an unrecognized one just 404s with a clear error). Builds `letterboxd.com/<role>/<slug>/`. |
| `stack-letterboxd-radarr-popular` | `[--no-search] [--no-monitor] [--limit N] [--dry-run]` | **Confirmed broken, left in place deliberately.** `letterboxd.com/films/popular/`'s poster grid is pure client-side JS hydration - the server-rendered HTML has zero film data at any header combination tried, unlike every other Letterboxd grid this technique covers. This command will currently always report "no films found." It's kept rather than silently pointed at a different page, so the failure is honest instead of quietly returning the wrong list - don't suggest running it expecting real results, and don't treat a "no films found" report from it as a sign something else is broken. |
| `stack-letterboxd-radarr-list-random` | `[--no-search] [--no-monitor] [--limit N] [--dry-run]` | Picks one random URL from a locally cached pool of Letterboxd's own featured lists (`~/.cache/letterboxd_lists.txt`, built by `scripts/scrape_letterboxd.py` off `letterboxd.com/lists/featured/`), removes it from the cache so a future run won't repeat it, then runs `stack-letterboxd-radarr-list` against it to completion, tailing Control Panel's live per-film progress log while it runs. All flags pass straight through. Runs the scraper automatically first if the cache file doesn't exist yet. |
</command_reference>

## Common mistakes

<common_mistakes>
<general_anti_patterns>
- **Running `stack-letterboxd-radarr-popular` expecting real results.** It's a confirmed, permanent limitation of that specific Letterboxd page (client-side rendering), not an intermittent bug - don't retry it hoping for a different outcome, and don't burn time debugging Control Panel's scraper against it.
- **Reading an intermittent failure from `stack-letterboxd-radarr-collection` as a real bug.** That specific `/films/in/` path is Cloudflare-challenge-gated; a failure there is expected some fraction of the time and worth a simple retry before investigating further.
- **Forgetting `--dry-run` exists before running an unfamiliar list against Radarr for real.** Every list-import command supports it - use it first on any list whose size or content isn't already known, especially before a whole filmography or a large custom list.
- **Assuming these commands need a separate scraping container or credentials.** All scraping and TMDb-id resolution happens server-side in Control Panel using the standalone `OMDB_KEY`/`MDBLIST_KEY` `.env` secrets - there's nothing else to set up or authenticate.
- **Expecting `--dry-run`/`--no-monitor`/`--limit` on the add-a-list-source commands.** `stack-radarr-import-list`, `stack-sonarr-import-custom-list`, `stack-tmdb-import-company`, `stack-tmdb-import-keyword`, and `stack-trakt-import-list` only accept `--no-search` - they register a native import-list config for the app to pull on its own schedule, there's nothing to scrape/preview up front.
- **Running `stack-trakt-import-list` expecting it to authenticate Trakt for you.** It reuses an existing OAuth token already on the target app; if neither Radarr nor Sonarr has ever authenticated with Trakt, add one list manually in that app's UI first.
</general_anti_patterns>
</common_mistakes>

## Resources

<resources>
**Local:**
- `~/.config/fish/functions/stack-rating-*.fish`, `stack-mdblist-import.fish`, `stack-letterboxd-radarr*.fish`, `stack-radarr-import-list.fish`, `stack-sonarr-import-custom-list.fish`, `stack-tmdb-import-company.fish`, `stack-tmdb-import-keyword.fish`, `stack-trakt-import-list.fish` - the actual fish source these commands wrap
- `scripts/scrape_letterboxd.py` in this repo - builds the featured-lists cache `stack-letterboxd-radarr-list-random` draws from
- `control-panel/main.py` + `services/ratings/router.py`, `services/letterboxd/router.py`, `services/arr/router.py` in this repo - the real behavior behind every endpoint these commands call
</resources>

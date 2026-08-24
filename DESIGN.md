# Metacache — Design Document

An ARR-app companion that caches metadata locally so Plex (and the ARR apps) update from
a fast local server instead of hammering external providers.

**Status:** Draft v1 — August 2026
**Language:** C# / .NET (rationale in §9)

---

## 1. TL;DR

The idea — "cache TMDB/TVDB metadata on a local server so Plex refreshes from there" —
is not only feasible, it got *dramatically easier* in December 2025: **Plex added native
support for Custom Metadata Providers** (PMS 1.43+). A provider is just an HTTP API.
You add its URL in Plex (Settings → Metadata Agents → Add Provider), pick it as the
agent for a library, and Plex pulls *all* matching + metadata + artwork from your server.
No DNS hijacking, no MITM, no cert tricks — for Plex.

So the design is one local service with two faces:

1. **Plex face (primary):** a native Plex metadata provider that answers Plex's match and
   metadata requests out of a local cache.
2. **ARR face (in scope):** a caching reverse proxy for the domains Sonarr/Radarr/Lidarr
   hit directly (`api.themoviedb.org`, `image.tmdb.org`, `api.thetvdb.com`,
   `webservice.fanart.tv`), reached via a DNS/hosts override. This is the classic
   "cache proxy" pattern, needed only because the ARR apps don't have a pluggable
   metadata backend the way Plex now does.

Everything (provider lookups, proxy fetches) reads/writes the same shared local cache, so
Plex scans, ARR imports, and UI art all hit the LAN instead of the internet.

### Existing work to study first

| Project | What it is | Relevance |
|---|---|---|
| `plexinc/tmdb-example-provider` | Official Plex example provider (TypeScript, TV only) | Reference implementation of the provider API — read before writing code |
| `developer.plex.tv/pms` → "Metadata Providers" | Official API docs | The contract (§6) |
| `Drewpeifer/plex-meta-tvdb` | Community TVDB provider (archived) | Second example of the API |
| `daemosofchaos/PlexModernMetadataProvider` | **C#/.NET 10** provider for Plex | Validates C# as a stack; movie matching ideas |
| `Glossarr` | Proxy that intercepts metadata requests for translation | Proof that intercepting ARR/Plex metadata traffic works in practice |

---

## 2. Why do this? (goals)

- **Faster scans/refreshes:** LAN latency (sub-ms) instead of WAN round-trips; repeated
  refreshes of the same item are served from disk without touching the internet.
- **Rate-limit immunity:** TMDB (~50 req/s burst) and TVDB (now paid, rate-limited) stop
  being a bottleneck; a full library refresh becomes a handful of upstream calls.
- **Offline resilience:** metadata and art keep working when the WAN link is down.
- **Determinism:** your metadata no longer changes under you when providers edit records
  or change API behavior; you control TTLs and can pin versions.
- **Privacy:** Plex/ARR no longer phone metadata providers for every item in your library.

Non-goals: not a metadata *editor*, not a replacement for Plex Meta Manager (collections/
overlays), not a piracy-adjacent tool. Movies + TV first; music comes later (Plex hasn't
shipped provider support for music libraries yet).

---

## 3. Architecture overview

```
┌─────────────┐   provider API (HTTP)   ┌───────────────────────────────┐
│  Plex Media │ ───────────────────────▶│  Metacache                    │
│  Server     │ ◀───────────────────────│                               │
└─────────────┘                         │  ┌─────────────────────────┐  │
                                        │  │ Provider API (Plex)     │  │
┌─────────────┐   DNS override + HTTPS  │  │  /movie  /tv            │  │
│ Sonarr      │ ───────────────────────▶│  │  match, metadata,       │  │
│ Radarr      │ ◀───────────────────────│  │  children, images       │  │
│ Lidarr ...  │                         │  ├─────────────────────────┤  │
└─────────────┘                         │  │ Reverse proxy (ARR)     │  │
                                        │  │  api.tmdb.org,          │  │
                                        │  │  image.tmdb.org, ...    │  │
                                        │  ├─────────────────────────┤  │
                                        │  │ Cache core              │  │
                                        │  │  SQLite (JSON)          │  │
                                        │  │  image files (disk)     │  │
                                        │  │  TTL / revalidate       │  │
                                        │  ├─────────────────────────┤  │
                                        │  │ Warm-up worker          │  │
                                        │  │  ← Sonarr/Radarr API    │  │
                                        │  ├─────────────────────────┤  │
                                        │  │ Admin API + dashboard   │  │
                                        │  └─────────────────────────┘  │
                                        └───────────────────────────────┘
                                                  │ upstream (only on
                                                  │ cache miss)
                                                  ▼
                                        TMDB · TVDB · Fanart.tv · IMDb
```

Data flow for a Plex library refresh: Plex scans files → POSTs a **match** request
(title/year/filename hints) → Metacache searches TMDB via the cache → returns the best
candidate with external GUIDs (`imdb://…`, `tmdb://…`, `tvdb://…`) → Plex stores the GUID →
GETs **metadata** by rating key (seasons/episodes via `/children`) → Metacache synthesizes
the Plex JSON from cached upstream data → artwork URLs in the response point back at
Metacache's own image endpoint → Plex pulls posters/backdrops from the LAN. Everything
after the first match is served entirely from the local cache.

---

## 4. The key discovery: Plex Custom Metadata Providers

Plex announced Custom Metadata Providers on 2025-12-09 (PMS 1.43+, beta at the time;
legacy agent system is slated for full removal in 2026). The essentials:

- A **metadata provider** is any HTTP API returning metadata in Plex's standardized
  JSON format. It must expose:
  - `GET /movie` and/or `GET /tv` → the **MediaProvider definition** (identifier,
    title, version, supported Types, and Feature endpoints).
  - A **metadata** feature: `GET <key>/<ratingKey>` (plus `/children`,
    `/grandchildren`, `/images`).
  - A **match** feature: `POST <key>` for search/matching.
  - Optional **collection** feature (movie libraries).
- Providers are **unauthenticated** today; only Movie and TV libraries are supported
  (music later). Language/country arrive via `X-Plex-Language` / `X-Plex-Country`
  headers or query params.
- Users install a provider by pasting its URL into Settings → Metadata Agents →
  Add Provider, then compose one or more providers into an **agent**.

Implications for this project:

1. **No TLS/CA/DNS hacks for Plex.** The provider just needs to be reachable over HTTP
   on the LAN. (Bind to the LAN interface, not 0.0.0.0, since there's no auth yet.)
2. **Future-proof:** the legacy agent system dies in 2026; writing a provider now is
   the only path that keeps working.
3. **The API is young.** Plex explicitly warns of bugs and missing features. Keep the
   provider-schema mapping in one isolated module so churn is cheap (§11, mapper).

---

## 5. Provider identity & IDs

- **Identifier:** must start with `tv.plex.agents.custom.`; suffix only
  `[a-zA-Z0-9.]`; keep it unique. Use e.g.
  `tv.plex.agents.custom.metacache.movie` and `tv.plex.agents.custom.metacache.tv`.
- **GUIDs:** every item carries `{identifier}://{type}/{ratingKey}`, e.g.
  `tv.plex.agents.custom.metacache.tv://show/tmdb-show-15260`.
- **Rating keys:** `[a-zA-Z0-9_-]` only, no slashes (they become part of the GUID).
  Proposed scheme (embed the source ID + indices, parseable with one regex):

  | Type | Rating key | Example |
  |---|---|---|
  | Movie | `tmdb-movie-{tmdbId}` | `tmdb-movie-19934` |
  | Show | `tmdb-show-{tmdbId}` | `tmdb-show-15260` |
  | Season | `tmdb-season-{tmdbId}-{n}` | `tmdb-season-4020-1` |
  | Episode | `tmdb-episode-{tmdbId}-{s}-{e}` | `tmdb-episode-4020-1-1` |
  | Collection | `tmdb-collection-{id}` | `tmdb-collection-9488` |

  (TVDB-only shows should still be resolvable: keep a `tvdbId` column and synthesize
  `tvdb-show-{id}` keys for those, or normalize through TMDB where possible.)

**Hybrid sources (TMDB + TVDB, confirmed):** TMDB is the primary source — best API,
free, no rate-limit pain. TVDB augments it: external-ID bridging, content ratings,
alternate episode orders, and coverage of shows TMDB is missing. Every item row in the
cache stores both `tmdbId` and `tvdbId` so either provider can be the lookup origin
(§7.4 schema already carries `source`/`source_id`).

---

## 6. Provider API contract (what to implement)

### 6.1 Provider definitions

`GET /movie` and `GET /tv` return:

```json
{
  "MediaProvider": {
    "identifier": "tv.plex.agents.custom.metacache.movie",
    "title": "Metacache Movie Provider",
    "version": "1.0.0",
    "Types": [
      { "type": 1, "Scheme": [ { "scheme": "tv.plex.agents.custom.metacache.movie" } ] }
    ],
    "Feature": [
      { "type": "metadata", "key": "/library/metadata" },
      { "type": "match",    "key": "/library/metadata/matches" },
      { "type": "collection","key": "/library/collections" }
    ]
  }
}
```

Types: `1=movie, 2=show, 3=season, 4=episode, 18=collection`. Plex recommends **one
provider per parent type** (separate movie and TV providers) so agents can combine them
freely — follow that recommendation.

### 6.2 Metadata feature

- `GET /library/metadata/{ratingKey}` → `MediaContainer` with one `Metadata` object.
  - `includeChildren=1` (required support for shows/seasons) → include `Children`.
  - `episodeOrder` → honor alternate season orderings (TMDB episode groups).
- `GET /library/metadata/{ratingKey}/children` and `/grandchildren` → paged lists.
  **Paging is mandatory here** via `X-Plex-Container-Size` / `X-Plex-Container-Start`
  (default page size 20, start index 1); `totalSize` = all, `size` = this page.
- `GET /library/metadata/{ratingKey}/images` → recommended; returns all available
  image assets (coverPoster, background, backgroundSquare, clearLogo, snapshot).
- Return codes: `200` / `404` (unknown rating key) / `400` / `500`.
- Response-customization params (`includeFields`, `excludeElements`, …) are optional
  to support; the match endpoint benefits most (smaller responses). Support them —
  Plex sends them and they cut bandwidth.

### 6.3 Match feature

`POST /library/metadata/matches` — body fields (type is required; everything else
depends on type):

| Field | For types | Notes |
|---|---|---|
| `type` | all | 1/2/3/4 |
| `title` | movie, show | |
| `parentTitle` | season | |
| `grandparentTitle` | episode | |
| `year` | movie, show | optional |
| `guid` | all | external id, e.g. `tvdb://152831` — use it for exact pinning |
| `index` | season/episode | |
| `parentIndex` | episode | |
| `date` | episode | air date, used when indices absent |
| `filename` | all | relative file path — use for filename heuristics |
| `manual` | all | `1` → return ranked list for "Fix Match"; `0`/absent → best single result |
| `includeAdult` | all | filter adult content unless `1` |

Response is a `MediaContainer.Metadata[]` — best match first. Include `Guid[]`
(imdb/tmdb/tvdb ids) on results so Plex can pin subsequent refreshes without re-searching.

**Matching strategy (movies/shows):** TMDB search by title+year (cached); score by year
distance, title similarity (normalize punctuation/articles), filename hints; prefer
exact external-ID hits when `guid` is supplied; return the top candidate. For episodes,
match by `parentIndex`/`index` (or air `date`) against the already-pinned show — this is
why the show's season/episode structure must be cached eagerly (§8).

### 6.4 Metadata object shape (what to synthesize)

Per `Metadata.md` in the example repo: `ratingKey`, `key`, `guid`, `type`, `title`,
`originallyAvailableAt`, `thumb`, `art`, plus `Image[]` (recommend coverPoster +
background + clearLogo + backgroundSquare), `Genre[]`, `Guid[]`, `Rating[]`
(imdb/tmdb/rotten-tomatoes image ids), `Role[]/Director[]/Producer[]/Writer[]`,
`Country[]`, `Studio[]`, `Network[]` (TV), `Collection[]` (movies, if the collection
feature is advertised), `SeasonType[]` (alternate orders), and parent/grandparent
attributes for seasons/episodes. **All `url` fields must point back at Metacache's own
image endpoint** (see §7.3) so Plex never fetches art from the internet.

---

## 7. Caching design

### 7.1 Layers

1. **Synthesized provider responses** (the Plex JSON we return) — cheap to rebuild;
   cache briefly (or not at all) — they're derived from layer 2.
2. **Normalized upstream metadata** — the item store: movies/shows/seasons/episodes/
   people/collections as structured rows keyed by provider ID, with language variants.
   This is the real cache. TTL + ETag revalidation.
3. **Raw upstream HTTP** (for the ARR proxy face) — pass-through cache of provider API
   JSON keyed by URL.
4. **Images** — content-addressed files on disk.

### 7.2 Cache keys & TTLs

- Cache key = SHA-256 of the normalized URL (scheme + host + path + sorted query),
  optionally including the language/country tag so `de-DE` and `en-US` don't collide.
  Strip API keys from the key (and from logs).
- **TTL table** (start values; make per-provider configurable):

| Source | Content | TTL | Revalidation |
|---|---|---|---|
| TMDB API | item JSON | 24 h | ETag / Last-Modified → 304 |
| TMDB images | jpg/png | 30 d | none (URLs are content-addressed upstream) |
| TVDB API | item JSON | 24–48 h | ETag |
| Fanart.tv | art | 7 d | none |
| Search/match responses | list JSON | 12 h | none |
| Synthesized Plex JSON | derived | 1 h | n/a (rebuilt from item store) |

- **Stale-if-error:** serve stale entries when upstream 5xx / timeout / offline — this
  is what makes "internet down but library works" true.
- **429 handling:** honor `Retry-After`, back off per host, never thundering-herd —
  single-flight per key (only one in-flight upstream request per key; others await it).

### 7.3 Image endpoint

Upstream image URLs (e.g. `https://image.tmdb.org/t/p/original/qk3eQ8…jpg`) are rewritten
to `http://{host}:{port}/img/{sha256-of-original-url}`. On miss, Metacache fetches the
image from upstream and stores it (per-file cap, default 20 MB); on hit, it's a local
file read (range-request aware). Plex's UI then loads every poster/backdrop from the LAN.
Filenames keep no upstream host/API info → cache stays private.

**Shipped (implementation notes):** `ImageStore` keeps extensionless content-addressed
files at `{dir}/{first2}/{sha256}`, written atomically; content type is derived from the
original URL, which is recorded in the `urls` table. `ImageCache` single-flights fetches
and enforces a total-bytes cap (default 10 GB) by evicting oldest-first. Images are
treated as immutable (no TTL) — bounded by the caps instead. `/img/{hash}` refetches
when the URL is known but the file is missing, and 404s for unknown/invalid hashes.

### 7.4 Storage

- **SQLite** (`metacache.db`): item store, cache index, stats. One file, zero ops,
  plenty for hundreds of thousands of items. WAL mode.
  - Sketch (implemented as `Metacache.Core/Cache/CacheStore.cs`; schema versioned via
    `PRAGMA user_version`, timestamps persisted as ISO-8601 UTC):
    ```sql
    items(id TEXT, kind TEXT, source TEXT, source_id TEXT, lang TEXT,
          json TEXT, fetched_at TEXT, expires_at TEXT, etag TEXT,
          PRIMARY KEY (id, lang))        -- one row per language variant
    upstream_cache(key TEXT PRIMARY KEY, -- sha256 of URL
          url TEXT, status INT, content_type TEXT, body BLOB,
          fetched_at TEXT, expires_at TEXT, etag TEXT, last_modified TEXT, hits INT)
    urls(id TEXT PRIMARY KEY,            -- sha256 of original URL
          url TEXT, path TEXT,           -- path to image file
          size INT, fetched_at TEXT)
    ```
  - Indexes on `(source, source_id)`, `(kind, lang)`, `upstream_cache(expires_at)`.
- **Image store:** `images/ab/cdef1234…` content-addressed files.
- Sizing: a 2,000-movie library ≈ 4–8 GB of images + < 200 MB of JSON. Fine on any NAS.

---

## 8. Cache warming (the "companion" part)

**Shipped as M3 (§18).** The cache is most valuable when it's *already full* before
Plex asks. Warm it from the ARR apps themselves:

- **Radarr:** `GET /api/v3/movie` (API key via header) → tmdbIds of everything in your
  movie library → prefetch movie metadata + images + collections.
- **Sonarr:** `GET /api/v3/series` → tvdbIds → prefetch show, all seasons, all episodes,
  episode stills, alternate episode orders.
- **Lidarr** (once Plex supports music providers) and **Prowlarr** are future warmers.
- Also warm searchable headspace: TMDB trending/popular pages so "Fix Match" on a new
  file often hits cache.
- Schedule: nightly incremental + event-driven (watch the ARR apps' webhooks/API for
  new imports). A single full warm of a big library is a few thousand upstream requests;
  at TMDB's 50 rps that's minutes — and it only happens once.

This turns the ARR apps' existing databases into the *inventory* and Metacache into the
*pantry*: everything Plex will ever ask for is already local.

---

## 9. Language choice: C# / .NET (and why not C or C++)

**Recommendation: C# on .NET (8+, current LTS).** Reasons:

1. **First-class HTTP server** — Kestrel (ASP.NET Core) handles the provider API, the
   proxy, and the dashboard with zero native dependencies. Writing an HTTP proxy is
   ~100 lines, not a project.
2. **`HttpClient` + `SocketsHttpHandler`** gives pooled connections, retries, redirects,
   and TLS for upstream calls out of the box.
3. **SQLite** via `Microsoft.Data.Sqlite` (or EF Core if you want migrations) — no server,
   runs on any NAS.
4. **Cross-platform + tiny deploy** — single self-contained binary or Docker image on
   Linux/Windows/macOS/Synology; runs fine on the same box as Plex.
5. **Background services** (`IHostedService`) are the natural fit for the warmer and
   revalidation loops.
6. **Proof in the space:** `PlexModernMetadataProvider` is already a C#/.NET 10 Plex
   provider; Plex's own docs explicitly say "any language that can serve an HTTP API."
7. **Team velocity:** JSON serialization, testing (xUnit), and dependency management
   (NuGet) are boring and reliable — important when the provider schema is still moving.

**C++** is viable (cpp-httplib or Boost.Beast + libcurl + SQLite) but you'll spend most
of your effort on plumbing (HTTP parsing edge cases, TLS, JSON, pooling, packaging) that
.NET gives you free. Choose C++ only if you have a hard constraint (existing C++ codebase,
minimal-runtime deployment on weird hardware). **C** is not a sensible choice here:
HTTP/TLS/JSON in C is a maintenance burden with no payoff for a LAN metadata service.

If you're set on C++, use `cpp-httplib` for the server, `libcurl` for upstream, `nlohmann/json`,
`SQLite3` directly, and accept a slower build. The architecture in this doc is
language-agnostic either way.

---

## 10. The ARR proxy face (DNS override) — in scope

Sonarr/Radarr hardcode their metadata endpoints — no pluggable backend. To make them
consume the cache too:

- Run the same service on a second port (e.g. 443) as a **transparent caching reverse
  proxy** for `api.themoviedb.org`, `image.tmdb.org`, `api.thetvdb.com`,
  `webservice.fanart.tv`, and whatever else the ARR apps call.
- Override DNS for those hosts to the Metacache host:
  - Same machine: `/etc/hosts` (or `extra_hosts` in Docker Compose).
  - LAN-wide: Pi-hole / AdGuard Home custom DNS entries.
- **TLS is the catch:** the apps will use HTTPS with SNI for those real domains. The
  proxy must terminate TLS with certificates for those exact hostnames, signed by a
  **local CA** you generate (e.g. with `mkcert`) and install into the trust store of
  the hosts running the ARR apps / Plex. No pinning is known on these providers'
  endpoints, so this works — but it is the fiddliest part, and it's optional.

The provider face lands first (M1–M3); the proxy face lands in M4 for full offline
behavior. Until then the ARR apps keep using the internet for their own calls (imports,
UI art) while Plex still gets everything from the cache.

---

## 11. Project layout (C#)

```
Metacache.sln
├── src/
│   ├── Metacache.Core/          # domain models, cache core, TTL logic, rate limiter
│   │   ├── Cache/               # SQLite store, image store, single-flight
│   │   ├── Providers/           # TMDB client, TVDB client (typed, cached)
│   │   └── Matching/            # match scoring, title normalization
│   ├── Metacache.Plex/          # provider API: definitions, match, metadata,
│   │   │                        # children, images, collections (the mapper lives
│   │   │                        # here, isolated — the one place that touches
│   │   │                        # Plex's schema)
│   │   └── Mappers/
│   ├── Metacache.Proxy/         # ARR-facing reverse proxy + DNS-cert handling
│   ├── Metacache.Warmer/        # Sonarr/Radarr sync + prefetch jobs
│   ├── Metacache.Api/           # admin API, metrics (Prometheus), purge, dashboard
│   └── Metacache.Host/          # ASP.NET host, config, DI, Docker entrypoint
└── tests/
    ├── Metacache.Core.Tests/
    ├── Metacache.Plex.Tests/    # golden-file tests against Plex schema examples
    └── Metacache.Matching.Tests/
```

**Hard rule:** only `Metacache.Plex/Mappers` serializes to Plex's provider schema. When
Plex changes the API (it will — it's brand new), you change one folder.

---

## 12. Milestones

- **M0 — Skeleton:** .NET host, `/movie` + `/tv` provider definitions, health endpoint,
  Docker + Compose, config. *Definition of done:* Plex "Add Provider" accepts the URL
  and shows the provider; requests log. **Shipped.** Cache core (SQLite store,
  single-flight, ETag revalidation, stale-if-error) also shipped as M1 groundwork.
- **M1 — Movies:** match + metadata for movie libraries; GUIDs; image rewriting through
  the local endpoint; SQLite cache with TTL + ETag revalidation; 404/400 semantics.
  *DoD:* create a movie library using the provider; "Fix Match" finds films; refresh
  shows two upstream calls total. **Shipped** — see §16.
- **M2 — TV:** shows/seasons/episodes; `/children` + `/grandchildren` with paging;
  episode matching by index and air date; localization (X-Plex-Language); content
  ratings by country; alternate episode orders. *DoD:* a TV library works end to end
  with correct episode matching on re-scans. **Shipped** — see §17 (alternate
  episode orders still deferred).
- **M3 — Companion features:** Sonarr/Radarr warm-up jobs; metrics + dashboard
  (hit rate, per-provider counts, disk usage); manual purge + TTL tuning; stale-if-error
  offline mode. *DoD:* unplug the WAN and a full library refresh still completes.
  **Shipped** — see §18 (dashboard UI and the remaining tuning knobs still to come).
- **M4 — ARR proxy face:** transparent caching reverse proxy for
  `api.themoviedb.org`/`image.tmdb.org`/`api.thetvdb.com`/`webservice.fanart.tv` with
  DNS override (§10); local CA + per-hostname certs; multi-language warm; music
  provider when Plex ships it.

---

## 13. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Provider API is new; schema churn | Isolate all Plex serialization in `Mappers`; golden-file tests; pin against the example repo's `Metadata.md` |
| Legacy agents removed in 2026 | Custom providers are the replacement path — being early is an advantage |
| No auth on providers yet | Bind to LAN; firewall port; add API-key auth in front once Plex ships it |
| Matching quality (Plex "Fix Match") | Return rich `Guid[]`; support manual search ranked lists; filename heuristics; watch Plex forums for matching feedback |
| Provider ToS (TMDB/TVDB caching rules) | Personal, non-redistributed caching for a private library is the intended scope; don't ship caches to others; check current ToS before any public distribution |
| Rate limits during initial warm | Single-flight + per-host rate limiter + Retry-After handling; warm off-peak |
| TVDB went paid / rate-limited | Prefer TMDB as primary source; keep TVDB only as an ID bridge where needed |
| Storage growth | Image size cap, LRU eviction policy, dashboard + purge API |

---

## 14. Decisions & open items

**Locked (2026-08-24):**

| Decision | Choice |
|---|---|
| Language | C# / .NET 10 (§9) |
| Metadata sources | TMDB + TVDB hybrid, TMDB primary (§5) |
| ARR proxy face | In scope (§10, milestone M4) |

**Defaults chosen (override anytime):**

- **Hosting:** Docker image or self-contained binary, run on the same host as Plex.
- **Provider identifiers:** `tv.plex.agents.custom.metacache.movie` / `.tv` (suffix
  configurable).
- **HTTP port:** 8765 (configurable via env/config).

**Still open (no impact on M0–M2):** exact LAN IP/hostname the provider URL will use
(affects image URL rewriting in §7.3), TVDB API key provisioning, and whether the ARR
proxy face terminates TLS for ARR apps on this box or via Pi-hole LAN-wide.

---

## 15. Match scoring (M1)

**Goal:** turn a Plex match request (§6.3) into a ranked list of TMDB candidates — one
best match for auto-matching, or a full ranked list for manual "Fix Match". Implemented
as a pure, unit-tested engine in `Metacache.Core/Matching/`; the M1 provider routes
requests through it.

### 15.1 Inputs

| Hint | Source | Used for |
|---|---|---|
| `title` | match body | title similarity |
| `year` | match body | year score |
| `filename` | match body | filename year + token overlap |
| `guid` (e.g. `imdb://tt0088763`) | match body | exact external-ID match (overrides all) |
| `manual` | match body | ranked list vs. single best |
| `includeAdult` | match body | adult filtering |
| `X-Plex-Language` | header/query | small tiebreak bonus |

### 15.2 Normalization (`TitleNormalizer`)

Before any comparison: lowercase → replace smart quotes with ASCII → map non-
alphanumerics to spaces → collapse whitespace → strip leading articles (`the`/`a`/`an`) →
map trailing standalone roman numerals to digits (`rocky ii` → `rocky 2`, `episode iv` →
`episode 4`). Similarity between two normalized titles = `max(token-Jaccard, bigram-Dice)`
so word reordering and small spelling variants both score well.

### 15.3 Candidate score (weighted sum, clamped to [0, 1] → ×100)

| Component | Weight | Value |
|---|---|---|
| Title similarity | 0.45 | max over candidate `title` and `original_title` |
| Year | 0.25 | exact = 1.0, ±1 = 0.4, else 0 (missing input = 0.5 neutral) |
| Filename | 0.20 | 0.6·(file-year match) + 0.4·(filename-token Jaccard); no filename = 0.5 neutral |
| Popularity | 0.10 | `1 − e^(−popularity/200)` — tiebreaker only |
| Language | +0.02 | request language primary tag == candidate `original_language` |

**Exact external GUID** (`guid` matches a candidate's `imdb://`/`tmdb://`/`tvdb://` id)
overrides the weighted sum → score 1.0. Adult candidates are filtered out unless
`includeAdult=1`. Ties break by popularity, then stable input order.

### 15.4 Thresholds & response shaping (`MatchPolicy`)

- Auto-match: return the best candidate only if `score ≥ 0.60`; below that, return an
  empty container so Plex shows "Fix Match" instead of committing a wrong match.
- Manual: return all candidates with `score ≥ 0.15`, sorted descending, capped at 20.

### 15.5 M1 flow

1. Map the Plex match body → `MatchHint`.
2. `guid` present → TMDB `find` by external id (exact). Otherwise TMDB `search` by
   title+year (both through `UpstreamCache`, single-flighted).
3. **Enrich** the top ~8 search candidates with details (imdb id, posters, runtime,
   original language) via `MetadataCache` — needed for exact-GUID scoring, artwork, and
   the response `Guid[]`.
4. `MatchScorer.Score(hint, candidates)` → ranked `ScoredMatch[]` (with per-component
   breakdown for diagnostics).
5. Map to `MediaContainer.Metadata[]` (M1 mapper) — best first, include `Guid[]`.

### 15.6 Edge cases & limitations

- Remakes/reboots with identical titles are separated by year; genuinely identical
  title+year pairs fall back to popularity and remain a known coin-flip (manual fix
  available).
- Filename group names (e.g. `-RARBG`) aren't reliably distinguishable from title words;
  only well-known release tags (codec/resolution/source) are stripped.
- Weights and thresholds live in `MatchPolicy`, which is now bound from the
  `Metacache:Matching` configuration section (env overrides like
  `Metacache__Matching__AutoMatchThreshold` work) — tunable at runtime without recompiling.

### 15.7 TV matching (seasons/episodes)

Seasons and episodes use their own weight set — the show title confirms identity while
**structure (index/air-date) acts as a gate**: a definite index mismatch drops the
structure component to 0, keeping wrong seasons/episodes below the auto threshold.

| Component | Weight | Value |
|---|---|---|
| Show title | 0.40 | hint `parentTitle` (season) or `grandparentTitle` (episode) vs candidate parent (show) title |
| Structure | 0.35 | season: season-index equality; episode: ½·(season) + ½·(episode) index equality, or exact air-date equality when no index hints exist |
| Filename | 0.15 | filename tokens vs show title; `S01E05` / `Season N` parsed from the path supply structure when the body has no index |
| Popularity | 0.10 | tiebreaker |

Structural hints are taken from the request body first, then the filename; with no
structural hint at all the component is neutral (0.5). Exact-GUID override, adult
filtering, thresholds and manual/auto shaping are shared with movie matching.

**Shipped:** the engine (`MatchHint` with `MatchKind`, `MatchCandidate` with TV fields,
`MatchScorer` dispatch, `TitleNormalizer`, `FilenameParser` with SxxEyy/`Season N`,
`MatchPolicy` TV weights) with unit tests — see `tests/…/Matching/`.

---

## 16. M1 — movies shipped (implementation notes)

M1 lands the full movie loop: Plex match → ranked result → metadata → local artwork,
with every TMDB call behind the cache. Notes on the choices made:

**TMDB auth is header-based — with a legacy fallback.** The API Read Access Token is
sent as `Authorization: Bearer`, so URLs, cache keys and logs never contain the
secret. A live probe found that legacy v3 API keys (32-char hex) are **rejected as
Bearer (401)** and only work as the `api_key` query parameter — so `TmdbOptions.Auth`
supports `Auto` (default: probes `/authentication` once per process and picks the
mode the key accepts), `Bearer`, and `Query`. In `Query` mode the cache key is still
computed from the secret-free URL via `UpstreamCache`'s new `cacheKey` override, so
the key never lands in the cache DB. The header support itself required a small,
general extension to the cache gateway: `UpstreamRequest` carries optional per-
request headers, forwarded by `HttpUpstreamClient` — the ARR proxy face (M4) will
reuse this for Sonarr/Radarr header keys.

**M1 uses the raw-HTTP cache layer** (`UpstreamCache`) for all TMDB JSON — search/find
12 h TTL, movie details 24 h — which already delivers single-flight, ETag
revalidation, stale-if-error and per-language keys (the URL carries `language`). The
normalized `items` store (`MetadataCache`) is exercised starting in M2, where TV
season/episode structures need indexable rows; movies are fully served by the raw
layer. A match is search + one details call (the enriched winner); a guid-pinned match
is find + one details call; a manual search enriches the top 8 candidates in parallel.

**Artwork is fully local.** `MovieMapper` rewrites every TMDB poster/backdrop URL to
`/img/{sha256}` via `ImageCache.RewriteToLocalPath`; Plex pulls art from Metacache and
`/img` fetches+stores on first request (self-healing). Match items carry a rewritten
`thumb` too, so even the Fix Match dialog never touches the internet. Live testing
caught one hole: nothing registered those hashes before the first fetch, so the very
first Plex image request 404'd — the provider service now calls
`ImageCache.RegisterUrl` for each artwork URL it emits (a lazy, idempotent `urls`
row), making every rewritten `/img/{hash}` resolvable from the moment it's served.

**Schema quirk handled:** Plex's metadata object legitimately has both `guid` (string)
and `Guid` (array) — plus `studio`/`Studio`. System.Text.Json's default
case-insensitive conflict check rejects those pairs, so provider responses serialize
with `PropertyNameCaseInsensitive = false` (`ProviderJson`); every property name is
pinned by an explicit attribute, so nothing else changes.

**Deferred to M2 (kept the wire models ready):** collections, `Network[]`,
`SeasonType[]`, alternate episode orders, and response-customization params
(`includeFields`/`excludeElements`). M1 serves `Guid[]`, `Genre[]`, `Image[]`,
`Rating[]` (TMDB vote), `Country[]`, `Studio[]`, tagline, summary, duration and year
— the fields Plex needs for a complete movie library.

---

## 17. M2 — TV shipped (implementation notes)

M2 wires TMDB TV data into the §15.7 structure-gated scoring engine and ships the
paged hierarchy endpoints, plus cast/crew and content ratings for both movies and TV.

**Shows, seasons, episodes.** `TvProviderService` mirrors the movie service: a show
match is search (or external-GUID find) → score → enrich the winner; season and
episode matches resolve the show first, then gate on structure — `index`/`parentIndex`
(and `SxxEyy` filename parsing) via the scorer, or exact `date` equality when only an
air date is given — so a wrong season or episode can never be committed. A season
match enriches the winning season's episodes (or all seasons when only an air date is
supplied); manual match lists are ranked exactly like movies. Rating keys are
`tmdb-show-{id}`, `tmdb-season-{id}-{n}`, `tmdb-episode-{id}-{s}-{e}`.

**Hierarchy endpoints.** `GET /library/metadata/{ratingKey}/children` returns seasons
of a show or episodes of a season; `/grandchildren` returns every episode of a show.
Both page via Plex's `X-Plex-Container-Size`/`X-Plex-Container-Start` headers
(`PlexPaging`), defaulting to a full page with `size`/`totalSize` in the
`MediaContainer`.

**Cast/crew and content ratings.** `PeopleMapper` emits `Role[]` (cast) and
`Director[]`/`Producer[]`/`Writer[]` (crew) from TMDB credits, with profile photos
rewritten to `/img/{hash}` like all artwork; movies enrich from `/movie/{id}/credits`,
shows from `/tv/{id}/credits`. Content ratings come from `/movie/{id}/release_dates`
(certifications) and `/tv/{id}/content_ratings`, resolved by `X-Plex-Country` (falls
back to the US rating). The extra calls run in parallel and are cached.

**GUID pinning needed real external ids.** A `tmdb://` pin was always exact, but an
`imdb://`/`tvdb://` pin on a show built its candidate from a TMDB *summary*, which
carries only `tmdb://` — so the scorer's exact-GUID override never fired and the auto
threshold filtered the result to empty. The movie flow avoided this because
`/movie/{id}` includes `imdb_id`; TV needs the separate `/tv/{id}/external_ids` call.
The show match flow now enriches guid-pinned candidates with their real external ids
(`find` + `show` + `external_ids` = 3 calls, mirroring the movie DoD) so the override
fires and the pinned show is returned exactly.

**Contract gaps caught by tests.** (1) Plex's `guid`/`Guid` case collision is shared
by every kind, so all provider JSON keeps the case-sensitive `ProviderJson` options.
(2) The TV images endpoints initially served raw TMDB URLs instead of rewritten
`/img/{hash}` assets — the rewrite helper is now applied to every served image.
(3) A fixture that served one movie's details for every `/movie/{id}` hid enrichment
bugs; distinct fixtures now exist per item.

**Deferred:** collections, alternate episode orders, `Network[]`, `SeasonType[]`, and
`includeFields`/`excludeElements` response customization. Wire models for all of
these already exist in `MetadataModels.cs`.

**Live check against real TMDB (Read Access Token) found one gap:** shows and seasons
emitted no `Rating[]` even though episodes did (and movies always had). The mapper
now emits the TMDB audience rating on show/season items too (seasons inherit the
show's vote). Everything else verified live: structure-gated episode matching by
index and by air date, `/children` + `/grandchildren` paging (default 20, header
overrides), complete `Guid[]` (tmdb+imdb+tvdb) and cast/crew with rewritten `/img`
thumbs, country-aware content rating, real poster fetch through `/img`, and repeat
matches adding zero upstream calls.

---

## 18. M3 — cache warming + metrics shipped (implementation notes)

M3 turns the ARR apps' libraries into the cache inventory and adds the metrics
surface. Notes on the choices made:

**The warmer reuses the provider services.** `CacheWarmer` (Metacache.Plex/Warming)
calls `MovieProviderService.GetMovieMetadataAsync` / `TvProviderService.GetShowMetadataAsync`
for each library item, so every fetch flows through the normal cached gateway (TTL,
single-flight, ETag) and artwork registration — the warm is literally a headless
Plex refresh. A Radarr movie costs the details+credits+release-dates calls; a Sonarr
series resolves its tvdbId via the find endpoint, then fetches the show, every
season, and every episode, pulling show/season posters and episode stills through the
image cache. All of it is cached, so the next real refresh is a cache hit.

**ARR API keys ride in headers.** `ArrClient` queries `/api/v3/movie` and
`/api/v3/series` with `X-Api-Key`, so keys never appear in URLs or logs. These calls
are deliberately NOT routed through the upstream cache — the ARR APIs are the
inventory source, change constantly, and are queried on demand.

**The warmer writes `items` rows.** Every warmed movie/show/season/episode gets a row
in the normalized store (kind/source/source-id), which finally exercises the `items`
table (§7.4) and feeds the per-kind counts. `POST /warm/movies|shows|all` runs with
bounded concurrency (`Metacache:Arr:Concurrency`, default 4), returns a run summary,
and 409s while another run is in flight; `GET /warm/status` exposes the live state.

**Hit rate is a process counter, not a query.** `UpstreamCache` now increments
Interlocked request/hit counters (served-from-cache counts as a hit, including
stale-if-error), so `GET /metrics` reports a live hit rate without scanning the DB.
The endpoint also reports upstream-cache entries/bytes, per-kind item counts, image
files/bytes on disk, and the SQLite file size (`null` for `:memory:`).

**Deferred to M4+:** the scheduled (nightly) warm, event-driven warming on ARR
webhooks, a dashboard UI, trending/popular search warm-up, and the remaining M3
tuning knobs (manual TTL tuning). `items` rows are written by the warmer only —
provider-served lookups don't yet record rows, so per-kind counts reflect warm runs.

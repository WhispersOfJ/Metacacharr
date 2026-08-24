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
to `http://{host}:{port}/img/{sha256-of-original-url}`. On miss, Metacache streams the
image from upstream into the image store (with a size cap, e.g. 20 MB) and serves it;
on hit, it's a local file read. Plex's UI then loads every poster/backdrop from the LAN.
Filenames keep no upstream host/API info → cache stays private.

### 7.4 Storage

- **SQLite** (`metacache.db`): item store, cache index, stats. One file, zero ops,
  plenty for hundreds of thousands of items. WAL mode.
  - Sketch:
    ```sql
    items(id TEXT PRIMARY KEY,          -- normalized id: tmdb-show-15260
          kind TEXT,                    -- movie|show|season|episode|collection|person
          source TEXT, source_id TEXT,  -- tmdb|tvdb|imdb + id
          lang TEXT,                    -- en-US / de-DE / …
          json TEXT,                    -- normalized metadata payload
          fetched_at TEXT, expires_at TEXT, etag TEXT)
    upstream_cache(key TEXT PRIMARY KEY, -- sha256 of URL
          url TEXT, status INT, content_type TEXT, body BLOB,
          fetched_at TEXT, expires_at TEXT, etag TEXT, hits INT)
    urls(id TEXT PRIMARY KEY,            -- sha256 of original URL
          url TEXT, path TEXT,           -- path to image file
          size INT, fetched_at TEXT)
    ```
  - Indexes on `(source, source_id)`, `(kind, lang)`.
- **Image store:** `images/ab/cdef1234…` content-addressed files.
- Sizing: a 2,000-movie library ≈ 4–8 GB of images + < 200 MB of JSON. Fine on any NAS.

---

## 8. Cache warming (the "companion" part)

The cache is most valuable when it's *already full* before Plex asks. Warm it from the
ARR apps themselves:

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
  and shows the provider; requests log.
- **M1 — Movies:** match + metadata for movie libraries; GUIDs; image rewriting through
  the local endpoint; SQLite cache with TTL + ETag revalidation; 404/400 semantics.
  *DoD:* create a movie library using the provider; "Fix Match" finds films; refresh
  shows two upstream calls total.
- **M2 — TV:** shows/seasons/episodes; `/children` + `/grandchildren` with paging;
  episode matching by index and air date; localization (X-Plex-Language); content
  ratings by country; alternate episode orders. *DoD:* a TV library works end to end
  with correct episode matching on re-scans.
- **M3 — Companion features:** Sonarr/Radarr warm-up jobs; metrics + dashboard
  (hit rate, per-provider counts, disk usage); manual purge + TTL tuning; stale-if-error
  offline mode. *DoD:* unplug the WAN and a full library refresh still completes.
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

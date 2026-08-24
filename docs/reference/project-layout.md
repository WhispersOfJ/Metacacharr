# Project Layout

> Source tree structure, build commands, and development workflow.

## Directory Structure

```
Metacacharr/
├── src/
│   ├── Metacache.Core/           # Core library (no ASP.NET dependency)
│   │   ├── Cache/                # SQLite store, single-flight, upstream gateway
│   │   │   ├── CacheStore.cs     # SQLite operations (schema v4)
│   │   │   ├── UpstreamCache.cs  # ETag revalidation, stale-if-error, 429 retry
│   │   │   ├── MetadataCache.cs  # Item-level cache with stale-if-error
│   │   │   ├── ImageCache.cs     # Image fetch + resize + variant storage
│   │   │   ├── ImageStore.cs     # Content-addressed image storage
│   │   │   ├── SingleFlight.cs   # Per-key deduplication
│   │   │   └── UpstreamMetrics.cs# Per-provider latency histograms
│   │   ├── Matching/             # Match scoring engine
│   │   │   ├── MatchScorer.cs    # Weighted scoring algorithm
│   │   │   ├── MatchPolicy.cs    # Configurable weights/thresholds
│   │   │   ├── MatchOverrides.cs # Persisted GUID pins
│   │   │   ├── TitleNormalizer.cs# Article stripping, accent removal
│   │   │   └── FilenameParser.cs # Title/year extraction from filenames
│   │   └── Providers/            # Upstream API clients
│   │       ├── TmdbClient.cs     # TMDB v3 API (search, find, details)
│   │       ├── TvdbClient.cs     # TVDB v4 API (seasons, episodes)
│   │       └── ArrClient.cs      # Radarr/Sonarr API (inventory lists)
│   │
│   ├── Metacache.Plex/           # Plex-specific provider logic
│   │   ├── ProviderEndpoints.cs  # Plex API endpoints (match, metadata, children)
│   │   ├── MovieProviderService.cs # Movie match + metadata
│   │   ├── TvProviderService.cs  # TV match + metadata + hierarchy
│   │   ├── MovieMapper.cs        # TMDB → Plex metadata mapping
│   │   ├── TvMapper.cs           # TMDB → Plex TV mapping
│   │   ├── PeopleMapper.cs       # Cast/crew mapping
│   │   ├── ProviderCatalog.cs    # Provider definitions + features
│   │   ├── PlexPaging.cs         # Container-Size/Start helpers
│   │   ├── BrowseMapper.cs       # Cache index → Plex browse format
│   │   ├── GuidLookupService.cs  # Cross-provider GUID translation
│   │   └── Warming/              # Cache warmer
│   │       ├── CacheWarmer.cs    # Bulk + predictive + event-driven warm
│   │       ├── PlexPlayParser.cs # Plex webhook payload parsing
│   │       └── WarmOptions.cs    # Schedule + language config
│   │
│   └── Metacache.Host/           # ASP.NET Core host
│       ├── Program.cs            # Entry point, DI, pipeline
│       ├── Auth/                 # Bearer token middleware
│       ├── Proxy/                # ARR reverse proxy (M4)
│       ├── Pages/                # 10 UI/UX improvement pages
│       ├── MetricsEndpoints.cs   # /metrics + /metrics/prometheus
│       ├── MetricsDashboardEndpoints.cs # /dashboard
│       ├── WarmEndpoints.cs      # /warm/* + /webhook/*
│       ├── CacheAdminEndpoints.cs# /cache/stats + /cache/purge
│       ├── CacheIndexEndpoints.cs# /items + /guid/lookup
│       ├── ImageEndpoints.cs     # /img/{hash}
│       ├── LibraryBrowseEndpoints.cs # /library/search + /library/recentlyAdded
│       ├── MatchOverrideEndpoints.cs # /admin/overrides + /admin/unmatched
│       └── AdminEndpoints.cs     # /admin/items + /admin/upstream + /admin/purge
│
├── tests/
│   └── Metacache.Host.Tests/     # Integration + unit tests
│       ├── Cache/                # Cache store, index, image tests
│       ├── Matching/             # Match override tests
│       ├── Warming/              # Warmer, predictive, parser tests
│       ├── Auth/                 # Auth middleware tests
│       └── Proxy/                # Proxy router, cert tests
│
├── monitoring/                   # Docker Compose monitoring stack
│   ├── docker-compose.yml        # Prometheus + Grafana + Metacache
│   ├── prometheus.yml            # Scrape config
│   ├── metacache-alerts.yml      # Alerting rules
│   └── grafana/                  # Dashboard provisioning
│
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                # Build + test + format + CVE gate
│   │   └── docker.yml            # Docker build + GHCR push + Trivy scan
│   └── dependabot.yml            # NuGet + Docker base image updates
│
├── docs/                         # Diátaxis documentation suite
├── Dockerfile                    # Multi-stage build
├── DESIGN.md                     # Full architecture document
├── README.md                     # Project overview
└── Metacache.slnx                # Solution file
```

## Build Commands

```bash
# Restore + build
dotnet build

# Build Release (CI-equivalent, warnings as errors)
dotnet build -c Release --nologo -warnaserror

# Format check
dotnet format --verify-no-changes

# Auto-fix formatting
dotnet format

# Run tests
dotnet test

# Run tests with verbose output
dotnet test -v n

# Run specific test class
dotnet test --filter "FullyQualifiedName~CacheWarmerTests"

# NuGet CVE audit
dotnet list package --vulnerable
```

## Development Workflow

1. **Make changes** to source files
2. **Build:** `dotnet build -c Release --nologo -warnaserror`
3. **Format:** `dotnet format`
4. **Test:** `dotnet test`
5. **Commit** with conventional commit message

## Test Organization

| Test class | What it tests |
|------------|---------------|
| `CacheStoreTests` | SQLite schema, CRUD, migrations |
| `CacheIndexTests` | Search, pagination, freshness |
| `ImageCacheTests` | Fetch, resize, variants, eviction |
| `CacheWarmerTests` | Bulk warm, predictive, multi-language |
| `PlexPlayParserTests` | Webhook payload parsing |
| `AuthMiddlewareTests` | Token validation, route protection |
| `ProxyRouterTests` | Hostname resolution, URL reconstruction |
| `CertManagerTests` | CA generation, leaf certs, persistence |
| `PagesTests` | All 10 UI pages return valid HTML |
| `AdminEndpointsTests` | Search, purge, database info |

## Adding a New Endpoint

1. Create or edit an `*Endpoints.cs` file in `Metacache.Host/`
2. Add the route in the `Map*` extension method
3. Wire it in `Program.cs` with `app.Map*Endpoints()`
4. Add tests in `tests/Metacache.Host.Tests/`
5. Update `docs/reference/api-endpoints.md`

## Adding a New Config Key

1. Add to the relevant options record (e.g. `WarmOptions`, `ProxyOptions`)
2. Read it in `Program.cs` from `IConfiguration`
3. Register in DI
4. Update `docs/reference/configuration.md`

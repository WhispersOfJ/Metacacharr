# Design Decisions

> Why Metacache was built the way it was.

## Language: C# / .NET

**Decision:** Use C# with .NET 10.

**Why:**
- ASP.NET Core is the fastest HTTP framework on .NET
- SQLite integration via `Microsoft.Data.Sqlite` is mature and performant
- Strong typing catches bugs at compile time
- LINQ makes database queries readable
- Docker images are small with the self-contained publish option

**Alternatives considered:**
- *Rust:* Better raw performance, but slower development iteration
- *Go:* Simpler deployment, but less expressive database layer
- *Python:* Faster prototyping, but insufficient performance for proxy workloads

## Database: SQLite

**Decision:** Use SQLite with WAL mode for all persistent storage.

**Why:**
- Zero dependencies — runs anywhere .NET runs
- Single file — easy backup, easy migration
- WAL mode allows concurrent reads while warming writes
- Sufficient for metadata workloads (small records, read-heavy)

**Alternatives considered:**
- *PostgreSQL:* Overkill for a single-node cache; adds deployment complexity
- *Redis:* In-memory; data lost on restart; not suitable for persistent metadata
- *LevelDB/RocksDB:* Good for key-value, but lacks SQL query flexibility

## Cache Strategy: ETag + Stale-if-Error

**Decision:** Use conditional requests (ETag/If-Modified-Since) with stale fallback.

**Why:**
- ETag revalidation: 304 responses cost almost zero bandwidth
- Stale-if-error: Library works offline during upstream outages
- TTL-based expiry: Simple, predictable, tunable

**Alternatives considered:**
- *Polling with fixed interval:* Wastes bandwidth when nothing changes
- *Webhook-based invalidation:* TMDB doesn't support push notifications
- *Cache-aside with no stale:* Fails during upstream outages

## Match Scoring: Weighted Algorithm

**Decision:** Weighted scoring with configurable thresholds.

**Why:**
- Transparent: users can understand why a match was chosen
- Tunable: weights can be adjusted for different libraries
- Deterministic: same inputs always produce the same score
- GUID-first: external IDs are the most reliable signal

**Alternatives considered:**
- *Machine learning:* Overkill; insufficient training data
- *Fuzzy string matching only:* Misses year/GUID signals
- *Exact match only:* Too many false negatives

## Architecture: Monolith (Not Microservices)

**Decision:** Single process with multiple responsibilities.

**Why:**
- Simpler deployment (one Docker container)
- No network overhead between components
- SQLite doesn't need a separate service
- Easier debugging (one log stream)
- Sufficient for the expected load (single Plex server)

**Alternatives considered:**
- *Microservices:* More complex deployment, network partitions, harder debugging
- *Separate cache service:* Adds latency for metadata lookups
- *External message queue:* Overkill for webhook-driven warming

## ARR Integration: Transparent Proxy

**Decision:** DNS override + TLS termination + transparent reverse proxy.

**Why:**
- ARR apps have no plugin system
- The only way to intercept their calls is at the network level
- Transparent to the ARR apps (no configuration changes needed)
- Works with any ARR version (no API dependency)

**Alternatives considered:**
- *ARR plugin:* Doesn't exist; ARR doesn't support custom backends
- *HTTP proxy (no TLS):* ARR apps use HTTPS; would break
- *VPN/tunnel:* Too complex for home users

## Warming: Multi-Strategy

**Decision:** Bulk + event-driven + predictive + nightly scheduled warming.

**Why:**
- Bulk (Radarr/Sonarr): Fills the initial cache from inventory
- Event-driven (webhooks): Warms individual items on import
- Predictive (playback): Pre-warms related content before it's needed
- Nightly (scheduled): Catches anything missed by event-driven warm

**Each strategy fills a different gap:**
- Bulk: First-time setup
- Event-driven: New imports
- Predictive: Next episode / similar titles
- Nightly: Catch-all for anything missed

## UI: Self-Contained HTML

**Decision:** All UI pages are self-contained HTML/CSS/JS with zero external dependencies.

**Why:**
- Works with the WAN down (no CDN, no external fonts)
- No build step (no npm, no webpack)
- Simple to maintain (one file per page)
- Fast to load (no external requests)
- Secure (no supply chain risk from CDN)

**Alternatives considered:**
- *React/Vue SPA:* Requires npm build step; adds complexity
- *Server-side Razor:* Couples UI to .NET; harder to iterate
- *External dashboard (Grafana):* Separate deployment; harder to customize

## Testing: Integration-First

**Decision:** Most tests are integration tests using `WebApplicationFactory`.

**Why:**
- Tests the full request pipeline (DI, middleware, endpoints)
- Catches wiring issues that unit tests miss
- `FakeUpstream` makes tests deterministic (no network calls)
- In-memory SQLite makes tests fast and isolated

**Alternatives considered:**
- *Unit tests only:* Miss integration issues
- *End-to-end tests:* Too slow for CI; flaky
- *Manual testing:* Doesn't scale; catches bugs too late

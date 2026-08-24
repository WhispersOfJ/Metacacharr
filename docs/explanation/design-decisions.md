# Explanation: Design Decisions

> Why Metacacharr was built this way.

## Why a Unified Stack?

### Problem

Two separate repos with overlapping concerns:
- **Metacache** — Metadata caching for Plex
- **Media-Stack** — Media acquisition and serving

Users had to manually integrate them, configure webhooks, and manage two deployment processes.

### Solution

Unified monorepo with shared Docker Compose:
- Single `docker compose up` starts everything
- Shared environment variables
- Integrated monitoring
- Automatic webhook wiring

### Tradeoffs

**Pros:**
- Simplified deployment
- Shared configuration
- Unified monitoring
- Automatic integration

**Cons:**
- Larger repository
- More complex CI/CD
- Tightly coupled releases

## Why SQLite for Metacache?

### Problem

Need a fast, embedded database for metadata caching.

### Options Considered

| Database | Pros | Cons |
|----------|------|------|
| SQLite | Embedded, fast, zero-config | Single-writer, no replication |
| PostgreSQL | Full-featured, scalable | Requires separate service |
| Redis | Fast, in-memory | Volatile, memory-hungry |
| MongoDB | Flexible schema | Complex, resource-heavy |

### Decision

SQLite chosen for:
- **Simplicity** — No separate service to manage
- **Performance** — Fast reads for cache hits
- **Portability** — Single file database
- **Reliability** — Battle-tested, ACID compliant

### Tradeoffs

**Pros:**
- Zero configuration
- Fast reads
- Easy backup (copy single file)
- No network overhead

**Cons:**
- Single-writer (acceptable for read-heavy workload)
- No replication (not needed for single instance)
- Size limits (not a problem for metadata)

## Why C#/.NET for Metacache?

### Problem

Need a high-performance metadata cache with Plex provider API support.

### Options Considered

| Language | Pros | Cons |
|----------|------|------|
| C#/.NET | Fast, Plex SDK available, strong typing | Heavier runtime |
| Python | Fast development, rich ecosystem | Slower runtime |
| Go | Fast, small binary | No Plex SDK |
| Rust | Fastest, safe | Steep learning curve |

### Decision

C#/.NET chosen for:
- **Plex SDK** — Official .NET SDK available
- **Performance** — Fast enough for real-time caching
- **Developer familiarity** — Existing expertise
- **Docker support** — Excellent container images

### Tradeoffs

**Pros:**
- Official Plex SDK
- Strong typing catches errors early
- Fast runtime
- Good Docker support

**Cons:**
- Larger container image
- Requires .NET runtime
- More verbose than Python

## Why This Integration Pattern?

### Problem

Need to connect Metacache with Radarr, Sonarr, and Plex.

### Options Considered

| Pattern | Pros | Cons |
|---------|------|------|
| Webhooks | Real-time, event-driven | Requires webhook setup |
| Polling | Simple, reliable | Wasteful, delayed |
| Shared database | Fast, direct | Tight coupling |
| Message queue | Decoupled, scalable | Complex infrastructure |

### Decision

Webhooks chosen for:
- **Real-time** — Immediate cache updates
- **Standard** — All three services support webhooks
- **Decoupled** — Services remain independent
- **Simple** — No additional infrastructure

### Implementation

```
Plex → webhook → plex-webhook-listener → Metacache
Radarr → webhook → Metacache
Sonarr → webhook → Metacache
```

### Tradeoffs

**Pros:**
- Real-time updates
- Standard integration pattern
- No additional infrastructure
- Services remain independent

**Cons:**
- Requires webhook configuration
- Must handle delivery failures
- No guaranteed ordering

## Why This Monitoring Stack?

### Problem

Need observability for the unified stack.

### Options Considered

| Stack | Pros | Cons |
|-------|------|------|
| Prometheus + Grafana | Industry standard, powerful | Complex setup |
| ELK Stack | Full-text search, logs | Resource-heavy |
| Datadog | Managed, easy | Expensive, vendor lock-in |
| Custom | Tailored to needs | Maintenance burden |

### Decision

Prometheus + Grafana chosen for:
- **Industry standard** — Widely supported
- **Free** — No licensing costs
- **Powerful** — Rich query language
- **Community** — Large ecosystem

### Components

- **Prometheus** — Metrics collection
- **Grafana** — Visualization
- **Loki** — Log aggregation
- **Promtail** — Log shipping

### Tradeoffs

**Pros:**
- Free and open source
- Industry standard
- Powerful querying
- Large community

**Cons:**
- Complex initial setup
- Requires maintenance
- Resource-heavy for small deployments

## Why This Warming Strategy?

### Problem

Need to pre-populate cache for fast Plex refreshes.

### Options Considered

| Strategy | Pros | Cons |
|----------|------|------|
| On-demand | Simple, no waste | Slow on first request |
| Scheduled | Predictable | May warm unused items |
| Event-driven | Real-time, relevant | Complex implementation |
| Predictive | Proactive | Requires behavior analysis |

### Decision

Hybrid approach:
- **Scheduled** — Nightly warm of entire library
- **Event-driven** — Warm on import events
- **Predictive** — Warm on playback events

### Tradeoffs

**Pros:**
- Comprehensive coverage
- Real-time for new imports
- Proactive for popular content
- Balances resource usage

**Cons:**
- Complex implementation
- May waste resources on unused content
- Requires multiple integration points

## Why This Deployment Model?

### Problem

Need easy deployment for self-hosters.

### Options Considered

| Model | Pros | Cons |
|-------|------|------|
| Docker Compose | Simple, widely used | Single-host only |
| Kubernetes | Scalable, production-ready | Complex setup |
| Bare metal | Maximum performance | Manual management |
| Cloud-managed | Easy, maintained | Expensive, vendor lock-in |

### Decision

Docker Compose chosen for:
- **Simplicity** — Single command deployment
- **Portability** — Works on any Docker host
- **Self-hosted** — No cloud dependency
- **Community** — Most self-hosters use Docker

### Tradeoffs

**Pros:**
- Simple deployment
- Portable across hosts
- No cloud dependency
- Large community

**Cons:**
- Single-host only
- Manual scaling
- No built-in high availability

## Future Considerations

### Potential Improvements

1. **Multi-language caching** — Cache metadata in multiple languages
2. **ARR proxy** — Transparent HTTPS proxy for Radarr/Sonarr
3. **Distributed cache** — Share cache across multiple Plex instances
4. **Machine learning** — Predictive warming based on viewing patterns
5. **GraphQL API** — More flexible query interface

### What We'd Do Differently

1. **Start with TypeScript** — Faster development cycle
2. **Use PostgreSQL** — Better for complex queries
3. **Implement CQRS** — Separate read/write paths
4. **Add event sourcing** — Complete audit trail

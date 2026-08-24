# Metacache Documentation

> A local metadata cache for Plex that makes refreshes fast, offline-capable, and rate-limit-safe.

Metacache sits between Plex and upstream providers (TMDB, TVDB), caching all metadata locally. Plex refreshes from the fast local server instead of hammering external APIs. It implements Plex's **Custom Metadata Provider** API (PMS 1.43+).

## Quick Start

- **[Getting Started](tutorials/01-getting-started.md)** — Install, configure, register in Plex, first warm (15 minutes)
- **[First Warm](tutorials/02-first-warm.md)** — Warm your library and verify cache hits
- **[Configuration Reference](reference/configuration.md)** — Every config key with defaults and examples

## For Self-Hosters

| Task | Guide |
|------|-------|
| Register in Plex | [How to: Register in Plex](how-to/register-in-plex.md) |
| Set up the ARR proxy | [Tutorial: ARR Proxy Setup](tutorials/05-arr-proxy-setup.md) |
| Add API key auth | [How to: Configure Auth](how-to/configure-auth.md) |
| Use the dashboard | [How to: Use the Dashboard](how-to/use-dashboard.md) |
| Fix a bad match | [How to: Fix Match Manually](how-to/fix-match-manually.md) |
| Warm your library | [How to: Warm from UI](how-to/warm-from-ui.md) |
| Monitor with Grafana | [Tutorial: Monitoring Stack](tutorials/04-monitoring-stack.md) |
| Troubleshoot issues | [How to: Troubleshoot](how-to/troubleshoot.md) |

## For Developers

| Topic | Doc |
|-------|-----|
| API endpoints | [Reference: API Endpoints](reference/api-endpoints.md) |
| Configuration | [Reference: Configuration](reference/configuration.md) |
| Database schema | [Reference: Database Schema](reference/database-schema.md) |
| Match scoring | [Reference: Match Scoring](reference/match-scoring.md) |
| Project layout | [Reference: Project Layout](reference/project-layout.md) |
| Architecture | [Explanation: Architecture](explanation/architecture.md) |
| Design decisions | [Explanation: Design Decisions](explanation/design-decisions.md) |

## Understanding Metacache

- [How caching works](explanation/caching-strategy.md) — ETag revalidation, stale-if-error, single-flight
- [How match scoring works](explanation/match-algorithm.md) — Why the scoring algorithm works the way it does
- [How predictive warming works](explanation/predictive-warming.md) — Playback-start events drive cache warming
- [How the ARR proxy works](explanation/arr-proxy-design.md) — Transparent reverse proxy for Radarr/Sonarr

## Deployment

- [Docker](deploy/docker.md) — Build and run with Docker
- [Docker Compose](deploy/docker-compose.md) — Full stack with Prometheus + Grafana
- [Manual](deploy/manual.md) — Self-contained binary setup
- [Plex Media Server](deploy/plex-media-server.md) — PMS-specific notes

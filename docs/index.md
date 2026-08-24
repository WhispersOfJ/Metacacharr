# Metacacharr Documentation

> A unified media stack combining **Metacache** (local metadata cache for Plex) with **Media-Stack** (Docker Compose media acquisition and serving).

Metacacharr brings together two powerful systems:
- **Metacache** — A C#/.NET metadata cache that makes Plex refreshes fast, offline-capable, and rate-limit-safe
- **Media-Stack** — A Python/Django media acquisition stack with Plex, Radarr, Sonarr, Usenet, and more

## Quick Start

- **[First-Time Setup](tutorials/01-first-time-setup.md)** — Deploy the full Metacacharr stack from scratch (30 minutes)
- **[Add to Existing Stack](tutorials/05-add-metacache-to-existing-stack.md)** — Add Metacache to your running media-stack
- **[Connect Plex Providers](tutorials/02-connect-plex-providers.md)** — Register Metacache as Plex metadata provider

## For Self-Hosters

| Task | Guide |
|------|-------|
| Deploy the full stack | [Tutorial: First-Time Setup](tutorials/01-first-time-setup.md) |
| Add Metacache to existing stack | [Tutorial: Add to Existing Stack](tutorials/05-add-metacache-to-existing-stack.md) |
| Register in Plex | [How to: Connect Plex Providers](tutorials/02-connect-plex-providers.md) |
| Enable webhook warming | [How to: Enable Webhook Warming](how-to/enable-webhook-warming.md) |
| Configure Metacache URL | [How to: Configure Metacache URL](how-to/configure-metacache-url.md) |
| Fix volume permissions | [How to: Fix Volume Permissions](how-to/fix-volume-permissions.md) |
| Update Prometheus scrape | [How to: Update Prometheus Scrape](how-to/update-prometheus-scrape.md) |
| Use Letterboxd warm chain | [How to: Use Letterboxd Warm Chain](how-to/use-letterboxd-warm-chain.md) |
| Access Metacache dashboard | [How to: Access Dashboard](how-to/access-metacache-dashboard.md) |
| Troubleshoot issues | [How to: Troubleshoot](how-to/troubleshoot-common-issues.md) |

## For Developers

| Topic | Doc |
|-------|-----|
| API endpoints | [Reference: API Endpoints](reference/api-endpoints.md) |
| Configuration | [Reference: Configuration](reference/configuration.md) |
| Docker Compose services | [Reference: Docker Compose Services](reference/docker-compose-services.md) |
| Integration points | [Reference: Integration Points](reference/integration-points.md) |
| Project structure | [Reference: Project Structure](reference/project-structure.md) |
| Architecture | [Explanation: Architecture Overview](explanation/architecture-overview.md) |
| Design decisions | [Explanation: Design Decisions](explanation/design-decisions.md) |

## Understanding Metacacharr

- [Architecture Overview](explanation/architecture-overview.md) — How the unified stack fits together
- [Caching Strategy](explanation/caching-strategy.md) — ETag revalidation, stale-if-error, single-flight
- [Warm Pipeline](explanation/warm-pipeline.md) — Predictive vs bulk vs webhook warming
- [Design Decisions](explanation/design-decisions.md) — Why SQLite, why C#, why this integration pattern

## Deployment

- [Docker Compose](deploy/docker-compose.md) — Full stack deployment
- [Add to Existing Stack](deploy/adding-to-existing-stack.md) — Step-by-step for existing media-stack users
- [Monitoring Setup](deploy/monitoring-setup.md) — Prometheus + Grafana configuration

## Reference: Existing Documentation

This unified stack builds upon two existing documentation sets:

### Metacache Documentation (31 documents)
- [Tutorials](tutorials/) — Getting started, first warm, multi-language, monitoring, ARR proxy
- [How-to Guides](how-to/) — Plex registration, auth, dashboard, Fix Match, GUIDs, warming, cache browsing, purging, ARR setup, troubleshooting
- [Reference](reference/) — API endpoints, configuration, database schema, match scoring, project layout
- [Explanation](explanation/) — Architecture, caching strategy, match algorithm, predictive warming, ARR proxy design, design decisions
- [Deploy](deploy/) — Docker, Docker Compose, manual binary, Plex Media Server

### Media-Stack Documentation
- [README.md](../media-stack/README.md) — Comprehensive stack documentation (189KB)
- [STACK.md](../media-stack/STACK.md) — Detailed reference for architecture, gotchas, and workflow playbooks
- [PLANS.md](../media-stack/PLANS.md) — Future plans and roadmap
- [CHANGELOG.md](../media-stack/CHANGELOG.md) — Version history
- [CLAUDE.md](../media-stack/CLAUDE.md) — AI assistant rules and verification procedures
- [CRON-JOBS-SETUP.md](../media-stack/CRON-JOBS-SETUP.md) — Scheduled task configuration
- [DISCORD-ALERTS-SETUP.md](../media-stack/DISCORD-ALERTS-SETUP.md) — Notification configuration
- [GRAFANA-DASHBOARDS.md](../media-stack/GRAFANA-DASHBOARDS.md) — Dashboard configuration

# Metacache

An ARR-app companion that caches movie/TV metadata locally so Plex refreshes from a
fast local server instead of hammering TMDB/TVDB over the internet. Implements Plex's
**Custom Metadata Provider** API (PMS 1.43+), which natively lets you point Plex at any
HTTP metadata server.

See [DESIGN.md](DESIGN.md) for the full architecture, API contract, and roadmap.

## Status: M0 — provider skeleton

- `GET /movie` and `GET /tv` serve the MediaProvider definitions Plex needs to register
  the providers ("Add Provider").
- `GET /healthz` liveness check.
- Rating-key and GUID utilities with tests.

Match/metadata endpoints (M1), TV support (M2), cache warming (M3) and the ARR proxy
face (M4) are next — see DESIGN.md §12.

## Requirements

- .NET 10 SDK (`dotnet`), or Docker.

## Run

```bash
dotnet run --project src/Metacache.Host
# → listening on http://127.0.0.1:8765
```

### Configuration

| Setting | Default | Notes |
|---|---|---|
| `Metacache__BindAddress` | `127.0.0.1` | Set to `0.0.0.0` to expose on the LAN (required for Plex on another machine) |
| `Metacache__Port` | `8765` | Provider URL port |

Env vars override `appsettings.json`, e.g.:

```bash
Metacache__BindAddress=0.0.0.0 Metacache__Port=8765 dotnet run --project src/Metacache.Host
```

### Docker

```bash
docker build -t metacache .
docker run -d --name metacache --network host metacache
# binds 0.0.0.0:8765 (configurable via Metacache__Port)
```

## Registering the providers in Plex

1. Plex Media Server 1.43+ (custom metadata providers must be enabled).
2. Settings → Metadata Agents → **Add Provider**, enter
   `http://<metacache-host>:8765/movie` (and again with `/tv` for the TV provider).
3. **Add Agent**, name it, and make Metacache the Primary provider for a library.
4. Create/assign a library using that agent. Requests are logged to the Metacache
   console.

> **Security:** the provider API is unauthenticated (Plex does not send auth yet).
> Keep it on your LAN, and use a firewall rule if you must expose it further.

## Tests

```bash
dotnet test
```

## Project layout

```
src/Metacache.Core/   shared identity constants
src/Metacache.Plex/   Plex provider API: wire models, catalog, rating keys, endpoints
src/Metacache.Host/   ASP.NET Core host, config, logging
tests/Metacache.Host.Tests/  integration + unit tests
```

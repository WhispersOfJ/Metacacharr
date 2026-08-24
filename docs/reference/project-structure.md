# Reference: Project Structure

> Monorepo layout, build commands, and development workflow.

## Directory Layout

```
metacacharr/
├── docker-compose.yml          # Unified stack definition
├── .env.example                # Environment template
├── .gitignore                  # Git ignore rules
│
├── metacache/                  # C#/.NET metadata cache
│   ├── Dockerfile              # Container build
│   ├── Metacache.slnx          # Solution file
│   ├── src/
│   │   ├── Metacache.Core/     # Core library (cache, matching, providers)
│   │   ├── Metacache.Plex/     # Plex integration (providers, warming)
│   │   └── Metacache.Host/     # Web host (endpoints, proxy, auth)
│   ├── tests/                  # Unit and integration tests
│   ├── docs/                   # Metacache documentation
│   └── monitoring/             # Prometheus/Grafana config
│
├── media-stack/                # Python/Django media stack
│   ├── docker-compose.yml      # Original stack definition
│   ├── Dockerfile              # Installer image
│   ├── control-panel/          # Django/DRF backend
│   │   ├── core/               # Shared utilities
│   │   ├── services/           # Service routers (arr, plex, etc.)
│   │   ├── models/             # Database models
│   │   └── static/             # Frontend assets
│   ├── control-panel-django/   # Previous-gen backend (deprecated)
│   ├── scripts/                # Utility scripts
│   ├── fish-functions/         # CLI functions (stack-*)
│   ├── config/                 # Runtime configuration
│   ├── docs/                   # Media-stack documentation
│   └── systemd/                # Service units
│
├── docs/                       # Unified documentation
│   ├── tutorials/              # Learning-oriented guides
│   ├── how-to/                 # Problem-oriented guides
│   ├── reference/              # Information-oriented docs
│   ├── explanation/            # Understanding-oriented docs
│   └── deploy/                 # Deployment guides
│
└── monitoring/                 # Unified monitoring config
    ├── prometheus.yml          # Prometheus configuration
    ├── grafana/                # Grafana dashboards
    └── alerts.yml              # Alerting rules
```

## Build Commands

### Metacache (C#/.NET)

```bash
cd metacache

# Restore dependencies
dotnet restore

# Build
dotnet build

# Run tests
dotnet test

# Publish
dotnet publish src/Metacache.Host/Metacache.Host.csproj -c Release -o /app/publish

# Build Docker image
docker build -t metacache .
```

### Media-Stack (Python)

```bash
cd media-stack

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Build installer image
docker build -t media-stack-installer .
```

## Development Workflow

### 1. Make Changes

Edit files in `metacache/src/` or `media-stack/control-panel/`.

### 2. Run Tests

```bash
# Metacache tests
cd metacache && dotnet test

# Media-stack tests
cd media-stack && pytest
```

### 3. Rebuild Container

```bash
# Metacache
docker compose build metacache
docker compose up -d metacache

# Control panel
docker compose build control-panel
docker compose up -d control-panel
```

### 4. Verify

```bash
# Check health
curl http://localhost:8765/healthz

# Check logs
docker compose logs -f metacache
```

## Key Files

### Metacache

| File | Purpose |
|------|---------|
| `src/Metacache.Host/Program.cs` | Application entry point |
| `src/Metacache.Core/Cache/CacheStore.cs` | SQLite cache implementation |
| `src/Metacache.Plex/Warming/CacheWarmer.cs` | Cache warming logic |
| `src/Metacache.Host/WarmEndpoints.cs` | Warm API endpoints |
| `tests/` | Unit and integration tests |

### Media-Stack

| File | Purpose |
|------|---------|
| `control-panel/main.py` | FastAPI application |
| `control-panel/services/*/router.py` | Service routers |
| `scripts/plex-webhook-listener.py` | Plex webhook handler |
| `docker-compose.yml` | Service definitions |

## Code Style

### C#/.NET

- Follow Microsoft coding conventions
- Use nullable reference types
- Prefix private fields with `_`
- Use records for immutable data

### Python

- Follow PEP 8
- Use type hints
- Use docstrings for public functions
- Keep functions small and focused

## Testing

### Metacache Tests

```bash
cd metacache

# Run all tests
dotnet test

# Run specific test class
dotnet test --filter "FullyQualifiedName~CacheStoreTests"

# Run with verbosity
dotnet test --verbosity normal
```

### Media-Stack Tests

```bash
cd media-stack

# Run all tests
pytest

# Run specific test file
pytest tests/test_arr_client.py

# Run with coverage
pytest --cov=control-panel
```

## Documentation

### Viewing Docs

```bash
# Serve docs locally
cd docs
python -m http.server 8000

# Open in browser
open http://localhost:8000
```

### Adding Docs

1. Choose the right quadrant (tutorial, how-to, reference, explanation)
2. Follow the existing style
3. Update index.md with links
4. Test all code examples

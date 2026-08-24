# ARR Proxy Design

> Why Metacache uses a transparent reverse proxy and how it works.

## The Problem

Radarr and Sonarr hardcode their metadata endpoints:
- Radarr calls `api.themoviedb.org` for movie metadata
- Sonarr calls `api.thetvdb.com` for episode data

There's no plugin system, no configurable backend, no way to redirect these calls to a local cache. Every import, every UI refresh, every metadata lookup hits the real API.

## The Solution: Transparent Reverse Proxy

Metacache runs a second HTTPS endpoint that **impersonates** the real APIs:

```
Radarr → DNS override → Metacache:443 (pretends to be api.themoviedb.org)
                              │
                              ├─ Cache hit → serve from SQLite
                              └─ Cache miss → fetch from real API, cache, serve
```

Radarr never knows it's talking to a cache. The responses are identical.

## How TLS Works

### The Challenge

Radarr connects to `api.themoviedb.org:443` with HTTPS. The real API uses a valid certificate from a public CA. Metacache needs to present a certificate for `api.themoviedb.org` that Radarr trusts.

### The Solution: Local CA

1. **Metacache generates a local CA** on first run (`data/certs/metacache-ca.pfx`)
2. **Per-hostname leaf certs** are generated on demand, signed by the local CA
3. **User installs the CA cert** into the trust store of each ARR host
4. **Kestrel's SNI selector** picks the right cert based on the hostname

### Certificate Flow

```
Radarr connects to Metacache:443 with SNI="api.themoviedb.org"
  │
  ├─ Kestrel asks CertManager for cert("api.themoviedb.org")
  │
  ├─ CertManager checks cache → cert exists? return it
  │
  └─ CertManager generates new cert:
      1. RSA 2048-bit key pair
      2. Subject: CN=api.themoviedb.org
      3. SAN: api.themoviedb.org
      4. Signed by local CA
      5. Cached in memory + persisted to disk
```

## SNI Routing

Server Name Indication (SNI) is the TLS extension that tells the server which hostname the client wants. Metacache uses it for routing:

1. Client connects with SNI="api.themoviedb.org"
2. `ProxyRouter` maps hostname → upstream base URL
3. `ProxyMiddleware` reconstructs the full URL from SNI + path + query
4. `UpstreamCache` serves from cache or fetches from the real API

### Route Table

| Hostname | Upstream |
|----------|----------|
| `api.themoviedb.org` | `https://api.themoviedb.org/3` |
| `image.tmdb.org` | `https://image.tmdb.org/t/p/original` |
| `api.thetvdb.com` | `https://api4.thetvdb.com` |
| `webservice.fanart.tv` | `https://webservice.fanart.tv/v3` |

Unknown hostnames pass through to normal ASP.NET routing (the provider endpoints).

## DNS Override

The proxy only works if DNS resolves the real hostnames to Metacache's IP:

### Pi-hole / AdGuard Home (LAN-wide)

Add custom DNS entries:
```
192.168.1.100  api.themoviedb.org
192.168.1.100  image.tmdb.org
192.168.1.100  api.thetvdb.com
192.168.1.100  webservice.fanart.tv
```

### /etc/hosts (single machine)

```
192.168.1.100 api.themoviedb.org image.tmdb.org api.thetvdb.com webservice.fanart.tv
```

### Docker Compose

```yaml
services:
  radarr:
    extra_hosts:
      - "api.themoviedb.org:192.168.1.100"
      - "image.tmdb.org:192.168.1.100"
```

## API Key Handling

ARR apps send API keys in the URL or Authorization header. Metacache handles both:

1. **URL keys:** `?api_key=xxx` → stripped from cache key (never stored in DB)
2. **Header keys:** `Authorization: Bearer xxx` → passed through to upstream
3. **Cache keys:** Computed from the **secret-free** URL

This ensures API keys never leak into the database or logs.

## What ARR Apps See

| Aspect | Without Proxy | With Proxy |
|--------|---------------|------------|
| API responses | From TMDB/TVDB | Identical (from cache) |
| Latency | 100–500ms | <5ms (cache hit) |
| Rate limits | Consumed | Zero (cache hit) |
| Offline | Fails | Works (stale-if-error) |
| TLS | Valid public cert | Valid local cert (trusted via CA) |

## Security Properties

- **No key leakage:** API keys stripped from cache keys
- **Constant-time auth:** Token comparison prevents timing attacks
- **Cert isolation:** Only routed hostnames get certificates
- **No cert pinning:** TMDB/TVDB don't pin certificates (verified)
- **Pass-through headers:** Authorization, Accept, etc. forwarded unchanged

## Limitations

- **Requires trust store modification:** Each ARR host needs the local CA installed
- **DNS dependency:** If DNS override is wrong, ARR apps hit the real API (no harm, just no caching)
- **Not a full MITM:** Only intercepts GET requests; POST/PUT/DELETE pass through normally
- **Port 443 conflict:** If another service uses port 443, configure a different proxy port

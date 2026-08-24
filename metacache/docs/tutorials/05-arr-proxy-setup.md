# Tutorial: ARR Proxy Setup

> **Goal:** Enable the transparent caching proxy so Radarr/Sonarr hit Metacache instead of upstream APIs.
>
> **Time:** ~20 minutes (most time is DNS + trust store setup)
>
> **Prerequisites:** [Getting Started](01-getting-started.md) completed

## Why the ARR Proxy?

Without the proxy, Metacache only caches what Plex requests. Radarr/Sonarr still make their own API calls to TMDB for imports, UI art, and metadata lookups. The proxy eliminates **all** duplicate API calls from ARR apps.

## Overview

```
Radarr ──→ DNS override ──→ Metacache:443 (HTTPS)
                                  │
                                  ├─ Cache hit? → serve from SQLite
                                  └─ Cache miss? → fetch from upstream, cache, serve
```

## Step 1: Enable the Proxy

### Environment variable

```bash
Metacache__Proxy__Enabled=true
```

### appsettings.json

```json
{
  "Metacache": {
    "Proxy": {
      "Enabled": true,
      "HttpPort": 443,
      "CertDirectory": "data/certs"
    }
  }
}
```

## Step 2: Install the CA Certificate

Metacache generates a local Certificate Authority (CA) on first run. You must install this CA into the trust store of every machine running Radarr/Sonarr.

### Download the CA cert

```bash
curl -o metacache-ca.pem http://localhost:8765/proxy/ca-cert
```

### Install on each ARR host

**Windows:**
```powershell
certutil -addstore "Root" metacache-ca.pem
# Or double-click the .pem file → Install Certificate → Local Machine → Trusted Root
```

**macOS:**
```bash
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain metacache-ca.pem
```

**Linux:**
```bash
sudo cp metacache-ca.pem /usr/local/share/ca-certificates/metacache-ca.crt
sudo update-ca-certificates
```

## Step 3: Override DNS

You need to redirect these hostnames to your Metacache IP:
- `api.themoviedb.org`
- `image.tmdb.org`
- `api.thetvdb.com`
- `webservice.fanart.tv`

### Option A: Pi-hole / AdGuard Home (LAN-wide)

Add custom DNS entries:
```
192.168.1.100  api.themoviedb.org
192.168.1.100  image.tmdb.org
192.168.1.100  api.thetvdb.com
192.168.1.100  webservice.fanart.tv
```

### Option B: /etc/hosts (single machine)

```bash
echo "192.168.1.100 api.themoviedb.org image.tmdb.org api.thetvdb.com webservice.fanart.tv" | sudo tee -a /etc/hosts
```

### Option C: Docker Compose extra_hosts

```yaml
services:
  radarr:
    extra_hosts:
      - "api.themoviedb.org:192.168.1.100"
      - "image.tmdb.org:192.168.1.100"
      - "api.thetvdb.com:192.168.1.100"
      - "webservice.fanart.tv:192.168.1.100"
```

## Step 4: Verify

```bash
# Should return TMDB JSON (proxied through the cache)
curl -v https://api.themoviedb.org/3/movie/550 | head -c 200

# Check the X-Cache-Source header
curl -sI https://api.themoviedb.org/3/movie/550 | grep X-Cache-Source
# → X-Cache-Source: Upstream (first call)
# → X-Cache-Source: Cache (subsequent calls)
```

## Step 5: Check Proxy Status

```bash
curl http://localhost:8765/proxy/status
```

Returns:
```json
{
  "routedHostnames": [
    { "hostname": "api.themoviedb.org", "upstream": "https://api.themoviedb.org/3" },
    { "hostname": "image.tmdb.org", "upstream": "https://image.tmdb.org/t/p/original" },
    { "hostname": "api.thetvdb.com", "upstream": "https://api4.thetvdb.com" },
    { "hostname": "webservice.fanart.tv", "upstream": "https://webservice.fanart.tv/v3" }
  ],
  "caSubject": "CN=Metacache Local CA, O=Metacache",
  "caThumbprint": "AB12CD34..."
}
```

## Custom Routes

Add additional hostnames via config:

```json
{
  "Metacache": {
    "Proxy": {
      "Routes": {
        "custom.api.example.com": "https://api.example.com/v2"
      }
    }
  }
}
```

## Troubleshooting

**"SSL certificate problem: self-signed certificate":**
- The CA cert isn't installed in the trust store. Re-run Step 2.

**Radarr/Sonarr can't connect after DNS override:**
- Verify DNS: `nslookup api.themoviedb.org` should return your Metacache IP
- Check the proxy is listening: `curl -k https://localhost:443/healthz`

**"Connection refused" on port 443:**
- Ensure the proxy is enabled and the port isn't blocked by a firewall
- Check logs for certificate generation errors

## What Happens Under the Hood

1. Radarr resolves `api.themoviedb.org` to your Metacache IP (via DNS override)
2. Radarr connects to Metacache:443 with HTTPS + SNI for `api.themoviedb.org`
3. Metacache's `CertManager` presents a valid certificate for that hostname (signed by the local CA)
4. `ProxyMiddleware` reconstructs the full upstream URL from the SNI hostname + request path
5. `UpstreamCache` checks for a cached response — if fresh, serves it; if stale, revalidates with ETags
6. Response is served back to Radarr as if it came from the real API

## Security Notes

- The local CA is generated automatically and stored in `data/certs/`
- Only hostnames in the route table get certificates — unknown hostnames are rejected
- API keys in URLs are stripped from cache keys (they never appear in the database)
- The proxy uses constant-time token comparison for auth (when enabled)

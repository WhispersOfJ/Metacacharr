# Tutorial: Getting Started with Metacache

> **Goal:** Install Metacache, configure your TMDB API key, register the providers in Plex, and warm your first library.
>
> **Time:** ~15 minutes
>
> **Prerequisites:**
> - Plex Media Server 1.43+ (with Custom Metadata Providers enabled)
> - A TMDB API Read Access Token ([get one here](https://www.themoviedb.org/settings/api))
> - .NET 10 SDK or Docker

## Step 1: Get your TMDB API Key

1. Create a free account at [themoviedb.org](https://www.themoviedb.org)
2. Go to **Settings → API** and request an API Read Access Token
3. Copy the token (it starts with `eyJ...`)

## Step 2: Install Metacache

### Option A: Docker (recommended)

```bash
docker build -t metacache .
docker run -d --name metacache --network host \
  -e Metacache__Tmdb__ApiKey=YOUR_TOKEN_HERE \
  metacache
```

### Option B: From source

```bash
git clone https://github.com/WhispersOfJ/Metacacharr.git
cd Metacacharr
dotnet run --project src/Metacache.Host
```

Set the API key via environment variable:

```bash
Metacache__Tmdb__ApiKey=YOUR_TOKEN_HERE dotnet run --project src/Metacache.Host
```

## Step 3: Verify it's running

Open your browser or use curl:

```bash
curl http://localhost:8765/healthz
# → ok
```

Check the provider definition:

```bash
curl http://localhost:8765/movie | head -c 200
# → {"Name":"Metacache Movie Provider",...}
```

## Step 4: Register in Plex

1. Open Plex → **Settings → Metadata Agents**
2. Click **Add Provider**
3. Enter: `http://YOUR_SERVER_IP:8765/movie`
4. Click **Add Provider** again
5. Enter: `http://YOUR_SERVER_IP:8765/tv`

> **Tip:** Use the server's LAN IP, not `localhost` — Plex needs to reach Metacache over the network.

## Step 5: Configure Radarr/Sonarr (optional)

If you use Radarr or Sonarr, add their connection details to speed up warming:

```bash
# Docker
docker run -d --name metacache --network host \
  -e Metacache__Tmdb__ApiKey=YOUR_TOKEN \
  -e Metacache__Arr__RadarrUrl=http://localhost:7878 \
  -e Metacache__Arr__RadarrApiKey=YOUR_RADARR_KEY \
  -e Metacache__Arr__SonarrUrl=http://localhost:8989 \
  -e Metacache__Arr__SonarrApiKey=YOUR_SONARR_KEY \
  metacache
```

Or in `appsettings.json`:

```json
{
  "Metacache": {
    "Tmdb": { "ApiKey": "YOUR_TOKEN" },
    "Arr": {
      "RadarrUrl": "http://localhost:7878",
      "RadarrApiKey": "YOUR_RADARR_KEY",
      "SonarrUrl": "http://localhost:8989",
      "SonarrApiKey": "YOUR_SONARR_KEY"
    }
  }
}
```

## Step 6: Warm your library

```bash
curl -X POST http://localhost:8765/warm/all
```

Or use the **[Warm Progress UI](http://localhost:8765/ui/warm-progress)** for a real-time progress bar.

Wait for the warm to complete. You'll see output like:

```json
{
  "source": "all",
  "itemsWarmed": 847,
  "imagesWarmed": 1234,
  "elapsedSeconds": 42.5
}
```

## Step 7: Verify it's working

1. Go to your Plex library → **Refresh Metadata**
2. Check the Metacache console — you should see cache hits (no upstream calls)
3. Open the **[Dashboard](http://localhost:8765/dashboard)** — hit rate should be >90%

## What just happened?

1. **Metacache cached** all your movie/show metadata from TMDB/TVDB locally
2. **Plex refreshed** from the local cache instead of hitting upstream APIs
3. **Images are served** from local disk via `/img/{hash}` endpoints
4. **Future refreshes** hit the cache with ETag revalidation — only changed items fetch from upstream

## Next Steps

- [First Warm](02-first-warm.md) — Understand the warm process in detail
- [Multi-Language Warming](03-multi-language.md) — Cache metadata in multiple languages
- [Interactive Dashboard](../how-to/use-dashboard.md) — Explore the admin UI
- [ARR Proxy Setup](05-arr-proxy-setup.md) — Make Radarr/Sonarr hit the cache too

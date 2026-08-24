# How to: Configure Metacache URL

> Set the METACACHE_URL environment variable for webhook warming.

## Overview

The `METACACHE_URL` environment variable tells other services (Plex webhook listener, control panel) where to send warm requests.

## Step 1: Edit .env

Add to your `.env` file:

```bash
METACACHE_URL=http://metacache:8765
```

**Note**: Use the container name `metacache`, not `localhost`, since services communicate over Docker network.

## Step 2: Optional API Key

If Metacache has authentication enabled:

```bash
METACACHE_URL=http://metacache:8765
METACACHE_API_KEY=your-api-key
```

## Step 3: Restart Services

```bash
# Restart Plex webhook listener
docker compose restart plex-webhook-listener

# Or restart all services
docker compose down && docker compose up -d
```

## Step 4: Verify

Test the connection:

```bash
curl http://localhost:8765/healthz
```

## Common Configurations

### Local Docker Network

```bash
METACACHE_URL=http://metacache:8765
```

### External Metacache

```bash
METACACHE_URL=http://192.168.4.20:8765
```

### With Authentication

```bash
METACACHE_URL=http://metacache:8765
METACACHE_API_KEY=changeme
```

## Troubleshooting

**Connection refused**
- Verify Metacache is running: `docker compose ps metacache`
- Check network: `docker network inspect media-stack_stacknet`
- Test from container: `docker exec plex-webhook-listener curl http://metacache:8765/healthz`

**401 Unauthorized**
- Check METACACHE_API_KEY matches Metacache config
- Verify API key in Metacache logs: `docker compose logs metacache | grep auth`

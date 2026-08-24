# How to Register Metacache in Plex

> Register Metacache as a metadata provider in Plex Media Server.

## Prerequisites

- Metacache running and accessible from the Plex machine
- Plex Media Server 1.43+ with Custom Metadata Providers enabled

## Steps

### 1. Enable Custom Metadata Providers

1. Open Plex → **Settings** (gear icon)
2. Go to **Metadata Agents**
3. Ensure "Custom Metadata Providers" is enabled (PMS 1.43+)

### 2. Add the Movie Provider

1. Click **Add Provider**
2. Enter the URL:
   ```
   http://METACACHE_IP:8765/movie
   ```
3. Click **Save**

### 3. Add the TV Provider

1. Click **Add Provider** again
2. Enter the URL:
   ```
   http://METACACHE_IP:8765/tv
   ```
3. Click **Save**

### 4. Assign to a Library

1. Go to **Libraries** → select your library
2. Click **Edit** → **Advanced**
3. Set **Metadata Agent** to "Metacache Movie" (or "Metacache TV")
4. Set Metacache as the **Primary** agent

### 5. Test

1. Click **Refresh Metadata** on a few items
2. Check the Metacache console for log output
3. Open the **[Dashboard](http://METACACHE_IP:8765/dashboard)** — you should see requests

## Finding Your Server IP

```bash
# Linux/macOS
hostname -I | awk '{print $1}'

# Windows
ipconfig | findstr "IPv4"
```

## Copy-Paste URLs

Use the **[Registration Helper](http://METACACHE_IP:8765/ui/register)** for auto-detected URLs and step-by-step visual guide.

## Troubleshooting

**"Provider not found" in Plex:**
- Verify Metacache is running: `curl http://METACACHE_IP:8765/healthz`
- Check Plex can reach Metacache: no firewall blocking port 8765

**"Metadata not updating":**
- Click **Refresh Metadata** manually first
- Check Metacache logs for errors
- Verify the provider is set as Primary in library settings

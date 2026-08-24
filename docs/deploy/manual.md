# Deploy Manually

> Run Metacache as a self-contained binary without Docker.

## Prerequisites

- .NET 10 SDK (for building) or the published binary
- TMDB API key

## Build from Source

```bash
git clone https://github.com/WhispersOfJ/Metacacharr.git
cd Metacacharr
dotnet publish src/Metacache.Host -c Release -r linux-x64 --self-contained -o publish
```

This produces a self-contained binary in `publish/` — no .NET runtime needed on the target machine.

### Platform-specific builds

```bash
# Linux x64
dotnet publish src/Metacache.Host -c Release -r linux-x64 --self-contained -o publish

# Linux ARM64 (Raspberry Pi 4+)
dotnet publish src/Metacache.Host -c Release -r linux-arm64 --self-contained -o publish

# Windows x64
dotnet publish src/Metacache.Host -c Release -r win-x64 --self-contained -o publish

# macOS ARM64 (Apple Silicon)
dotnet publish src/Metacache.Host -c Release -r osx-arm64 --self-contained -o publish
```

## Run

```bash
# Set configuration via environment
export Metacache__Tmdb__ApiKey=YOUR_TOKEN
export Metacache__BindAddress=0.0.0.0
export Metacache__Port=8765

# Run the binary
./publish/Metacache.Host
```

Or with `appsettings.json`:

```bash
cp appsettings.json publish/appsettings.json
# Edit publish/appsettings.json with your config
./publish/Metacache.Host
```

## Run as a Service

### systemd (Linux)

Create `/etc/systemd/system/metacache.service`:

```ini
[Unit]
Description=Metacache Metadata Cache
After=network.target

[Service]
Type=simple
User=metacache
Group=metacache
WorkingDirectory=/opt/metacache
ExecStart=/opt/metacache/Metacache.Host
Restart=on-failure
RestartSec=5
Environment=Metacache__Tmdb__ApiKey=YOUR_TOKEN
Environment=Metacache__BindAddress=0.0.0.0

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable metacache
sudo systemctl start metacache
sudo systemctl status metacache
```

### launchd (macOS)

Create `~/Library/LaunchAgents/com.metacache.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.metacache</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/metacache/Metacache.Host</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>Metacache__Tmdb__ApiKey</key>
        <string>YOUR_TOKEN</string>
        <key>Metacache__BindAddress</key>
        <string>0.0.0.0</string>
    </dict>
</dict>
</plist>
```

Load:

```bash
launchctl load ~/Library/LaunchAgents/com.metacache.plist
```

## Data Directory

By default, Metacache stores data in the working directory:

```
./data/
├── metacache.db      # SQLite database
├── images/           # Cached artwork
└── certs/            # TLS certificates (proxy only)
```

Override with:

```bash
Metacache__DataPath=/var/lib/metacache/metacache.db
```

## Firewall

If the host has a firewall, open port 8765 (and 443 if using the proxy):

```bash
# UFW (Ubuntu)
sudo ufw allow 8765/tcp
sudo ufw allow 443/tcp

# firewalld (CentOS/RHEL)
sudo firewall-cmd --add-port=8765/tcp --permanent
sudo firewall-cmd --reload
```

## Verify

```bash
curl http://localhost:8765/healthz
# → ok

curl http://localhost:8765/movie
# → {"Name":"Metacache Movie Provider",...}
```

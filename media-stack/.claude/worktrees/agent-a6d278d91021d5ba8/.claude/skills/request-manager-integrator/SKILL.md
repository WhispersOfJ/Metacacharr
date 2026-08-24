---
name: request-manager-integrator
description: Configure and verify the request manager (Jellyseerr/Overseerr-family "seerr" service) integration with Radarr and Sonarr — connect it to the right instance, root folder, and quality profile, and confirm the connection is actually live. Use when the user asks to hook up seerr to radarr/sonarr, add a second quality-profile-specific connection, or troubleshoot "requests aren't showing up in radarr/sonarr". Trigger phrases: "connect seerr to radarr", "set up request manager", "requests aren't being sent to sonarr", "add a second radarr connection to seerr".
---

# Request Manager Integrator

Configures `seerr`'s Radarr/Sonarr "server" connections via its REST API, and verifies
end-to-end reachability (seerr -> Arr app) rather than just writing config and assuming
it works.

## Auth / config

```
SEERR_URL / SEERR_API_KEY         (defaults to http://localhost:5055)
RADARR_URL / RADARR_API_KEY       (same vars as arr-config-sync / trash-guides-applier)
SONARR_URL / SONARR_API_KEY
```

The Arr URL seerr needs to store is the **docker-internal** hostname (e.g.
`http://radarr:7878`), not `localhost` — seerr calls it from inside the compose network.
Never hardcode a LAN IP; always resolve via env var or docker service name.

## Usage

```bash
python3 integrator.py list-connections                       # what's currently configured in seerr
python3 integrator.py connect radarr --root /media/movies --profile "HD Bluray + WEB"
python3 integrator.py connect sonarr --root /media/tv --profile "WEB-1080p"
python3 integrator.py verify                                   # test every configured connection actually reaches its Arr app
```

`connect` looks up the target root folder and quality profile by name against the live
Arr instance (via the same API pattern as `arr-config-sync`) and fails loudly if either
doesn't exist yet, rather than writing a broken connection.

## Interpreting results

- `verify` failing for a connection that `list-connections` shows as configured usually
  means either the Arr app's API key was rotated (see `secret-injector`) without updating
  seerr, or the container-internal hostname changed — check
  `docker-compose-manager status <service>` to confirm the Arr container itself is up
  before assuming seerr's config is wrong.
- If requests silently vanish (accepted in seerr, never appear in Radarr/Sonarr queue),
  check the seerr connection's configured root folder against what
  `arr-config-sync list-apps`/`add-root-folder` shows as actually present in the Arr app.

## Safety rules

- `connect` never deletes or replaces an existing connection with the same name unless
  `--force` is passed — multiple connections per app (e.g. different quality-profile routing)
  are a normal, intentional pattern in this stack, not something to silently collapse.

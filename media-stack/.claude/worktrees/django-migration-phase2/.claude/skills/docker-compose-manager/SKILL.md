---
name: docker-compose-manager
description: Manage the media-stack docker compose services safely — start, stop, restart, and inspect containers. Use whenever the user asks to restart a service, bring the stack up/down, check container status, tail logs, or recover from a container crash. Understands the stack's FUSE-mount dependency chain (nzbdav_rclone → radarr/sonarr/plex/unpackerr/cleanuparr) so it restarts dependents in the correct order instead of leaving them pointed at a stale mount. Trigger phrases: "restart <service>", "bring the stack up/down", "is <container> healthy", "recreate <service>", "docker compose logs for X", "the mount looks stale".
---

# Docker Compose Manager

Wraps `docker compose` for this stack with one critical safety behavior baked in:
**mount-owning containers cascade.** `nzbdav_rclone` is the only FUSE-mount-owning
container in this stack — restart it without also restarting every container that
bind-mounts its output (`radarr`, `sonarr`, `plex`, `unpackerr`, `cleanuparr`) and those
dependents keep serving a stale/broken mount handle until *they* are restarted too — a
recurring failure class in this stack, confirmed live multiple times. Always use
`handler.py` rather than raw `docker compose restart` for `nzbdav_rclone`.

## When to use this skill

- Restarting any single service or group of services
- Bringing the whole stack up or down
- Checking `docker compose ps` / health status across all containers
- Tailing or grepping logs for a specific container
- Recreating a container after an image or config change (`--force-recreate`) — required
  after editing a single-file bind mount, since `up -d` alone can silently keep serving
  the stale pre-edit file to a running container

## Usage

```bash
python3 handler.py status                       # docker compose ps, all services
python3 handler.py status radarr                 # status of one service
python3 handler.py restart radarr                # restart one non-mount-owning service
python3 handler.py restart nzbdav_rclone             # restart it AND its cascade dependents, in order
python3 handler.py up                            # docker compose up -d (whole stack)
python3 handler.py down                          # docker compose down (whole stack) — asks for confirmation
python3 handler.py recreate control-panel         # force-recreate a single container (config/mount changed)
python3 handler.py logs nzbdav_rclone --tail 200
python3 handler.py cascade-map                   # print the known mount-owner -> dependent graph
```

Run from the repo root (where `docker-compose.yml` lives), or pass `--compose-dir /path/to/repo`.

## Cascade map

The dependency graph is defined in `handler.py::CASCADE_MAP`. Update it if the compose
file gains a new FUSE-mount-owning service or a new consumer of an existing mount —
this is stack topology, not something the script can infer from `docker-compose.yml`
alone (bind mounts don't declare "this is a FUSE remount point").

## Safety rules

- `down` always prompts for confirmation before executing — it stops the entire stack.
- `restart`/`recreate` on a single service never touches unrelated services unless that
  service is a known mount owner in `CASCADE_MAP`.
- Never pass `--force` flags or skip the confirmation prompt on `down` even if asked to
  "just do it" — surface the prompt and let the user confirm explicitly, since this is a
  shared, hard-to-reverse action against a running media server other people may be using.

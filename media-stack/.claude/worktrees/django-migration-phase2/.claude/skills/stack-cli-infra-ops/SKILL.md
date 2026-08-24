---
name: stack-cli-infra-ops
description: Exact fish CLI command reference for container control and infrastructure diagnostics against this stack's Control Panel (status, restart, resource/mount/permission/image checks, Seerr requests, top), plus a handful of local disk/backup commands that don't go through Control Panel at all (disk-free thresholds, Docker disk usage, a one-off Claude-dir tarball - restic-based backup verify/status/integrity-check were removed entirely 2026-08-12, see common_mistakes). Use whenever the user asks to check overall stack health, restart a container from the terminal, check disk free space or Docker's disk usage, or check for OOM kills, missing mem_limits, stale mounts, or unreadable config files. Trigger phrases: "check stack status", "restart this container", "any oom kills", "check mount health", "top containers by cpu", "seerr requests", "how much disk space is free", "docker disk usage breakdown".
---

# Stack CLI: Infra & Ops

<skill_scope skill="stack-cli-infra-ops">
This is a command reference, not an operational tool: it exists so the exact fish function name, argument order, and output shape for every container-control/diagnostic terminal command in this stack is already known, without reading the fish source fresh each time. Every command here is a thin fish wrapper around Control Panel's own HTTP API (`http://192.168.4.20:8420`); the actual behavior lives in `control-panel/main.py` plus `services/host/router.py` (`app.py` is retired dead code, not the live source; `services/backups/router.py` no longer exists - restic support was removed entirely 2026-08-12).

**Related skills:**
- `docker-compose-manager` operates one layer lower - it runs `docker compose` directly on the host with FUSE-mount cascade awareness (restarting `nzbdav_rclone`'s dependents in the right order). `stack-container`/`stack-restart-all` below go through Control Panel's own HTTP API instead, which has its own (separately maintained) mount-ordering logic for the whole-stack restart specifically, but no cascade awareness for a single-container restart. Prefer `docker-compose-manager` when a FUSE-mount-owning container needs restarting; either works for a plain application container.
- `health-monitor` is a broader Python sweep (Docker health + HTTP reachability across every service in one pass) meant for a general "is everything okay" triage. `stack-status` below is Control Panel's own live per-container view - similar purpose, different implementation, prefer whichever is already running or the user names.
</skill_scope>

## Calling convention

<calling_convention>
Many commands here (`stack-status`, `stack-resource-check`, `stack-mount-health`, `stack-oom-check`, `stack-perms-check`, `stack-image-check`, `stack-version`, `stack-backup-verify`, `stack-backup-restore-test`) are one-line `__stack_api GET/POST <path>` calls that just print the response's `message` field. `stack-backup-integrity-check` instead `curl`s `/api/backup-integrity-check` directly and pipes through an inline `python3 -c "..."` formatter, since it needs to print a per-repo status line, not just one message. The rest of the structured-output commands follow that same curl+python3 shape.

None of these read a `STACK_HOST_IP` environment variable - the Control Panel URL is a literal hardcoded string in every function.

**Three commands in this file are not Control Panel wrappers at all** - `stack-claude-full-backup`, `stack-disk-free`, and `stack-docker-disk-usage` run local tools directly (`tar`, `df`, `docker system df`) against this host, with no HTTP call anywhere in their source. They're grouped here by theme (backup/disk), not by mechanism - don't assume every command in this file hits `192.168.4.20:8420` just because most of them do.
</calling_convention>

## Command reference

<command_reference>
| Command | Args | What it does |
|---|---|---|
| `stack-status` | none | Live state/health of every container in the stack. |
| `stack-container` | `<restart\|stop\|start> <container-name>` | Controls one container by name. No confirmation prompt - unlike `stack-restart-all`, a single-container action isn't gated. |
| `stack-restart-all` | `[-y\|--yes]` | Restarts every container in the stack (~20 services; the exact running count drifts - `kometa` in particular exits after each scheduled run rather than staying up, see `/api/version`'s "N/M containers running" for the live figure). Prompts for confirmation unless `-y`/`--yes` is given, mirroring the arm/confirm double-click the web UI uses for the same "danger zone" action. |
| `stack-resource-check` | none | Containers missing an explicit `mem_limit`/`cpus` in `docker-compose.yml` - these silently inherit the full host ceiling instead of a real number. |
| `stack-log-levels` | `[reset]` (no arg = check) | Checks, or resets to default, every Servarr app's log level. |
| `stack-mount-health` | none | Confirms every known FUSE mountpoint (currently just `nzbdav_rclone`'s) resolves cleanly. |
| `stack-oom-check` | none | Containers Docker has recorded an OOM-kill for - the only reliable way to catch one, since `restart: unless-stopped` silently restarts a killed container with no other visible symptom. |
| `stack-perms-check` | none | Config files unreadable by group/other - these silently fail to back up rather than erroring loudly. |
| `stack-image-check` | none | Checks digest- or exact-version-pinned images for a newer registry digest (channel-tag images are already covered by Watchtower and not what this checks). |
| `stack-disk-config-sizes` | none | Per-app `config/` directory size, largest first. |
| `stack-disk-free` | `[warn-pct default 80] [crit-pct default 90]` | `df -h` filtered to real filesystems (tmpfs/devtmpfs/overlay/squashfs excluded), one `[ok\|warn\|FAIL]` line per mount by use percentage. Host-level free space - distinct from `stack-disk-config-sizes`'s per-app `config/` directory sizes. |
| `stack-docker-disk-usage` | none | `docker system df` - images/containers/volumes/build-cache totals. Which Docker-managed category is eating disk, not per-app config size (`stack-disk-config-sizes`) and not host filesystem free space (`stack-disk-free`). |
| `stack-version` | none | This repo's README-declared version plus a live core/extras container count - a doc-vs-reality drift check. |
| `stack-claude-full-backup` | none | One-off full `~/Claude` tree `tar.zst` (no excludes) to `~/Dropbox/Stack and Claude Backups`, dated (`Claude-full-backup-YYYYMMDD.tar.zst`) - see common_mistakes before treating this as a real backup mechanism. |
| `stack-notify-test` | none | Sends a real test message through the stack's Discord webhook - confirms it still works without waiting for a real failure to find out it doesn't. |
| `stack-top` | `[cpu\|mem] [limit]` (default cpu, 10) | Top containers by resource usage, compact - faster than scanning every card in the dashboard grid. |
| `stack-seerr-requests` | `[pending\|approved\|available\|all]` (default pending) | Media requests sitting in Seerr, by status - confirms a request actually landed there before chasing why it's not showing up in Radarr/Sonarr. |
</command_reference>

## Common mistakes

<common_mistakes>
<general_anti_patterns>
- **Using `stack-container restart` on `nzbdav_rclone` or any FUSE-mount owner.** This command has no cascade awareness - restarting a mount-owning container without also restarting everything that bind-mounts its output (radarr, sonarr, plex, unpackerr, cleanuparr) leaves those dependents serving a stale mount handle until *they're* separately restarted. Use `docker-compose-manager`'s cascade-aware restart for that container specifically, not this.
- **Reading "container looks up" as "container is fine."** `restart: unless-stopped` means an OOM-killed container just silently restarts with no other visible symptom - `stack-oom-check` is the only way this class of problem surfaces; a clean `stack-status` doesn't rule it out.
- **Treating `stack-claude-full-backup` as a real disaster-recovery mechanism.** It isn't. As of 2026-08-12 this stack has zero automated backup coverage - restic (and everything that read it: `stack-backup-verify`/`stack-backup-status`/`stack-backup-restore-test`/`stack-backup-integrity-check`) was removed entirely at explicit user request pending a new backup solution. `stack-claude-full-backup` is a manual, one-off `tar.zst` of the whole `~/Claude` tree to Dropbox, dated (`Claude-full-backup-YYYYMMDD.tar.zst`, one retained copy per day, overwritten if run twice the same day) - a convenience snapshot, not a real DR mechanism, and not a substitute for whatever replaces restic.
</general_anti_patterns>

<from_fish>
- **Naming a local variable `status` in a fish script, expecting it to shadow cleanly.** `status` is a fish builtin tied to the last command's exit code; `set -l status ...` is silently rejected, so every later `$status` read falls through to the builtin instead of the intended value. Confirmed live in `stack-seerr-requests.fish` itself, which names its own local variable `req_status` specifically to avoid this - a real, previously-hit bug (produced `filter=1` in the request URL instead of `filter=pending`), not a hypothetical. The same class of trap exists in zsh with the `path` array; check for a reserved-name collision before assuming a local variable in either shell behaves like an ordinary local.
</from_fish>
</common_mistakes>

## Resources

<resources>
**Local:**
- `~/.config/fish/functions/stack-status.fish`, `stack-container.fish`, `stack-restart-all.fish`, `stack-resource-check.fish`, `stack-log-levels.fish`, `stack-mount-health.fish`, `stack-oom-check.fish`, `stack-perms-check.fish`, `stack-image-check.fish`, `stack-disk-config-sizes.fish`, `stack-disk-free.fish`, `stack-docker-disk-usage.fish`, `stack-version.fish`, `stack-backup-*.fish`, `stack-claude-full-backup.fish`, `stack-notify-test.fish`, `stack-top.fish`, `stack-seerr-requests.fish` - the actual fish source these commands wrap
- `control-panel/main.py` + `services/host/router.py` in this repo - the real behavior behind every Control-Panel-backed endpoint these commands call (does not cover `stack-claude-full-backup`, `stack-disk-free`, `stack-docker-disk-usage` - those run local tools directly, see calling_convention)
- `scripts/backup-claude-dir.sh` in this repo - the separate, systemd-scheduled, overwrite-in-place tarball script `stack-claude-full-backup` is often confused with; read this file's own comments to see why it's not the same thing
</resources>

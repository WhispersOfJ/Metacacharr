---
name: stack-cli-system-maintenance
description: Exact fish CLI command reference for host/Arch-Linux-admin terminal commands on this stack's specific host - pacman/AUR/Flatpak updates, package history/orphans/cache, security advisories, disk/SMART health, systemd journal size and failed units, stack-*.timer health, firewall rules, SSH setup health, kernel/reboot status, zombie processes, memory pressure, scheduled jobs, and git status across every repo under ~/Claude. Use whenever the user asks to check for pending updates, whether a reboot is needed, disk or SMART health, failed services, SSH key health, journal disk usage, zombie processes, or scheduled jobs. Trigger phrases: "check for pending updates", "is a reboot needed", "check disk health", "list failed services", "check ssh keys", "vacuum the journal", "any zombie processes", "list scheduled jobs", "check kernel version", "any orphaned packages", "check the firewall", "git status across my repos".
---

# Stack CLI: System Maintenance

<skill_scope skill="stack-cli-system-maintenance">
This is a command reference, not an operational tool: it exists so the exact fish function name, argument order, and output shape for every host/Arch-Linux-admin terminal command in this stack is already known, without reading `~/.config/fish/functions/stack-*.fish` fresh each time. **Unlike every other `stack-cli-*` skill in this repo, none of these commands are Control Panel wrappers.** They call local system tools directly - `pacman`, `paccache`, `checkupdates`, `paru`/`yay`, `flatpak`, `arch-audit`, `smartctl`, `systemctl`, `journalctl`, `ss`, `nft`, `git`, `ps`, `crontab` - with no HTTP call, no Control Panel dependency, and no `control-panel/app.py` route behind any of them.
</skill_scope>

## Calling convention

<calling_convention>
These are **local host commands, not Control Panel API wrappers.** Every other `stack-cli-*` skill in this repo documents a thin fish wrapper around Control Panel's HTTP API (`http://192.168.4.20:8420`), runnable from any machine on the LAN or Tailscale mesh per `stack-cli-arr-fleet`'s own note. **Commands in this file are the opposite**: they shell out to whatever's actually installed on this one Arch/CachyOS host, read this host's own `/proc`, `/var/log`, `systemd` state, and `~/.ssh`/`~/Claude` directories directly. They only work when run *on this host* - there is nothing to reach over the network for, and running them from another machine would just report that other machine's (usually irrelevant, possibly nonexistent-pacman) state instead.

Most commands here degrade gracefully rather than assuming a fixed toolchain forever: they `type -q` check for an optional binary (`checkupdates`, `paru`/`yay`, `arch-audit`, `smartctl`, `flatpak`) and print a stderr note plus a fallback or early return instead of erroring opaquely if it's missing. Several mutating ones (`stack-pkg-update`, `stack-pkg-orphans --remove`, `stack-flatpak-updates --apply`) prompt for `[y/N]` confirmation unless a flag skips it, and shell out through `sudo -n` (passwordless sudo, already configured on this host) for the actual privileged action.
</calling_convention>

## Command reference

<command_reference>
| Command | Args | What it does |
|---|---|---|
| `stack-pkg-updates` | none | Pending pacman (via `checkupdates`, doesn't touch the local sync db) + AUR (`paru`/`yay -Qua`) updates, counted and listed. Read-only. |
| `stack-pkg-update` | `[--yes]` | Runs the actual update (`pacman -Syu`, then `paru`/`yay -Sua` if present). Confirmation-gated unless `--yes`. |
| `stack-pkg-history` | `[N default 20]` | Tail of `/var/log/pacman.log`'s install/remove/upgrade lines - what actually changed recently. |
| `stack-pkg-orphans` | `[--remove]` | Lists packages installed as a dependency that nothing depends on anymore (`pacman -Qdtq`). `--remove` actually removes them (confirmation-gated); without it, read-only. |
| `stack-pkg-clean-cache` | `[keep-N default 3]` | Vacuums pacman's package cache to the last N versions per package (`paccache -rk`). |
| `stack-aur-audit` | none | Cross-checks installed packages against Arch security advisories via `arch-audit` if installed; otherwise falls back to listing foreign/AUR packages (`pacman -Qm`) instead, since those have no distro security-tracking net at all. |
| `stack-flatpak-updates` | `[--apply]` | Lists pending Flatpak updates (`flatpak remote-ls --updates`); `--apply` runs them (confirmation-gated). |
| `stack-firewall-status` | none | Active nftables tables (`nft list tables`, needs sudo) plus every port this host is actually listening on (`ss -tlnp`). |
| `stack-git-status-all` | none | `git status --short` + current branch across every repo directly under `~/Claude` in one pass. |
| `stack-journal-errors` | none | Error-or-worse `journalctl` entries since last boot, summarized by unit with a frequency count - a recurring problem shows its count instead of scrolling past it N times. |
| `stack-journal-size` | `[--vacuum-size SIZE]` | Shows journald's on-disk usage (`journalctl --disk-usage`); `--vacuum-size` (e.g. `500M`) trims it down via `sudo journalctl --vacuum-size=`. |
| `stack-kernel-check` | none | Compares the running kernel (`uname -r`) against the installed package version, inferring the right package name (`linux-cachyos`/`linux-zen`/`linux-lts`/`linux`) from the running kernel's own suffix. Mismatch means a reboot is needed to load an already-installed kernel. |
| `stack-mem-pressure` | none | Kernel PSI (`/proc/pressure/{memory,cpu,io}`) snapshot - actual resource contention over time, which `free`/`top` don't show. |
| `stack-cron-list` | none | Every scheduled job on this host in one place: system `systemctl list-timers`, user `systemctl --user list-timers`, user crontab, root crontab (needs sudo). Broader than `stack-timer-status` - covers everything scheduled, not just this stack's own timers. |
| `stack-timer-status` | none | Enabled state + last-run `Result` for every `stack-*.timer` unit specifically, via `systemctl --user list-unit-files`/`show` (not `list-timers`, whose columns are unreliable to parse positionally - see common_mistakes). Surfaces a timer that fires on schedule but whose service fails every time - not visible from `stack-cron-list`'s raw listing or from `stack-service-failed` unless the service is actually left in `failed` state. |
| `stack-ssh-doctor` | none | Checks `~/.ssh` exists, `known_hosts` has a `github.com` entry, and at least one private key (`id_*`, non-`.pub`) is present. |
| `stack-uptime-report` | none | `uptime`, last-boot time (`who -b`), and the previous boot's last few journal lines for a reboot/shutdown/power message - a clean vs. crash-shutdown signal. |
| `stack-zombie-check` | none | Lists zombie/defunct processes (`ps` STAT `Z`) and their parent PID - a persistent zombie points at a parent that never reaps its children. |
| `stack-disk-health` | none | SMART overall-health plus reallocated/pending-sector counts (via `smartctl`) for every physical disk found by `lsblk` (zram excluded) - needs sudo. |
| `stack-reboot-check` | none | Checks `/var/run/reboot-required` *and* calls `stack-kernel-check` internally - a single yes/no answer that is a strict superset of `stack-kernel-check` alone (see common_mistakes). |
| `stack-service-failed` | none | `systemctl --failed` across both the system and user manager instances. |
| `stack-help` | none | Master command-discovery entrypoint - lists every `stack-*` command in this stack's fish functions (Control-Panel-backed and local alike) with a one-line description each. Run this first if unsure a command exists at all, in this file or any other `stack-cli-*` skill. |
</command_reference>

## Common mistakes

<common_mistakes>
<general_anti_patterns>
- **Running any command in this file expecting it to work from another machine.** Every other `stack-cli-*` skill's commands go through Control Panel's HTTP API and work from any LAN/Tailscale machine (see `stack-cli-arr-fleet`'s calling convention). These do not - they read this specific host's own `pacman`/`systemd`/`/proc`/`~/.ssh` state. Running `stack-pkg-updates` from a different machine just reports (or fails against) that machine's own package state, not this stack's host.
- **Treating `stack-kernel-check` and `stack-reboot-check` as two independent checks to run separately.** `stack-reboot-check` already calls `stack-kernel-check` internally, in addition to checking the `/var/run/reboot-required` marker. It's a strict superset - if the goal is "do I need to reboot," reach for `stack-reboot-check` alone rather than running both.
- **Assuming `stack-service-failed` catches every broken `stack-*.timer`.** It only lists units systemd currently has parked in `failed` state - a timer that fires on schedule but whose service exits nonzero without staying in `failed` (or hasn't run since the last `daemon-reload`/reboot) won't show up there. `stack-timer-status` checks last-run `Result` for every `stack-*.timer` directly and is the one that actually caught the real `%h`/path bug referenced in its own source, which `stack-service-failed` did not surface.
- **Parsing `systemctl list-timers`' own columns positionally to check a timer's status.** `stack-timer-status`'s own source notes why it deliberately avoids this: `list-timers`' NEXT/LAST fields are themselves multi-word datetimes that silently shift the `ACTIVATES` (service name) column out of the position a naive parser expects `UNIT` (timer name) to be in. It uses `list-unit-files` + `systemctl show --property=Result` instead - follow that pattern rather than re-parsing `list-timers` output by hand.
</general_anti_patterns>

<from_fish>
- **Assuming `stack-pkg-updates`/`stack-pkg-orphans`/`stack-aur-audit`/`stack-flatpak-updates` always have output to show.** Each checks `type -q` for its optional dependency (`checkupdates`, `paru`/`yay`, `arch-audit`, `flatpak`) first and prints a stderr fallback note instead of erroring if it's missing - a silent/empty-looking result on a host missing `pacman-contrib` (no `checkupdates`) is expected, not a bug.
- **Naming a local variable `status` in a fish function.** Same class of reserved-name collision as `stack-cli-infra-ops`'s note on `stack-seerr-requests.fish` - `stack-pkg-update.fish` and `stack-claude-full-backup.fish` (see `stack-cli-infra-ops`) both deliberately name their exit-code locals `status_pacman`/`tar_status` instead of `status`, since fish reserves `$status` for the last command's own exit code and silently rejects an assignment to it.
</from_fish>
</common_mistakes>

## Resources

<resources>
**Local:**
- `~/.config/fish/functions/stack-pkg-*.fish`, `stack-aur-audit.fish`, `stack-flatpak-updates.fish`, `stack-firewall-status.fish`, `stack-git-status-all.fish`, `stack-journal-*.fish`, `stack-kernel-check.fish`, `stack-mem-pressure.fish`, `stack-cron-list.fish`, `stack-timer-status.fish`, `stack-ssh-doctor.fish`, `stack-uptime-report.fish`, `stack-zombie-check.fish`, `stack-disk-health.fish`, `stack-reboot-check.fish`, `stack-service-failed.fish`, `stack-help.fish` - the actual fish source these commands run
- No `control-panel/app.py` route backs any command in this file - see calling_convention
</resources>

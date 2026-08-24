# Host Privileged-Action Helper — Research & Design

**Written:** 2026-08-07, mid-session, ahead of a deliberate context reset. Separate
document/separate task from the control-panel redesign by explicit request — this is
the "how do we let the panel trigger reboot/package-update safely" problem flagged as
an open design question in Phase 03 (`321a8be`) and in the original design-treatment
artifact's risk table.

**Research status:** grounded in known Linux/container privilege-separation patterns
(D-Bus/polkit, minimal RPC sidecars, the project's own existing nsenter precedent) —
this is well-established infrastructure territory, not fast-moving enough to need live
search to get right. `WebSearch` was rate-limited mid-research this session (resets
~12:10pm daily); if a future session has it available, a quick pass confirming current
(2026) best-practice writeups on "docker container triggers host reboot" or "minimal
privileged sidecar RPC pattern" would be useful *confirmation*, not a prerequisite —
the architecture below doesn't depend on anything that would have changed recently.

## The problem, precisely

Control-panel can already read real host state (mount health, disk usage, live
CPU/RAM via `/host-proc`) and can restart/stop/start/exec into any *container* it
manages (via `docker.sock`). It cannot currently:
- Reboot the host
- Run `apt update`/`apt upgrade` on the host
- Restart a host-level (non-Docker) service

All three are genuinely useful "PC maintenance" asks from the original request. All
three are also **irreversible or disruptive** actions on the literal machine everything
else runs on — this is categorically different from "restart the sonarr container,"
which is a decision I don't need to escalate. **This is why Phase 03 stopped short of
building it and flagged it instead of quietly picking an approach.**

## Why this can't just reuse what already exists

The container already holds `pid: host`, `cap_add: [SYS_ADMIN, SYS_PTRACE]`, and
`util-linux` (for `nsenter`) — added for one narrow purpose (Plex Health's D-state
introspection and the FUSE-unstick `nsenter`-into-host-mount-namespace recovery
action). Technically, `nsenter --target 1 --mount --pid -- systemctl reboot` from
inside this container **would already work today** — no new capability grant needed.

**This is explicitly the wrong path, and should stay unbuilt.** The existing
`nsenter` usage is one hardcoded command for one narrow recovery scenario, called from
one specific code path. Turning that same latent capability into a general "run a host
command via nsenter" surface — even gated behind a confirm dialog — would mean that
compromising the control-panel container (XSS, a future dependency CVE, SSRF chained
through one of the many external API calls it already makes) is equivalent to
compromising the host as root. That is a categorically larger blast radius than
anything else this panel does, including its existing `docker.sock` access, and it
would happen silently — the Linux capabilities enabling it are already granted, so
nothing in `docker-compose.yml` would even change to signal the widening. **Naming this
explicitly is the point of this document existing** — see CLAUDE.md's Confusion
Protocol and the "never a blanket sudo grant" line from the original risk table.

## Three real architectures considered

### Option A — D-Bus + systemd-logind, brokered by polkit

Mount the host's system D-Bus socket (`/run/dbus/system_bus_socket`) into the
container (or, better, into a narrow proxy — see caveat below) and call
`org.freedesktop.login1.Manager.Reboot()` directly. This is *the* standard Linux
mechanism for "let a non-root process trigger a reboot" — it's what `loginctl reboot`
and every desktop's power button use. Authorization is enforced by **polkit**, not by
whatever process makes the call, via a `.rules`/`.pkla` file scoped to a specific
Unix UID or group.

- **Covers reboot/poweroff natively, with zero custom privileged code.** polkit and
  logind are already on the host, already audited by the distro, already the
  battle-tested layer here.
- **Does not cleanly cover package updates.** `PackageKit`
  (`org.freedesktop.PackageKit`) is the D-Bus equivalent for that, but it's not
  guaranteed installed/enabled on a headless server distro the way logind is, and
  configuring it is its own project (it also wants to own the update transaction, not
  just shell out to apt — more moving parts than this problem needs for a homelab of
  one).
- **Real caveat:** mounting the *raw* system bus socket gives the container the
  ability to *attempt* calls to every D-Bus service on the host, not just logind —
  polkit is what stops unauthorized ones from succeeding, but that means correctness
  depends entirely on getting the polkit rule right, with no defense-in-depth if it's
  misconfigured. A `dbus-proxy` (e.g. `xdg-dbus-proxy`, originally built for Flatpak
  sandboxing) can filter the socket down to only the `org.freedesktop.login1`
  interface before it ever reaches the container — this is the piece that makes Option
  A actually narrow rather than "trust polkit config perfectly."

### Option B — Minimal privileged sidecar, custom Unix-socket RPC, fixed verb allowlist

A small (~100–150 line) daemon running **on the host directly** (a systemd service,
not a Docker container — it needs to run actions as host root, so containerizing it
buys nothing and adds a namespace to reason about for no benefit), listening on a Unix
domain socket owned by a dedicated group (e.g. `controlpanel-helper`, socket mode
`0660`). The socket is bind-mounted **read-write** into the control-panel container
(one new mount, nothing else changes about its existing privileges).

The daemon's entire interface is a **fixed, closed enum of verbs** — never a shell
string, never a templated command, never "here's an arg, go run it":
```
{"action": "reboot"}
{"action": "apt_update"}
{"action": "apt_upgrade"}
{"action": "restart_unit", "unit": "<name>"}   # unit must be in a hardcoded allowlist
```
Each verb maps to exactly one hardcoded `subprocess.run([...])` call with a literal
argument list (no `shell=True`, no string interpolation of anything caller-supplied
into a command line). `restart_unit` is the only parameterized verb, and its parameter
is checked against a compile-time allowlist, not accepted freely.

- **Smallest, most auditable attack surface of the three options.** The daemon *is*
  the security boundary — reviewing it means reading ~150 lines once, not reasoning
  about D-Bus method authorization or nsenter namespace semantics.
- **Covers package updates cleanly** (`apt_update`/`apt_upgrade` are just subprocess
  calls, no PackageKit dependency) as well as reboot.
- **Compromise of the calling container only grants the fixed verb set** — not "root
  on the host," not "every D-Bus service," just whatever this specific daemon chose to
  expose. If that's just `reboot` + `apt_upgrade`, that's the actual ceiling.
- **Real caveat:** this is custom code that has to be *written correctly* and
  *maintained* — the security property comes entirely from the implementation
  discipline (never adding a verb that takes free-form input), not from an external
  system like polkit enforcing it. It needs its own test coverage, same rigor as
  everything else in this project.
- **Precedent this resembles:** this is the same shape as any well-designed
  constrained-admin-API — the corrected pattern after early "let orchestration tools
  exec arbitrary host commands" designs (early Consul-exec, some early CI runners)
  were rightly criticized for being too permissive. The fix industry converged on was
  always "explicit allowlisted verbs, no shell templating" — exactly this.

### Option C — Reuse the existing nsenter/SYS_PTRACE capability directly

Covered above under "why this can't just reuse what already exists." **Rejected.**
Documenting it as a considered-and-rejected option, not an oversight, in case a future
session is tempted by "we already have the capability, why build something new" — the
answer is: because the *scope* of what that capability is used for matters as much as
whether it exists.

## Recommendation

**Option B (minimal privileged sidecar).** Reasoning:

1. It's the only option that cleanly covers both reboot *and* package updates without
   pulling in a second subsystem (PackageKit) that isn't already part of this stack's
   footprint.
2. Its security property is legible in one file, not distributed across a D-Bus policy
   file, a polkit rule, and a proxy config — easier to get right once and verify later.
3. It matches this project's own stated principle from the risk table almost exactly:
   *"a narrow host-side helper, never a blanket sudo grant."* Option B **is** that
   sentence, implemented.

Option A is a legitimate second choice if reboot/poweroff turns out to be the *only*
action ever wanted (skip package updates entirely) — in that narrow case, using
logind's own native mechanism instead of writing custom code is arguably more
"vanilla by default" per this project's own tech-choice rule. Worth an explicit
question to Bear before building, not an assumption either way.

## Implementation shape (Option B), once approved

**This section is the plan for *if and when* Bear explicitly approves standing up a
new host-level privileged component — nothing here should be auto-applied.** Standing
up a new sudoers-equivalent privilege boundary on the host is exactly the class of
action this project's own safety rules require stating plainly and waiting on, not
executing as a natural extension of "implement the feature":

1. **Host-side daemon** (`scripts/host-helper/helper.py` or similar, ~150 lines):
   listens on `/run/controlpanel-helper.sock`, fixed verb dispatch table, structured
   logging of every request (who/what/when/result) to a file Bear can audit
   independently of the panel's own logs.
2. **Host-side systemd unit + socket unit**: socket-activated (`helper.socket` +
   `helper.service`), so the daemon isn't a standing process, only spins up per
   request. Socket owned by a new dedicated group; only that group (and the
   control-panel container's mapped UID/GID) can connect.
3. **One new bind mount** in `docker-compose.yml` for control-panel:
   `/run/controlpanel-helper.sock:/host-helper.sock` (read-write, matches this
   project's existing pattern of naming host-mapped paths `/host-*`). No new
   `cap_add`, no new `pid`/`security_opt` changes needed — the container just gets a
   socket to talk to, same shape as the existing `docker.sock` mount.
4. **Container-side client** (`core/host_helper_client.py`): thin wrapper sending
   JSON over the Unix socket, timeout-bounded, raising the same `fail()`-shaped errors
   as every other integration in this codebase on failure/timeout/socket-not-present
   (degrade gracefully if the host hasn't installed the helper yet — this feature must
   be optional, not a hard dependency of the panel booting).
5. **New router** (`services/host_actions/router.py` or extend `services/host/`):
   `POST /api/host/reboot`, `POST /api/host/apt-update`, `POST /api/host/apt-upgrade`,
   each `current_user`-only (session required, matching every other destructive action
   in this app), each requiring `confirm: true` in the body (matching the
   catalog/prune/disk-health pattern already established in Phases 02–03), each
   double-guarded client-side with the existing `armButton` click-twice pattern.
6. **Tests**: mock the Unix-socket client the same way `docker_client`/`httpx` are
   mocked elsewhere — a fake socket server or a mocked client class, verifying the
   confirm-gate, the session-required gate, and that a missing helper socket degrades
   to a clear error rather than a crash.
7. **Docs**: a `scripts/host-helper/README.md` explaining what it grants, how to
   install/uninstall it, and how to verify it's working — since this is the one part
   of the whole redesign that changes the host's actual security posture, it deserves
   documentation good enough that Bear (or anyone auditing this stack later) can
   understand exactly what door was opened, and close it by removing one systemd unit
   if he ever wants to.

## Open questions for Bear before implementation starts

- Confirm Option B over Option A (or A-for-reboot-only + skip package updates
  entirely) — see Recommendation above.
- Confirm the exact verb list wanted (reboot + apt update + apt upgrade, per the
  original ask — anything else, e.g. restarting a specific host-level service, should
  be named explicitly rather than left as a vague "restart_unit" escape hatch).
- Confirm whether this should auto-run on any schedule (e.g. unattended nightly `apt
  update` check, human-confirmed `apt upgrade`) or stay 100% manual-trigger-only —
  this materially changes whether `apt_update`'s output needs surfacing back into the
  panel as a "N packages available" indicator, not just a fire-and-forget action.

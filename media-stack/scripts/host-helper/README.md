# controlpanel-helper

A minimal, privileged host-side daemon that lets the `control-panel` container
trigger a **fixed, closed set** of real host-level actions it otherwise has no
way to perform: reboot, and a pacman sync/upgrade. Full design rationale is in
`.claude/plans/host-privileged-helper.plan.md` (Option B - chosen over D-Bus/
polkit and over widening the container's existing `nsenter` capability).

## What this actually grants

Anything that can write to `/run/controlpanel-helper.sock` can ask this daemon
to run exactly one of three things, and nothing else:

| Action | Command | What it does |
|---|---|---|
| `reboot` | `systemctl reboot` | Reboots the host. Immediately, no confirmation at this layer - the confirmation gate lives in the control-panel UI/API, one layer up. |
| `pacman_sync` | `pacman -Sy --noconfirm` | Refreshes the package database only. No packages are installed or changed. |
| `pacman_upgrade` | `pacman -Syu --noconfirm` | Runs a full system upgrade. |

There is no fourth verb, no way to pass arguments into any of these commands,
and no shell involved (`subprocess.run([...])` with a literal argv list, never
`shell=True`, never string interpolation). Reviewing `helper.py` in full (~150
lines) is reviewing the entire security boundary - there's nothing else to it.

**This is real root access to three specific actions**, not a toy. Treat
installing it with the same weight as adding anyone to `sudoers` - because
that's functionally what it is, scoped to three commands instead of all of
them.

## Install

1. Create the daemon's dedicated group and copy the code into place:
   ```
   sudo groupadd --system controlpanel-helper
   sudo mkdir -p /opt/controlpanel-helper
   sudo cp scripts/host-helper/helper.py /opt/controlpanel-helper/helper.py
   ```
2. Install the systemd units:
   ```
   sudo cp scripts/host-helper/controlpanel-helper.socket /etc/systemd/system/
   sudo cp scripts/host-helper/controlpanel-helper.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now controlpanel-helper.socket
   ```
   Only the *socket* unit needs enabling - `controlpanel-helper.service` is
   socket-activated and systemd starts it automatically on the first
   connection, per request, rather than running as a standing process.
3. Confirm the socket exists and is owned correctly:
   ```
   ls -l /run/controlpanel-helper.sock
   # expect: srw-rw---- root controlpanel-helper
   ```
4. Uncomment the `controlpanel-helper.sock` bind mount in `docker-compose.yml`'s
   `control-panel` service (search for `HOST_HELPER_SOCKET`), then
   force-recreate the container:
   ```
   docker compose up -d --force-recreate control-panel
   ```
   Until this mount is added, `/api/host/reboot`, `/api/host/pacman-sync`, and
   `/api/host/pacman-upgrade` return a clear 503 ("Host helper isn't
   installed on this host") rather than crashing the panel - this feature is
   optional, not a hard dependency of the panel booting.

## Verify

```
echo '{"action": "pacman_sync"}' | sudo -u <a user in the controlpanel-helper group> \
  python3 -c "
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect('/run/controlpanel-helper.sock')
s.sendall(sys.stdin.read().encode() + b'\n')
s.shutdown(socket.SHUT_WR)
print(s.recv(65536).decode())
"
```
Or, once the container has the socket mounted, just use the panel's UI (Host
section → the three new action rows) - each requires clicking the action
button twice (arm, then confirm), matching every other destructive action in
this panel.

Every request - successful or not - is logged to `/var/log/controlpanel-helper.log`
(action, outcome, return code, timestamp), independent of the control-panel's
own logs. Check `journalctl -u controlpanel-helper.service` for stdout/stderr
from the daemon itself (startup errors, crashes) - the request log above is
the audit trail; the journal is for debugging the daemon.

## Uninstall

```
sudo systemctl disable --now controlpanel-helper.socket
sudo rm /etc/systemd/system/controlpanel-helper.socket /etc/systemd/system/controlpanel-helper.service
sudo systemctl daemon-reload
sudo rm -rf /opt/controlpanel-helper
sudo groupdel controlpanel-helper
```
Then remove (or re-comment) the socket bind mount in `docker-compose.yml` and
recreate `control-panel`. This closes the door completely - the panel falls
back to the same 503 behavior as if the helper had never been installed.

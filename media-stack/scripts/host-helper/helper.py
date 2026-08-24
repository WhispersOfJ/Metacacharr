#!/usr/bin/env python3
"""controlpanel-helper - minimal privileged host-action daemon.

Listens on a systemd-activated Unix socket, dispatches a fixed, closed
set of verbs (VERBS below) to hardcoded subprocess argv lists - never a
shell string, never a templated command, never a caller-supplied
argument reaching a command line. This IS the security boundary between
the control-panel container (root-in-container, but never root-on-host)
and actions that only host root can take. See
.claude/plans/host-privileged-helper.plan.md for the full design
rationale (Option B - minimal privileged sidecar - chosen over D-Bus/
polkit and over widening the container's existing nsenter capability).

Protocol: one connection per request. Client sends one newline-terminated
JSON object ({"action": "<verb>"}), then half-closes its write side.
Daemon replies with one newline-terminated JSON object
({"ok": bool, "message": str, "returncode": int|null}) and closes.

Runs as root (systemd service, User=root - the actions it performs
require it). Every request is logged to LOG_PATH with the action,
outcome, and return code, independent of the control-panel's own logs,
so this daemon's log is the audit trail Bear can check regardless of
whether the calling container is trusted.
"""
import json
import logging
import os
import socket
import subprocess

LOG_PATH = os.environ.get("CONTROLPANEL_HELPER_LOG", "/var/log/controlpanel-helper.log")
SOCKET_PATH = os.environ.get("CONTROLPANEL_HELPER_SOCKET", "/run/controlpanel-helper.sock")
RECV_CHUNK = 4096
MAX_REQUEST_BYTES = 4096  # a valid {"action": "..."} request is tiny; refuse anything larger outright

logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(message)s")

# Fixed, closed verb table - the entire security boundary lives here.
# Never add a verb that accepts caller-supplied arguments into the
# command line, never set shell=True, never string-interpolate anything
# from the request into a command. A new verb means a new hardcoded
# entry here, reviewed with the same scrutiny as these three. This host
# runs CachyOS (Arch-based, pacman) - NOT apt, despite the original
# design doc's illustrative examples using apt_update/apt_upgrade.
VERBS = {
    "reboot": (["systemctl", "reboot"], 60),
    # -Sy only refreshes the package database (list-only, no package
    # changes) - the pacman equivalent of "apt update", safe to run
    # unattended/on a schedule later if that's ever wanted.
    "pacman_sync": (["pacman", "-Sy", "--noconfirm"], 120),
    # -Syu performs a real full system upgrade - --noconfirm is required
    # here (not a shortcut) because this runs with no attached TTY; pacman
    # would otherwise hang forever on its own y/n prompt. 30 minutes
    # covers a large kernel/driver upgrade without hanging the caller
    # indefinitely on a stuck mirror.
    "pacman_upgrade": (["pacman", "-Syu", "--noconfirm"], 1800),
}


def _run_verb(action: str) -> dict:
    entry = VERBS.get(action)
    if entry is None:
        return {"ok": False, "message": f"Unknown action '{action}' - not in the fixed verb set.", "returncode": None}
    argv, timeout = entry
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": f"{action} timed out after {timeout}s.", "returncode": None}
    except OSError as e:
        return {"ok": False, "message": f"{action} failed to start: {e}", "returncode": None}
    ok = result.returncode == 0
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    message = output[-4000:] if output else ("succeeded" if ok else "failed with no output")
    return {"ok": ok, "message": message, "returncode": result.returncode}


def handle_request(raw: str) -> tuple[dict, str | None]:
    """Returns (response, action) - action is None when the request
    couldn't even be parsed far enough to log which verb was attempted."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "message": "Malformed JSON request.", "returncode": None}, None
    if not isinstance(payload, dict):
        return {"ok": False, "message": "Request must be a JSON object.", "returncode": None}, None
    action = payload.get("action")
    if not isinstance(action, str):
        return {"ok": False, "message": "Request must include a string 'action'.", "returncode": None}, None
    return _run_verb(action), action


def _listen_socket() -> socket.socket:
    """Prefers systemd socket activation (LISTEN_FDS=1, fd 3 already
    bound+listening by helper.socket) so the daemon isn't a standing
    process - only spins up per request. Falls back to binding
    SOCKET_PATH directly, for manual/local runs outside systemd (e.g.
    `python3 helper.py` during development)."""
    if os.environ.get("LISTEN_FDS") == "1" and os.environ.get("LISTEN_PID") == str(os.getpid()):
        return socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, fileno=3)
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o660)
    sock.listen(5)
    return sock


def _recv_request(conn: socket.socket) -> str:
    data = b""
    while not data.endswith(b"\n"):
        chunk = conn.recv(RECV_CHUNK)
        if not chunk:
            break
        data += chunk
        if len(data) > MAX_REQUEST_BYTES:
            raise ValueError("request too large")
    return data.decode("utf-8", errors="replace").strip()


def serve_one(conn: socket.socket) -> None:
    try:
        try:
            raw = _recv_request(conn)
        except ValueError as e:
            response, action = {"ok": False, "message": str(e), "returncode": None}, None
        else:
            response, action = handle_request(raw) if raw else ({"ok": False, "message": "Empty request.", "returncode": None}, None)
        logging.info(json.dumps({"action": action, "ok": response["ok"], "returncode": response["returncode"]}))
        conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
    finally:
        conn.close()


def serve(sock: socket.socket) -> None:
    while True:
        conn, _ = sock.accept()
        serve_one(conn)


def main() -> None:
    sock = _listen_socket()
    try:
        serve(sock)
    finally:
        sock.close()


if __name__ == "__main__":
    main()

"""Thin client for the host-privileged-action helper daemon (Option B of
.claude/plans/host-privileged-helper.plan.md, scripts/host-helper/helper.py).
Sends one JSON request over a Unix domain socket, reads one JSON
response, closes - never talks to the host any other way (no nsenter,
no D-Bus). This socket is the only privileged-beyond-docker.sock surface
this container has, and it's optional: the socket is only bind-mounted
once Bear has installed the host-side daemon (see the README in that
directory), so every route using this client must degrade to a clear
error rather than assume the socket exists.
"""
import json
import os
import socket

from core.responses import fail

HOST_HELPER_SOCKET = os.environ.get("HOST_HELPER_SOCKET", "/host-helper.sock")
DEFAULT_TIMEOUT = 600


def call_host_helper(action: str, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Raises a fail()-shaped HTTPException on any transport failure -
    socket not present (helper not installed on this host), connection
    refused, timeout, or a malformed response. On success, returns the
    daemon's own {"ok", "message", "returncode"} dict unchanged - the
    caller checks `ok` itself, since a verb can fail (e.g. pacman exiting
    non-zero) without this function raising."""
    if not os.path.exists(HOST_HELPER_SOCKET):
        fail("Host helper isn't installed on this host - see scripts/host-helper/README.md.", status_code=503)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(HOST_HELPER_SOCKET)
        sock.sendall((json.dumps({"action": action}) + "\n").encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
    except OSError as e:
        fail(f"Host helper request failed: {e}", status_code=502)
    finally:
        sock.close()
    try:
        return json.loads(data.decode("utf-8"))
    except json.JSONDecodeError:
        fail("Host helper returned a malformed response.", status_code=502)

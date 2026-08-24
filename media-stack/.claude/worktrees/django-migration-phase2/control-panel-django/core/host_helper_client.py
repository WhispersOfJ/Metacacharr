"""Thin client for the host-privileged-action helper daemon
(scripts/host-helper/helper.py), ported near-verbatim from the FastAPI-era
control-panel/core/host_helper_client.py. Sends one JSON request over a
Unix domain socket, reads one JSON response, closes - never talks to the
host any other way (no nsenter, no D-Bus). This socket is the only
privileged-beyond-docker.sock surface this container has, and it's
optional: the socket is only bind-mounted once the host-side daemon is
installed, so every route using this client must degrade to a clear error
rather than assume the socket exists.

Only transform applied vs. the FastAPI-era source: core.responses.fail()
(which raised a fastapi.HTTPException) is replaced with
core.api_base.ServiceError. Every constant/function name and signature is
otherwise byte-identical.
"""
import json
import os
import socket

from core.api_base import ServiceError

HOST_HELPER_SOCKET = os.environ.get("HOST_HELPER_SOCKET", "/host-helper.sock")
DEFAULT_TIMEOUT = 600


def call_host_helper(action: str, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Raises a ServiceError on any transport failure - socket not present
    (helper not installed on this host), connection refused, timeout, or a
    malformed response. On success, returns the daemon's own {"ok",
    "message", "returncode"} dict unchanged - the caller checks `ok`
    itself, since a verb can fail (e.g. pacman exiting non-zero) without
    this function raising."""
    if not os.path.exists(HOST_HELPER_SOCKET):
        raise ServiceError("Host helper isn't installed on this host - see scripts/host-helper/README.md.", status=503)
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
        raise ServiceError(f"Host helper request failed: {e}", status=502)
    finally:
        sock.close()
    try:
        return json.loads(data.decode("utf-8"))
    except json.JSONDecodeError:
        raise ServiceError("Host helper returned a malformed response.", status=502)

"""Host-privileged actions (reboot, pacman sync/upgrade), ported from
control-panel/services/host_actions/router.py. Each function proxies to a
single action string on the host-helper daemon and returns its raw
{"ok", "message", "returncode"} dict unchanged - the view layer checks
`ok` itself, since a verb can fail (e.g. pacman exiting non-zero) without
call_host_helper raising.

Action strings match the FastAPI-era router exactly: "reboot",
"pacman_sync", "pacman_upgrade" (underscore) - NOT the hyphenated
"pacman-sync"/"pacman-upgrade" used for the URL paths.
"""
from core.host_helper_client import call_host_helper


def reboot() -> dict:
    return call_host_helper("reboot")


def pacman_sync() -> dict:
    return call_host_helper("pacman_sync")


def pacman_upgrade() -> dict:
    return call_host_helper("pacman_upgrade")

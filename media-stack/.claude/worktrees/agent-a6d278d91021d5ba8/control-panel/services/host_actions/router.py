"""Host-privileged-action routes - reboot, pacman sync, pacman upgrade -
brokered through the host-side controlpanel-helper daemon (see
core/host_helper_client.py and
.claude/plans/host-privileged-helper.plan.md). Every route here is
session-only (current_user, never current_user_or_service) - these are
irreversible/disruptive host-level actions, never automation-invoked -
and requires confirm=true in the body, the same double-gate as
/api/disk-health/prune and the catalog install/remove routes.
"""
from core.host_helper_client import call_host_helper
from core.responses import fail, ok
from core.security import current_user
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(tags=["host-actions"])

SERVICE_META = {"label": "Host Actions", "health_check": None}


class HostActionRequest(BaseModel):
    confirm: bool = False


def _run_host_action(action: str, label: str, payload: HostActionRequest) -> dict:
    if not payload.confirm:
        fail(f"Set confirm=true to {label.lower()} - this is a real host-level action.", status_code=400)
    result = call_host_helper(action)
    if not result.get("ok"):
        fail(f"{label} failed: {result.get('message', 'unknown error')}", status_code=502)
    return ok(f"{label} succeeded.", output=result.get("message"))


@router.post("/api/host/reboot")
def host_reboot(payload: HostActionRequest, _=Depends(current_user)):
    """Reboots the physical host this entire stack runs on - every
    container, including this panel, goes down and back up. The daemon
    call itself returns before the reboot actually completes (systemctl
    reboot schedules it asynchronously), so this request finishes
    successfully even though the box is about to disappear."""
    return _run_host_action("reboot", "Reboot", payload)


@router.post("/api/host/pacman-sync")
def host_pacman_sync(payload: HostActionRequest, _=Depends(current_user)):
    """Refreshes the host's pacman package database only - no packages
    are installed or changed."""
    return _run_host_action("pacman_sync", "Package database sync", payload)


@router.post("/api/host/pacman-upgrade")
def host_pacman_upgrade(payload: HostActionRequest, _=Depends(current_user)):
    """Runs a full host system upgrade (`pacman -Syu`) - can take a
    while and may itself require a reboot afterward for kernel/driver
    updates to take effect."""
    return _run_host_action("pacman_upgrade", "Package upgrade", payload)

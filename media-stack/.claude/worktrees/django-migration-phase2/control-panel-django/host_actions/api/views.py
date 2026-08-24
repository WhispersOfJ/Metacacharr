"""Host-privileged-action routes - reboot, pacman sync, pacman upgrade -
brokered through the host-side controlpanel-helper daemon (see
core/host_helper_client.py). Ported from
control-panel/services/host_actions/router.py.

Every view here is session-only (IsAuthenticatedSessionOnly, never
IsAuthenticatedOrServiceKey) - these are irreversible/disruptive
host-level actions, never automation-invoked - and requires confirm=true
in the body, the same double-gate as the FastAPI-era
/api/disk-health/prune and catalog install/remove routes. The confirm
check happens in post() BEFORE the action function is called, matching
router.py's _run_host_action() checking payload.confirm before calling
call_host_helper()."""
from core.api_base import EnvelopeAPIView, ServiceError
from core.permissions import IsAuthenticatedSessionOnly
from host_actions import services
from host_actions.api.serializers import ConfirmRequestSerializer


class _ConfirmedActionView(EnvelopeAPIView):
    permission_classes = [IsAuthenticatedSessionOnly]
    label = None

    def call_action(self) -> dict:
        raise NotImplementedError

    def post(self, request):
        body = ConfirmRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if not body.validated_data["confirm"]:
            raise ServiceError(
                f"Set confirm=true to {self.label.lower()} - this is a real host-level action.",
                status=400,
            )
        result = self.call_action()
        if not result.get("ok"):
            raise ServiceError(f"{self.label} failed: {result.get('message', 'unknown error')}", status=502)
        return self.ok(f"{self.label} succeeded.", output=result.get("message"))


class RebootView(_ConfirmedActionView):
    """Reboots the physical host this entire stack runs on - every
    container, including this panel, goes down and back up. The daemon
    call itself returns before the reboot actually completes (systemctl
    reboot schedules it asynchronously), so this request finishes
    successfully even though the box is about to disappear."""

    label = "Reboot"

    def call_action(self) -> dict:
        return services.reboot()


class PacmanSyncView(_ConfirmedActionView):
    """Refreshes the host's pacman package database only - no packages
    are installed or changed."""

    label = "Package database sync"

    def call_action(self) -> dict:
        return services.pacman_sync()


class PacmanUpgradeView(_ConfirmedActionView):
    """Runs a full host system upgrade (`pacman -Syu`) - can take a
    while and may itself require a reboot afterward for kernel/driver
    updates to take effect."""

    label = "Package upgrade"

    def call_action(self) -> dict:
        return services.pacman_upgrade()

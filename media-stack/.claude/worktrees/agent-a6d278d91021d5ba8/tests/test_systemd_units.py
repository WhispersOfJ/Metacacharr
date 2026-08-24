"""Gate tests for systemd/ + Dockerfile + entrypoint.sh - the deploy layer.

No LLM judgment needed here: these are cross-references (does ExecStart point
at a real file, does every OnFailure= target a template that exists, is every
.timer paired with a .service) that a script can check deterministically and
that silently break a scheduled job if they drift.
"""
import re
import stat
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SYSTEMD_DIR = REPO_ROOT / "systemd"

SERVICE_FILES = sorted(SYSTEMD_DIR.glob("*.service"))
TIMER_FILES = sorted(SYSTEMD_DIR.glob("*.timer"))

# Daemons (Type=simple, never scheduled) and boot-time units (WantedBy=
# default.target, not timers.target) are legitimately timer-less.
TIMERLESS_SERVICES = {
    "media-stack.service",
    "notify-failure@.service",
    "stack-plex-health-monitor.service",
    "stack-plex-webhook.service",
}


def _directives(path: Path, key: str) -> list[str]:
    """All values for a repeated directive (e.g. every ExecStart= line) -
    systemd unit files legally repeat keys like ExecStart=, unlike strict INI."""
    prefix = f"{key}="
    return [
        line.split("=", 1)[1].strip()
        for line in path.read_text().splitlines()
        if line.strip().startswith(prefix)
    ]


def test_every_timer_has_a_matching_service():
    for timer in TIMER_FILES:
        service = timer.with_suffix(".service")
        assert service.exists(), f"{timer.name} has no matching {service.name}"


def test_every_non_daemon_service_has_a_timer_or_is_reactive():
    for service in SERVICE_FILES:
        if service.name in TIMERLESS_SERVICES:
            continue
        timer = service.with_suffix(".timer")
        assert timer.exists(), f"{service.name} has no matching .timer and isn't in TIMERLESS_SERVICES"


def test_execstart_script_paths_exist_and_are_executable():
    for service in SERVICE_FILES:
        for line in _directives(service, "ExecStart") + _directives(service, "ExecStartPre"):
            target = line.split()[0] if not line.startswith('"') else None
            if target is None or not target.startswith(str(REPO_ROOT)):
                continue
            path = Path(target)
            assert path.exists(), f"{service.name}: ExecStart target missing: {target}"
            assert path.stat().st_mode & stat.S_IXUSR, f"{service.name}: ExecStart target not executable: {target}"


def test_onfailure_targets_resolve_to_notify_failure_template():
    template = SYSTEMD_DIR / "notify-failure@.service"
    assert template.exists()
    for service in SERVICE_FILES:
        for line in _directives(service, "OnFailure"):
            assert re.match(r"^notify-failure@%n\.service$", line), (
                f"{service.name}: unexpected OnFailure target {line!r}"
            )


def test_no_service_references_a_nonexistent_compose_profile():
    """Regression guard: media-stack.service used to say `--profile extras`,
    a profile that was never defined in docker-compose.yml (compose profiles
    are additive, so this silently ran as if no profile were given at all -
    harmless today, but a landmine if a real profile is ever added)."""
    for service in SERVICE_FILES:
        text = service.read_text()
        assert "--profile extras" not in text, f"{service.name} references the removed 'extras' profile"


def test_no_stale_service_reference_in_unit_descriptions():
    removed = ("bazarr", "kometa", "ntfy", "organizr", "scrutiny", "speedtest-tracker", "byparr")
    for service in SERVICE_FILES:
        lowered = service.read_text().lower()
        for name in removed:
            assert name not in lowered, f"{service.name} references removed service {name!r}"


def test_dockerfile_copy_sources_exist():
    dockerfile = REPO_ROOT / "Dockerfile"
    copy_re = re.compile(r"^COPY\s+(.+?)\s+\S+$")
    for line in dockerfile.read_text().splitlines():
        m = copy_re.match(line.strip())
        if not m:
            continue
        for src in m.group(1).split():
            assert (REPO_ROOT / src).exists(), f"Dockerfile COPY source missing: {src}"


def test_entrypoint_does_not_reference_removed_compose_profile():
    entrypoint = REPO_ROOT / "entrypoint.sh"
    text = entrypoint.read_text()
    assert "--profile extras" not in text


def test_entrypoint_is_executable():
    entrypoint = REPO_ROOT / "entrypoint.sh"
    assert entrypoint.stat().st_mode & stat.S_IXUSR

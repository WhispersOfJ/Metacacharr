"""Gate tests for the nzbdav_rclone stale-mount self-heal.

Background (2026-08-13 incident): nzbdav_rclone declares
`depends_on: nzbdav / restart: true`, so every nzbdav restart also restarts
rclone. rclone is SIGKILLed without unmounting, which leaves a dead FUSE
mount on the host. On the next start rclone refuses to remount ("directory
already mounted") and crash-loops indefinitely, leaving every dependent
(plex, radarr, sonarr, bazarr, cleanuparr) holding a defunct handle. Plex's
scheduled scan then stat-failed on every file and flagged 19,024 library
items as deleted.

The fix is a pre-mount unmount in the container command. These tests pin the
three properties that make that fix actually work, each of which was gotten
wrong at least once while writing it.
"""
import subprocess

import pytest
import yaml

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"

MOUNTPOINT = "/mnt/remote/nzbdav"


@pytest.fixture(scope="module")
def rclone_service():
    """The nzbdav_rclone service as docker compose actually renders it.

    Parsing docker-compose.yml directly would not catch the word-splitting
    bug this suite exists to prevent - compose's own interpolation is what
    turns a bare `command: >` string into separate argv entries.
    """
    proc = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "config"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        pytest.skip(f"docker compose config unavailable: {proc.stderr[:200]}")
    return yaml.safe_load(proc.stdout)["services"]["nzbdav_rclone"]


def test_entrypoint_is_a_shell(rclone_service):
    # Arrange / Act
    entrypoint = rclone_service.get("entrypoint")

    # Assert - the image's default entrypoint is `rclone`, which cannot run
    # the pre-mount cleanup. It must be overridden to a shell.
    assert entrypoint == ["/bin/sh", "-c"]


def test_command_is_a_single_shell_argument(rclone_service):
    """`sh -c` takes ONE argument. Compose word-splits string commands."""
    # Arrange / Act
    command = rclone_service.get("command")

    # Assert
    assert isinstance(command, list)
    assert len(command) == 1, (
        "command word-split into separate argv entries; `sh -c` would receive "
        f"only {command[0]!r} and the mount would never run"
    )


def test_command_unmounts_before_mounting(rclone_service):
    # Arrange
    script = rclone_service["command"][0]

    # Act
    unmount_at = script.find(f"fusermount3 -uz {MOUNTPOINT}")
    fallback_at = script.find(f"umount -l {MOUNTPOINT}")
    mount_at = script.find(f"mount nzbdav: {MOUNTPOINT}")

    # Assert - both unmount attempts must precede the mount, or the stale
    # mountpoint is still present when rclone runs its already-mounted check.
    assert unmount_at != -1, "missing fusermount3 pre-mount cleanup"
    assert fallback_at != -1, "missing umount -l fallback cleanup"
    assert mount_at != -1, "rclone mount command disappeared"
    assert unmount_at < mount_at
    assert fallback_at < mount_at


def test_cleanup_failure_does_not_abort_the_mount(rclone_service):
    """On a clean start there is nothing to unmount; that must not be fatal."""
    # Arrange
    script = rclone_service["command"][0]
    mount_at = script.find("exec rclone")

    # Act
    prelude = script[:mount_at]

    # Assert - every cleanup statement swallows its own failure.
    cleanup_statements = [s.strip() for s in prelude.split(";") if s.strip()]
    assert cleanup_statements, "no pre-mount statements found"
    for statement in cleanup_statements:
        assert statement.endswith("|| true"), (
            f"{statement!r} can abort the container before rclone mounts"
        )


def test_rclone_runs_as_pid_one(rclone_service):
    """Without `exec`, the shell stays PID 1 and rclone never sees SIGTERM.

    That would make every stop a SIGKILL, which is the exact condition that
    leaves the stale mount behind in the first place.
    """
    # Arrange / Act
    script = rclone_service["command"][0]

    # Assert
    assert "exec rclone" in script


def test_mount_dependents_still_bind_the_mount_parent(rclone_service):
    """rclone must bind /mnt/remote (the parent), never the FUSE target.

    Binding the target itself makes rclone's own already-mounted check
    misfire on every start - the path looks like a mount boundary from
    inside the container before rclone touches it.
    """
    # Arrange / Act
    volumes = rclone_service.get("volumes", [])
    remote_binds = [
        v for v in volumes if v.get("target", "").startswith("/mnt/remote")
    ]

    # Assert
    assert remote_binds, "rclone no longer binds /mnt/remote"
    targets = {v["target"] for v in remote_binds}
    assert MOUNTPOINT not in targets, (
        "rclone binds the FUSE target directly; its already-mounted check "
        "will misfire on every start"
    )
    assert "/mnt/remote" in targets

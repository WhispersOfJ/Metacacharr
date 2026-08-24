from unittest.mock import patch

from host_actions import services


def test_reboot_calls_call_host_helper_with_reboot_action():
    """reboot() proxies to call_host_helper('reboot') and returns its dict verbatim."""
    with patch(
        "host_actions.services.call_host_helper",
        return_value={"ok": True, "message": "Rebooting", "returncode": 0},
    ) as mock_call:
        result = services.reboot()

    mock_call.assert_called_once_with("reboot")
    assert result == {"ok": True, "message": "Rebooting", "returncode": 0}


def test_pacman_sync_calls_call_host_helper_with_pacman_sync_action():
    """pacman_sync() proxies to call_host_helper('pacman_sync') (underscore, matches
    upstream router.py, NOT the hyphenated 'pacman-sync' used for the URL path)."""
    with patch(
        "host_actions.services.call_host_helper",
        return_value={"ok": True, "message": "Synced", "returncode": 0},
    ) as mock_call:
        result = services.pacman_sync()

    mock_call.assert_called_once_with("pacman_sync")
    assert result == {"ok": True, "message": "Synced", "returncode": 0}


def test_pacman_upgrade_calls_call_host_helper_with_pacman_upgrade_action():
    """pacman_upgrade() proxies to call_host_helper('pacman_upgrade') (underscore)."""
    with patch(
        "host_actions.services.call_host_helper",
        return_value={"ok": True, "message": "Upgraded", "returncode": 0},
    ) as mock_call:
        result = services.pacman_upgrade()

    mock_call.assert_called_once_with("pacman_upgrade")
    assert result == {"ok": True, "message": "Upgraded", "returncode": 0}

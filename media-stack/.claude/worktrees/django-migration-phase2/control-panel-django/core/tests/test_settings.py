import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _run_settings_import(env_overrides):
    """Import config.settings in a fresh subprocess so module-level state
    (SECRET_KEY / DEBUG) is evaluated from scratch against the given env,
    without disturbing the settings already loaded for the rest of the
    test suite."""
    env = os.environ.copy()
    env.pop("CONTROL_PANEL_SECRET_KEY", None)
    env.pop("CONTROL_PANEL_DEBUG", None)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=str(BASE_DIR),
        env=env,
        capture_output=True,
        text=True,
    )


def test_missing_secret_key_raises_when_debug_off():
    result = _run_settings_import({})
    assert result.returncode != 0
    assert "CONTROL_PANEL_SECRET_KEY must be set" in result.stderr


def test_missing_secret_key_allowed_when_debug_on():
    result = _run_settings_import({"CONTROL_PANEL_DEBUG": "1"})
    assert result.returncode == 0


def test_secret_key_present_is_fine_with_debug_off():
    result = _run_settings_import({"CONTROL_PANEL_SECRET_KEY": "some-real-secret"})
    assert result.returncode == 0

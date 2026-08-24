import json
import urllib.error
from unittest.mock import MagicMock, patch


def test_main_posts_to_sync_tick_with_service_key(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("CONTROL_PANEL_SERVICE_API_KEY=raw-test-key\nOTHER_VAR=ignored\n")
    monkeypatch.setenv("LETTERBOXD_SYNC_ENV_FILE", str(env_file))

    import importlib.util
    from pathlib import Path

    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "letterboxd-sync.py"
    spec = importlib.util.spec_from_file_location("letterboxd_sync_script", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps({"ok": True, "message": "Synced 2 tracked list(s).",
                                                    "results": [{"url": "a", "added": ["x"], "failed": []}]}).encode()
    fake_response.__enter__ = lambda self: fake_response
    fake_response.__exit__ = lambda self, *a: None

    captured_request = {}

    def fake_urlopen(req, timeout=None):
        captured_request["headers"] = dict(req.header_items())
        captured_request["url"] = req.full_url
        return fake_response

    with patch("urllib.request.urlopen", fake_urlopen):
        exit_code = module.main()

    assert exit_code == 0
    assert captured_request["headers"]["X-api-key"] == "raw-test-key"
    assert captured_request["url"] == "http://localhost:8420/api/arr/letterboxd/sync-tick"


def test_main_returns_1_on_unreachable_control_panel(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("CONTROL_PANEL_SERVICE_API_KEY=raw-test-key\n")
    monkeypatch.setenv("LETTERBOXD_SYNC_ENV_FILE", str(env_file))

    import importlib.util
    from pathlib import Path

    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "letterboxd-sync.py"
    spec = importlib.util.spec_from_file_location("letterboxd_sync_script", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    with patch("urllib.request.urlopen", fake_urlopen):
        exit_code = module.main()

    assert exit_code == 1


def test_main_returns_1_when_no_service_key_found(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SOME_OTHER_KEY=value\n")
    monkeypatch.setenv("LETTERBOXD_SYNC_ENV_FILE", str(env_file))

    import importlib.util
    from pathlib import Path

    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "letterboxd-sync.py"
    spec = importlib.util.spec_from_file_location("letterboxd_sync_script", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.main() == 1

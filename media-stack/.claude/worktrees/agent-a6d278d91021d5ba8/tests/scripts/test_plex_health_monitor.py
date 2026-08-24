import json
import urllib.error
from io import BytesIO


def test_scan_progress_finds_library_update_activity(plex_health_monitor):
    data = {"activities": [
        {"type": "media.generate", "progress": 5},
        {"type": "library.update.section", "progress": 42},
    ]}
    assert plex_health_monitor.scan_progress(data) == 42


def test_scan_progress_no_matching_activity(plex_health_monitor):
    data = {"activities": [{"type": "media.generate", "progress": 5}]}
    assert plex_health_monitor.scan_progress(data) is None


def test_scan_progress_no_activities_key(plex_health_monitor):
    assert plex_health_monitor.scan_progress({}) is None


def test_classify_dstate_threads_is_hard_hang(plex_health_monitor):
    data = {"dstate_threads": ["12345"], "mount_ok": True}
    assert plex_health_monitor.classify(data) == "hard_hang"


def test_classify_mount_not_ok_is_hard_hang(plex_health_monitor):
    data = {"dstate_threads": [], "mount_ok": False}
    assert plex_health_monitor.classify(data) == "hard_hang"


def test_classify_hard_hang_takes_priority_over_busy_db(plex_health_monitor):
    data = {"dstate_threads": ["1"], "mount_ok": False, "recent_busy_db_errors": 5}
    assert plex_health_monitor.classify(data) == "hard_hang"


def test_classify_busy_db_errors(plex_health_monitor):
    data = {"mount_ok": True, "recent_busy_db_errors": 3}
    assert plex_health_monitor.classify(data) == "busy_db"


def test_classify_analysis_active_suppresses_scan_lag(plex_health_monitor):
    data = {
        "mount_ok": True, "recent_busy_db_errors": 0, "analysis_active": True,
        "activities": [{"type": "library.update.section", "progress": 10}],
        "state": "scanning",
    }
    assert plex_health_monitor.classify(data) is None


def test_classify_scan_progress_present_is_scan_lag(plex_health_monitor):
    data = {
        "mount_ok": True, "recent_busy_db_errors": 0, "analysis_active": False,
        "activities": [{"type": "library.update.section", "progress": 10}],
    }
    assert plex_health_monitor.classify(data) == "scan_lag"


def test_classify_stalled_suspected_state_is_scan_lag(plex_health_monitor):
    data = {"mount_ok": True, "recent_busy_db_errors": 0, "state": "stalled_suspected"}
    assert plex_health_monitor.classify(data) == "scan_lag"


def test_classify_healthy_idle(plex_health_monitor):
    data = {"mount_ok": True, "recent_busy_db_errors": 0, "state": "idle"}
    assert plex_health_monitor.classify(data) is None


def test_env_get_missing_file(plex_health_monitor, tmp_path, monkeypatch):
    monkeypatch.setattr(plex_health_monitor, "STACK_DIR", tmp_path)
    assert plex_health_monitor.env_get("SOME_KEY") is None


def test_env_get_missing_key(plex_health_monitor, tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OTHER_KEY=value\n")
    monkeypatch.setattr(plex_health_monitor, "STACK_DIR", tmp_path)
    assert plex_health_monitor.env_get("SOME_KEY") is None


def test_env_get_found_key(plex_health_monitor, tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("FOO=bar\nSOME_KEY=  spaced  \n")
    monkeypatch.setattr(plex_health_monitor, "STACK_DIR", tmp_path)
    assert plex_health_monitor.env_get("SOME_KEY") == "spaced"


def test_notify_discord_unconfigured_prints_only(plex_health_monitor, monkeypatch, capsys):
    monkeypatch.setattr(plex_health_monitor, "DISCORD_WEBHOOK_URL", None)

    def _boom(*a, **k):
        raise AssertionError("urlopen should not be called when webhook unconfigured")

    monkeypatch.setattr(plex_health_monitor.urllib.request, "urlopen", _boom)
    plex_health_monitor.notify_discord("test message", "warn")
    assert "test message" in capsys.readouterr().out


def test_notify_discord_changeme_placeholder_prints_only(plex_health_monitor, monkeypatch, capsys):
    monkeypatch.setattr(plex_health_monitor, "DISCORD_WEBHOOK_URL", "changeme")

    def _boom(*a, **k):
        raise AssertionError("urlopen should not be called for the changeme placeholder")

    monkeypatch.setattr(plex_health_monitor.urllib.request, "urlopen", _boom)
    plex_health_monitor.notify_discord("test message", "error")
    assert "test message" in capsys.readouterr().out


def test_notify_discord_posts_with_user_agent(plex_health_monitor, monkeypatch):
    monkeypatch.setattr(plex_health_monitor, "DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    captured = {}

    class _Resp:
        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, timeout=None):
        captured["headers"] = req.headers
        captured["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr(plex_health_monitor.urllib.request, "urlopen", _urlopen)
    plex_health_monitor.notify_discord("hello", "info")
    assert captured["url"] == "https://discord.example/webhook"
    assert "user-agent" in {k.lower() for k in captured["headers"]}


def test_notify_discord_swallows_url_error(plex_health_monitor, monkeypatch, capsys):
    monkeypatch.setattr(plex_health_monitor, "DISCORD_WEBHOOK_URL", "https://discord.example/webhook")

    def _raise(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(plex_health_monitor.urllib.request, "urlopen", _raise)
    plex_health_monitor.notify_discord("hello", "error")
    assert "notify_discord failed" in capsys.readouterr().err


def test_api_get_parses_json_response(plex_health_monitor, monkeypatch):
    class _Resp(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, timeout=None):
        assert req.full_url == "http://localhost:8420/api/plex/scan-health"
        return _Resp(json.dumps({"state": "idle"}).encode())

    monkeypatch.setattr(plex_health_monitor.urllib.request, "urlopen", _urlopen)
    assert plex_health_monitor.api_get("/api/plex/scan-health") == {"state": "idle"}


def test_api_post_success_returns_message(plex_health_monitor, monkeypatch):
    class _Resp(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, timeout=None):
        return _Resp(json.dumps({"message": "restarted"}).encode())

    monkeypatch.setattr(plex_health_monitor.urllib.request, "urlopen", _urlopen)
    ok, message = plex_health_monitor.api_post("/api/container/plex/restart")
    assert ok is True
    assert message == "restarted"


def test_api_post_http_error_returns_detail_message(plex_health_monitor, monkeypatch):
    def _raise(req, timeout=None):
        raise urllib.error.HTTPError(
            "url", 409, "conflict", {}, BytesIO(json.dumps({"detail": {"message": "cooldown active"}}).encode())
        )

    monkeypatch.setattr(plex_health_monitor.urllib.request, "urlopen", _raise)
    ok, message = plex_health_monitor.api_post("/api/container/plex/restart")
    assert ok is False
    assert message == "cooldown active"


def test_api_post_network_failure(plex_health_monitor, monkeypatch):
    def _raise(req, timeout=None):
        raise urllib.error.URLError("unreachable")

    monkeypatch.setattr(plex_health_monitor.urllib.request, "urlopen", _raise)
    ok, message = plex_health_monitor.api_post("/api/container/plex/restart")
    assert ok is False
    assert "unreachable" in message


# --- Service-key auth (regression, 2026-08-14) -------------------------------
# Every control-panel route this script calls sits behind
# current_user_or_service. The script sent only a User-Agent, so every poll
# 401'd and the watchdog's own retry logic reported the control panel as
# unreachable instead of watching Plex. These pin the header onto both verbs.

def test_api_headers_include_service_key(plex_health_monitor, monkeypatch):
    monkeypatch.setattr(plex_health_monitor, "SERVICE_API_KEY", "secret-key")
    assert plex_health_monitor.api_headers()["X-Api-Key"] == "secret-key"


def test_api_headers_omit_key_when_unset(plex_health_monitor, monkeypatch):
    monkeypatch.setattr(plex_health_monitor, "SERVICE_API_KEY", None)
    assert "X-Api-Key" not in plex_health_monitor.api_headers()


def test_api_get_sends_service_key(plex_health_monitor, monkeypatch):
    monkeypatch.setattr(plex_health_monitor, "SERVICE_API_KEY", "secret-key")
    seen = {}

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, timeout=None):
        seen["key"] = req.get_header("X-api-key")
        return _Resp(json.dumps({"mount_ok": True}).encode())

    monkeypatch.setattr(plex_health_monitor.urllib.request, "urlopen", _urlopen)
    plex_health_monitor.api_get("/api/plex/scan-health")
    assert seen["key"] == "secret-key"


def test_api_post_sends_service_key(plex_health_monitor, monkeypatch):
    monkeypatch.setattr(plex_health_monitor, "SERVICE_API_KEY", "secret-key")
    seen = {}

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, timeout=None):
        seen["key"] = req.get_header("X-api-key")
        return _Resp(json.dumps({"message": "restarted"}).encode())

    monkeypatch.setattr(plex_health_monitor.urllib.request, "urlopen", _urlopen)
    ok, _ = plex_health_monitor.api_post("/api/container/plex/restart")
    assert ok is True
    assert seen["key"] == "secret-key"

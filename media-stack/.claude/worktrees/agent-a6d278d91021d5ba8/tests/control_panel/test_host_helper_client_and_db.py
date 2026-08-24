"""Gate tests for core/host_helper_client.py (Unix-socket privileged-action
client) and core/db.py (SQLAlchemy engine/session). First-ever coverage for
either module - tests/scripts/test_host_helper.py covers the daemon side
(scripts/host-helper/helper.py), not this client."""
import pytest


@pytest.fixture
def host_helper_module(cp_main_app):
    import core.host_helper_client as module
    return module


def test_call_host_helper_socket_missing_fails_503(host_helper_module, monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(host_helper_module.os.path, "exists", lambda p: False)
    with pytest.raises(HTTPException) as exc:
        host_helper_module.call_host_helper("some-action")
    assert exc.value.status_code == 503


def test_call_host_helper_connection_refused_fails_502(host_helper_module, monkeypatch):
    from fastapi import HTTPException
    import socket as socket_mod

    class FakeSocket:
        def __init__(self, *a, **k):
            pass

        def settimeout(self, t):
            pass

        def connect(self, addr):
            raise ConnectionRefusedError("refused")

        def close(self):
            pass

    monkeypatch.setattr(host_helper_module.os.path, "exists", lambda p: True)
    monkeypatch.setattr(socket_mod, "socket", FakeSocket)
    with pytest.raises(HTTPException) as exc:
        host_helper_module.call_host_helper("some-action")
    assert exc.value.status_code == 502


def test_call_host_helper_malformed_response_fails_502(host_helper_module, monkeypatch):
    from fastapi import HTTPException
    import socket as socket_mod

    class FakeSocket:
        def __init__(self, *a, **k):
            self._sent = False

        def settimeout(self, t):
            pass

        def connect(self, addr):
            pass

        def sendall(self, data):
            pass

        def shutdown(self, how):
            pass

        def recv(self, n):
            if not self._sent:
                self._sent = True
                return b"not-json"
            return b""

        def close(self):
            pass

    monkeypatch.setattr(host_helper_module.os.path, "exists", lambda p: True)
    monkeypatch.setattr(socket_mod, "socket", FakeSocket)
    with pytest.raises(HTTPException) as exc:
        host_helper_module.call_host_helper("some-action")
    assert exc.value.status_code == 502


def test_call_host_helper_success_returns_parsed_json(host_helper_module, monkeypatch):
    import socket as socket_mod
    import json

    class FakeSocket:
        def __init__(self, *a, **k):
            self._sent = False

        def settimeout(self, t):
            pass

        def connect(self, addr):
            pass

        def sendall(self, data):
            pass

        def shutdown(self, how):
            pass

        def recv(self, n):
            if not self._sent:
                self._sent = True
                return json.dumps({"ok": True, "message": "done", "returncode": 0}).encode()
            return b""

        def close(self):
            pass

    monkeypatch.setattr(host_helper_module.os.path, "exists", lambda p: True)
    monkeypatch.setattr(socket_mod, "socket", FakeSocket)
    result = host_helper_module.call_host_helper("some-action")
    assert result == {"ok": True, "message": "done", "returncode": 0}


def test_db_get_db_yields_and_closes_session(cp_main_app):
    import core.db as db_module
    gen = db_module.get_db()
    session = next(gen)
    assert session is not None
    with pytest.raises(StopIteration):
        next(gen)


def test_db_url_uses_env_override(monkeypatch, tmp_path):
    import importlib
    import sys
    custom_path = str(tmp_path / "custom.db")
    monkeypatch.setenv("CONTROL_PANEL_DB_PATH", custom_path)
    sys.modules.pop("core.db", None)
    import core.db as db_module
    importlib.reload(db_module)
    assert custom_path in db_module.DATABASE_URL

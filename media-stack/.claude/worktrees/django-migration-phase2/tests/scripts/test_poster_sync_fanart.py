import json
import urllib.error
import urllib.request
from io import BytesIO


class _CtxResp:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


class _StreamResp:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self._lines)


def _post_ok(message="sync started"):
    return _CtxResp(json.dumps({"message": message}).encode())


def test_main_requires_library_argument(poster_sync_fanart, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["poster-sync-fanart.py"])
    assert poster_sync_fanart.main() == 1
    assert "usage:" in capsys.readouterr().err


def test_main_success_stream_done(poster_sync_fanart, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["poster-sync-fanart.py", "Movies"])

    def _urlopen(target, timeout=None):
        if isinstance(target, urllib.request.Request):
            return _post_ok()
        assert target == "http://localhost:8420/api/posters/sync/stream"
        return _StreamResp([b"data: RUNNING 10%\n", b"data: DONE synced 42 posters\n"])

    monkeypatch.setattr(poster_sync_fanart.urllib.request, "urlopen", _urlopen)
    assert poster_sync_fanart.main() == 0
    assert "DONE synced 42 posters" in capsys.readouterr().out


def test_main_stream_error_line_returns_1(poster_sync_fanart, monkeypatch):
    monkeypatch.setattr("sys.argv", ["poster-sync-fanart.py", "Movies"])

    def _urlopen(target, timeout=None):
        if isinstance(target, urllib.request.Request):
            return _post_ok()
        return _StreamResp([b"data: ERROR something broke\n"])

    monkeypatch.setattr(poster_sync_fanart.urllib.request, "urlopen", _urlopen)
    assert poster_sync_fanart.main() == 1


def test_main_conflict_skips_quietly(poster_sync_fanart, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["poster-sync-fanart.py", "Movies"])

    def _urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            "url", 409, "conflict", {}, BytesIO(json.dumps({"detail": {"message": "already syncing"}}).encode())
        )

    monkeypatch.setattr(poster_sync_fanart.urllib.request, "urlopen", _urlopen)
    assert poster_sync_fanart.main() == 0
    assert "skipped for 'Movies'" in capsys.readouterr().out


def test_main_other_http_error_returns_1(poster_sync_fanart, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["poster-sync-fanart.py", "Movies"])

    def _urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            "url", 500, "server error", {}, BytesIO(json.dumps({"detail": {"message": "boom"}}).encode())
        )

    monkeypatch.setattr(poster_sync_fanart.urllib.request, "urlopen", _urlopen)
    assert poster_sync_fanart.main() == 1
    assert "failed to start sync for 'Movies'" in capsys.readouterr().err


def test_main_unreachable_control_panel_returns_1(poster_sync_fanart, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["poster-sync-fanart.py", "Movies"])

    def _urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(poster_sync_fanart.urllib.request, "urlopen", _urlopen)
    assert poster_sync_fanart.main() == 1
    assert "failed to reach Control Panel" in capsys.readouterr().err


def test_main_stream_lost_connection_returns_1(poster_sync_fanart, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["poster-sync-fanart.py", "Movies"])

    def _urlopen(target, timeout=None):
        if isinstance(target, urllib.request.Request):
            return _post_ok()
        raise urllib.error.URLError("stream dropped")

    monkeypatch.setattr(poster_sync_fanart.urllib.request, "urlopen", _urlopen)
    assert poster_sync_fanart.main() == 1
    assert "lost connection to sync stream" in capsys.readouterr().err


def test_main_stream_ends_without_done_or_error_returns_1(poster_sync_fanart, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["poster-sync-fanart.py", "Movies"])

    def _urlopen(target, timeout=None):
        if isinstance(target, urllib.request.Request):
            return _post_ok()
        return _StreamResp([b"data: RUNNING 50%\n"])

    monkeypatch.setattr(poster_sync_fanart.urllib.request, "urlopen", _urlopen)
    assert poster_sync_fanart.main() == 1
    assert "sync stream ended without a DONE/ERROR line" in capsys.readouterr().err


def test_main_ignores_non_data_lines(poster_sync_fanart, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["poster-sync-fanart.py", "Movies"])

    def _urlopen(target, timeout=None):
        if isinstance(target, urllib.request.Request):
            return _post_ok()
        return _StreamResp([b": keepalive\n", b"data: DONE all good\n"])

    monkeypatch.setattr(poster_sync_fanart.urllib.request, "urlopen", _urlopen)
    assert poster_sync_fanart.main() == 0
    out = capsys.readouterr().out
    assert "keepalive" not in out
    assert "DONE all good" in out

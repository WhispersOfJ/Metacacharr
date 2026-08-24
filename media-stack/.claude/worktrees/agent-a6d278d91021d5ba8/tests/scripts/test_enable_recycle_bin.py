import urllib.error


def _cfg(tmp_path, key="real-key"):
    return {
        "url": "http://localhost:7878",
        "key": key,
        "label": "Radarr",
        "recycle_bin": "/data/movies/.recyclebin",
        "host_recycle_bin": tmp_path / "movies" / ".recyclebin",
        "api_version": "v3",
    }


def test_missing_key_short_circuits(enable_recycle_bin, tmp_path):
    ok, detail = enable_recycle_bin.enable_recycle_bin("radarr", _cfg(tmp_path, key=None))
    assert ok is False
    assert "API key not configured" in detail


def test_placeholder_key_short_circuits(enable_recycle_bin, tmp_path):
    ok, detail = enable_recycle_bin.enable_recycle_bin("radarr", _cfg(tmp_path, key="changeme"))
    assert ok is False
    assert "API key not configured" in detail


def test_config_read_failure_reported(enable_recycle_bin, tmp_path, monkeypatch):
    def _raise(*a, **k):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(enable_recycle_bin, "api_request", _raise)
    ok, detail = enable_recycle_bin.enable_recycle_bin("radarr", _cfg(tmp_path))
    assert ok is False
    assert "config read failed" in detail


def test_already_set_is_left_alone(enable_recycle_bin, tmp_path, monkeypatch):
    monkeypatch.setattr(
        enable_recycle_bin, "api_request",
        lambda *a, **k: {"recycleBin": "/data/movies/.recyclebin"},
    )
    ok, detail = enable_recycle_bin.enable_recycle_bin("radarr", _cfg(tmp_path))
    assert ok is True
    assert "already set" in detail
    assert not (tmp_path / "movies" / ".recyclebin").exists()


def test_enables_recycle_bin_and_creates_host_dir(enable_recycle_bin, tmp_path, monkeypatch):
    calls = []

    def _api(url, key, method, path, body=None):
        calls.append((method, path, body))
        if method == "GET":
            return {}
        return {}

    monkeypatch.setattr(enable_recycle_bin, "api_request", _api)
    cfg = _cfg(tmp_path)
    ok, detail = enable_recycle_bin.enable_recycle_bin("radarr", cfg)

    assert ok is True
    assert "recycle bin set to /data/movies/.recyclebin" in detail
    assert cfg["host_recycle_bin"].is_dir()
    put_calls = [c for c in calls if c[0] == "PUT"]
    assert len(put_calls) == 1
    _, _, body = put_calls[0]
    assert body["recycleBin"] == "/data/movies/.recyclebin"
    assert body["recycleBinCleanupDays"] == 7


def test_config_write_failure_reported(enable_recycle_bin, tmp_path, monkeypatch):
    def _api(url, key, method, path, body=None):
        if method == "GET":
            return {}
        raise urllib.error.HTTPError(url, 500, "server error", None, None)

    monkeypatch.setattr(enable_recycle_bin, "api_request", _api)
    ok, detail = enable_recycle_bin.enable_recycle_bin("radarr", _cfg(tmp_path))
    assert ok is False
    assert "config write failed" in detail

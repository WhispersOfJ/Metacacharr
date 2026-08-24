import urllib.error


RADARR_CFG = {"url": "http://localhost:7878", "key": "real-key", "label": "Radarr"}


def test_trigger_backup_missing_key_short_circuits(arr_app_backup):
    cfg = {"url": "http://localhost:7878", "key": None, "label": "Radarr"}
    ok, detail = arr_app_backup.trigger_backup("radarr", cfg)
    assert ok is False
    assert "API key not configured" in detail


def test_trigger_backup_placeholder_key_short_circuits(arr_app_backup):
    cfg = {"url": "http://localhost:7878", "key": "changeme", "label": "Radarr"}
    ok, detail = arr_app_backup.trigger_backup("radarr", cfg)
    assert ok is False
    assert "API key not configured" in detail


def test_trigger_backup_start_failure_reported(arr_app_backup, monkeypatch):
    def _raise(*a, **k):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(arr_app_backup, "api_request", _raise)
    ok, detail = arr_app_backup.trigger_backup("radarr", RADARR_CFG)
    assert ok is False
    assert "failed to start" in detail


def test_trigger_backup_completes_immediately(arr_app_backup, monkeypatch):
    monkeypatch.setattr(arr_app_backup, "api_request", lambda *a, **k: {"id": 1, "status": "completed"})
    ok, detail = arr_app_backup.trigger_backup("radarr", RADARR_CFG)
    assert ok is True
    assert detail == "Radarr backup completed"


def test_trigger_backup_polls_until_completed(arr_app_backup, monkeypatch):
    monkeypatch.setattr(arr_app_backup.time, "sleep", lambda *_: None)
    responses = iter([
        {"id": 1, "status": "queued"},
        {"id": 1, "status": "started"},
        {"id": 1, "status": "completed"},
    ])
    monkeypatch.setattr(arr_app_backup, "api_request", lambda *a, **k: next(responses))
    ok, detail = arr_app_backup.trigger_backup("radarr", RADARR_CFG)
    assert ok is True
    assert detail == "Radarr backup completed"


def test_trigger_backup_reports_failed_status(arr_app_backup, monkeypatch):
    monkeypatch.setattr(arr_app_backup.time, "sleep", lambda *_: None)
    responses = iter([
        {"id": 1, "status": "queued"},
        {"id": 1, "status": "failed", "message": "disk full"},
    ])
    monkeypatch.setattr(arr_app_backup, "api_request", lambda *a, **k: next(responses))
    ok, detail = arr_app_backup.trigger_backup("radarr", RADARR_CFG)
    assert ok is False
    assert "disk full" in detail


def test_trigger_backup_status_check_failure_reported(arr_app_backup, monkeypatch):
    monkeypatch.setattr(arr_app_backup.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def _api(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"id": 1, "status": "queued"}
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(arr_app_backup, "api_request", _api)
    ok, detail = arr_app_backup.trigger_backup("radarr", RADARR_CFG)
    assert ok is False
    assert "status check failed" in detail


def test_trigger_backup_times_out_without_reaching_terminal_status(arr_app_backup, monkeypatch):
    monkeypatch.setattr(arr_app_backup.time, "sleep", lambda *_: None)
    # Every poll comes back "started" - time.monotonic() must actually
    # advance past POLL_TIMEOUT_SECONDS for the while-loop to exit, since
    # sleep() is stubbed out to not actually block.
    times = iter([0, 10, arr_app_backup.POLL_TIMEOUT_SECONDS + 1])
    monkeypatch.setattr(arr_app_backup.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(arr_app_backup, "api_request", lambda *a, **k: {"id": 1, "status": "started"})
    ok, detail = arr_app_backup.trigger_backup("radarr", RADARR_CFG)
    assert ok is False
    assert "still 'started'" in detail

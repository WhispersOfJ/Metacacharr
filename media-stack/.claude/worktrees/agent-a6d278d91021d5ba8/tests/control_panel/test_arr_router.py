"""Phase 3 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/arr/router.py's generic Radarr/Sonarr dispatch routes, ported from
app.py. Covers the auth-policy split (current_user vs current_user_or_service)
and the incident-derived logic in unstick-importing/queue-autofix/loop-
candidates, mirroring test_arr_root_folder_profile.py's httpx-mocking style.
"""
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient


def _login(client, main_module, password="correct-horse-battery-staple"):
    from core.security import hash_password
    from models.user import User

    db = main_module.SessionLocal()
    try:
        db.add(User(username="admin", password_hash=hash_password(password)))
        db.commit()
    finally:
        db.close()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert resp.status_code == 200


def _service_key_header(main_module):
    from core.security import hash_api_key
    from models.api_key import ApiKey

    db = main_module.SessionLocal()
    try:
        db.add(ApiKey(name="healthcheck-cron", key_hash=hash_api_key("raw-service-key")))
        db.commit()
    finally:
        db.close()
    return {"X-Api-Key": "raw-service-key"}


def _json_response(payload, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    return resp


# ---------------------------------------------------------------------
# Auth policy - read-only and automation-invoked mutating routes accept
# the service key; manual-only mutating routes require a session.
# ---------------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("GET", "/api/arr/radarr/search-status"),
    ("POST", "/api/arr/radarr/rss-sync"),
    ("POST", "/api/arr/radarr/search-missing"),
    ("POST", "/api/arr/radarr/unstick"),
    ("POST", "/api/arr/radarr/unstick-importing"),
    ("POST", "/api/arr/queue-autofix"),
    ("GET", "/api/arr/radarr/loop-candidates"),
    ("POST", "/api/arr/radarr/unmonitor"),
    ("GET", "/api/arr/radarr/manual-import"),
    ("POST", "/api/arr/radarr/manual-import-all"),
    ("GET", "/api/arr/radarr/blocklist"),
    ("POST", "/api/arr/radarr/blocklist/clear"),
    ("GET", "/api/backlog-status"),
    ("GET", "/api/arr/command-queue-summary"),
    ("GET", "/api/arr/queue-errors"),
    ("GET", "/api/arr/radarr/import-list/implementations"),
    ("POST", "/api/arr/radarr/import-list/add"),
    ("POST", "/api/mdblist/import-list"),
])
def test_automation_routes_accept_service_key(cp_main_app, monkeypatch, method, path):
    """Every route stack-queue-autofix.fish (and the stack-cli-arr-fleet
    skill) calls unattended must work with just the service key - the
    entire point of extending current_user_or_service's contract."""
    def fake_get(url, params=None, **kwargs):
        if "/queue" in url or "/history" in url or "/blocklist" in url or "/wanted" in url:
            return _json_response({"records": []})
        if "movies/wanted" in url or "episodes/wanted" in url:
            return _json_response({"data": []})
        return _json_response([])

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _json_response({}))
    monkeypatch.setattr(httpx, "delete", lambda *a, **k: _json_response({}))
    monkeypatch.setattr(httpx, "put", lambda *a, **k: _json_response({}))
    monkeypatch.setattr("services.arr.router.nzbdav_api", lambda *a, **k: {"queue": {"slots": [], "paused": False}})

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.request(method, path, headers=headers, json={"ids": [1]} if method == "POST" and "unmonitor" in path else None)
    assert resp.status_code != 401, resp.text


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/arr/radarr/exclude", {"movieId": 1}),
])
def test_manual_only_routes_reject_service_key(cp_main_app, monkeypatch, method, path, body):
    """Routes with no automation caller stay session-only even with a
    valid service key presented - import-list/implementations,
    import-list/add, and mdblist/import-list moved to
    test_automation_routes_accept_service_key above (2026-08-06's
    extend-service-key-auth commit made them automation-invoked too;
    radarr/exclude is the one route that commit's audit explicitly left
    current_user-only)."""
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.request(method, path, headers=headers, json=body)
    assert resp.status_code == 401


def test_no_credentials_is_401(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/arr/radarr/search-status")
    assert resp.status_code == 401


# ---------------------------------------------------------------------
# Behavior: rss-sync / search-missing / search-toggle
# ---------------------------------------------------------------------

def test_rss_sync_posts_command(cp_main_app, monkeypatch):
    posted = {}

    def fake_post(url, json=None, **kwargs):
        posted["url"], posted["json"] = url, json
        return _json_response({})

    monkeypatch.setattr(httpx, "post", fake_post)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/rss-sync")
    assert resp.status_code == 200
    assert "radarr:7878" in posted["url"]
    assert posted["json"] == {"name": "RssSync"}
    assert "Radarr" in resp.json()["message"]


def test_search_missing_unknown_app_404s(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/not-a-real-app/search-missing")
    assert resp.status_code == 404


# ---------------------------------------------------------------------
# Behavior: unstick-importing - the three verdict branches
# ---------------------------------------------------------------------

def test_unstick_importing_missing_path_clears_without_blocklist(cp_main_app, monkeypatch):
    queue_item = {
        "id": 1, "downloadId": "dl-1", "title": "Some Movie", "outputPath": "/data/movies/gone",
        "trackedDownloadState": "importing", "movieId": 42,
    }
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response({"records": [queue_item]}))
    deleted = {}

    def fake_delete(url, params=None, **kwargs):
        deleted["params"] = params
        return _json_response({}, status_code=200)

    monkeypatch.setattr(httpx, "delete", fake_delete)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _json_response({}))

    missing_result = MagicMock(exit_code=1)
    container = MagicMock()
    container.exec_run.side_effect = lambda cmd, **kwargs: missing_result
    monkeypatch.setattr("core.docker_client.docker_client.containers.get", lambda name: container)

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/arr/radarr/unstick-importing", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"][0]["verdict"] == "path-missing-cleared"
    assert deleted["params"]["blocklist"] == "false"


def test_unstick_importing_broken_file_blocklists(cp_main_app, monkeypatch):
    queue_item = {
        "id": 2, "downloadId": "dl-2", "title": "Some Show", "outputPath": "/data/shows/x",
        "trackedDownloadState": "importing", "seriesId": 7,
    }
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response({"records": [queue_item]}))
    deleted = {}

    def fake_delete(url, params=None, **kwargs):
        deleted["params"] = params
        return _json_response({}, status_code=200)

    monkeypatch.setattr(httpx, "delete", fake_delete)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _json_response({}))

    exists_ok = MagicMock(exit_code=0)
    find_symlinks = MagicMock()
    find_symlinks.output = b"/data/shows/x/file.mkv\n"
    dd_failed = MagicMock(exit_code=1, output=(b"", b"dd: read error"))

    container = MagicMock()

    def exec_run(cmd, **kwargs):
        if cmd[0] == "test":
            return exists_ok
        if cmd[0] == "find":
            return find_symlinks
        if cmd[0] == "timeout":
            return dd_failed
        raise AssertionError(f"unexpected exec {cmd}")

    container.exec_run.side_effect = exec_run
    monkeypatch.setattr("core.docker_client.docker_client.containers.get", lambda name: container)

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/arr/sonarr/unstick-importing", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"][0]["verdict"] == "broken-blocklisted"
    assert deleted["params"]["blocklist"] == "true"


def test_unstick_importing_no_targets_is_noop(cp_main_app, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response({"records": []}))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/arr/radarr/unstick-importing", headers=headers)
    assert resp.status_code == 200
    assert "No downloads currently importing" in resp.json()["message"]


# ---------------------------------------------------------------------
# Behavior: queue-autofix - storm guard + radarr-only importBlocked
# ---------------------------------------------------------------------

def test_queue_autofix_only_blocklists_import_blocked_on_radarr(cp_main_app, monkeypatch):
    radarr_queue = [
        {"id": 1, "title": "R1", "trackedDownloadState": "failedPending", "movieId": 10, "movie": {"monitored": True}},
        {"id": 2, "title": "R2", "trackedDownloadState": "importBlocked", "movieId": 11, "movie": {"monitored": True}},
    ]
    sonarr_queue = [
        # importBlocked on sonarr should NOT be touched (radarr-only per app.py's comment).
        {"id": 3, "title": "S1", "trackedDownloadState": "importBlocked", "episodeId": 20, "episode": {"monitored": True}},
    ]

    def fake_get(url, params=None, **kwargs):
        if "radarr:7878/api/v3/queue" in url:
            return _json_response({"records": radarr_queue})
        if "sonarr:8989/api/v3/queue" in url:
            return _json_response({"records": sonarr_queue})
        return _json_response({})

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "delete", lambda *a, **k: _json_response({}, status_code=200))
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _json_response({}))
    monkeypatch.setattr("services.arr.router.nzbdav_api", lambda *a, **k: {"queue": {"slots": [], "paused": False}})

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/arr/queue-autofix", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["radarr"]["import_blocked"] == 1
    assert body["sonarr"]["import_blocked"] == 0
    assert len(body["sonarr"]["fixed"]) == 0  # sonarr's importBlocked item untouched


def test_queue_autofix_disables_autoredownload_on_storm(cp_main_app, monkeypatch):
    from core import settings as settings_core
    settings_core.update_settings({"failed_pending_storm_threshold": 2})

    failed_items = [
        {"id": i, "title": f"F{i}", "trackedDownloadState": "failedPending", "movieId": i, "movie": {"monitored": True}}
        for i in range(3)
    ]

    def fake_get(url, params=None, **kwargs):
        if "radarr:7878/api/v3/queue" in url:
            return _json_response({"records": failed_items})
        if "sonarr:8989/api/v3/queue" in url:
            return _json_response({"records": []})
        if "config/downloadclient" in url:
            return _json_response({"id": 1, "autoRedownloadFailed": True})
        return _json_response({})

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "delete", lambda *a, **k: _json_response({}, status_code=200))
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _json_response({}))
    monkeypatch.setattr(httpx, "put", lambda *a, **k: _json_response({}))
    monkeypatch.setattr("services.arr.router.nzbdav_api", lambda *a, **k: {"queue": {"slots": [], "paused": True}})

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/arr/queue-autofix", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["radarr"]["autoredownload_disabled"] is True
    assert "paused" in body["message"].lower()


# ---------------------------------------------------------------------
# Behavior: loop-candidates suggestion logic
# ---------------------------------------------------------------------

def test_loop_candidates_flags_dedup_suffix_bug_over_unmonitor(cp_main_app, monkeypatch):
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    history = {"records": [
        {"movieId": 5, "date": now.isoformat(), "sourceTitle": "Movie (1)"},
        {"movieId": 5, "date": now.isoformat(), "sourceTitle": "Movie (2)"},
    ]}
    movie_detail = {"id": 5, "title": "Movie", "monitored": True, "hasFile": False}
    queue = {"records": [{"movieId": 5, "outputPath": "/data/movies/Movie (2).mkv"}]}

    def fake_get(url, params=None, **kwargs):
        if "/history" in url:
            return _json_response(history)
        if "/movie/5" in url:
            return _json_response(movie_detail)
        if "/queue" in url:
            return _json_response(queue)
        return _json_response({})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/arr/radarr/loop-candidates", headers=headers)
    assert resp.status_code == 200
    candidates = resp.json()["candidates"]
    assert candidates[0]["suggested_action"] == "suffix-bug"


def test_loop_candidates_below_threshold_excluded(cp_main_app, monkeypatch):
    history = {"records": [{"movieId": 9, "date": "2026-01-01T00:00:00Z", "sourceTitle": "Once"}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response(history))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/arr/radarr/loop-candidates", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["candidates"] == []


# ---------------------------------------------------------------------
# Behavior: manual-import-all skips unmatched candidates
# ---------------------------------------------------------------------

def test_manual_import_all_skips_unresolved_matches(cp_main_app, monkeypatch):
    queue_items = {"records": [
        {"id": 1, "outputPath": "/x", "downloadId": "d1", "trackedDownloadState": "importPending"},
    ]}
    manual_import_candidates = [
        {"name": "matched.mkv", "path": "/x/matched.mkv", "movie": {"id": 5, "title": "Matched"},
         "quality": {}, "languages": [], "size": 1},
        {"name": "unmatched.mkv", "path": "/x/unmatched.mkv", "movie": None, "quality": {}, "languages": [], "size": 1},
    ]

    def fake_get(url, params=None, **kwargs):
        if "/queue" in url:
            return _json_response(queue_items)
        if "/manualimport" in url:
            return _json_response(manual_import_candidates)
        return _json_response({})

    posted = {}

    def fake_post(url, json=None, **kwargs):
        posted["json"] = json
        return _json_response({})

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/arr/radarr/manual-import-all", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert "1 file(s) skipped" in resp.json()["message"]
    assert len(posted["json"]["files"]) == 1


def test_manual_import_all_no_files_reports_zero(cp_main_app, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response({"records": []}))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/arr/radarr/manual-import-all", headers=headers)
    assert resp.status_code == 200
    assert "No importable files" in resp.json()["message"]


ALL_ARR_APPS = ["radarr", "sonarr"]


@pytest.mark.parametrize("app_name", ALL_ARR_APPS)
@pytest.mark.parametrize("path", [
    "/cutoff-unmet",
    "/recently-added",
    "/import-lists",
    "/import-list/implementations",
    "/customformat-snapshot",
])
def test_per_app_routes_accept_every_arr_instance(cp_main_app, monkeypatch, app_name, path):
    def fake_get(url, params=None, **kwargs):
        # customformat-snapshot walks customformat then qualityprofile and
        # indexes into both, so a bare {} would fail for reasons unrelated
        # to the guard under test.
        if "/customformat" in url:
            return _json_response([{"id": 1, "name": "x265 (HD)"}])
        if "/qualityprofile" in url:
            return _json_response([{"name": "Anything", "formatItems": [{"format": 1, "score": -10000}]}])
        if "/wanted" in url:
            return _json_response({"records": [], "totalRecords": 0})
        return _json_response([])

    monkeypatch.setattr(httpx, "get", fake_get)

    client = TestClient(cp_main_app.app)
    resp = client.get(f"/api/arr/{app_name}{path}", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200, f"{app_name}{path} -> {resp.status_code} {resp.text}"


@pytest.mark.parametrize("app_name,expected", [
    ("radarr", "/api/v3/movie"),
    ("sonarr", "/api/v3/series"),
])
def test_recently_added_picks_endpoint_by_app_shape(cp_main_app, monkeypatch, app_name, expected):
    seen = {}

    def fake_get(url, params=None, **kwargs):
        seen["url"] = url
        return _json_response([])

    monkeypatch.setattr(httpx, "get", fake_get)

    client = TestClient(cp_main_app.app)
    resp = client.get(f"/api/arr/{app_name}/recently-added", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    assert seen["url"].endswith(expected), f"{app_name} hit {seen['url']}, expected ...{expected}"


@pytest.mark.parametrize("app_name", ALL_ARR_APPS)
def test_import_list_add_accepts_every_arr_instance(cp_main_app, monkeypatch, app_name):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response([]))
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _json_response({}))

    client = TestClient(cp_main_app.app)
    resp = client.post(
        f"/api/arr/{app_name}/import-list/add",
        headers=_service_key_header(cp_main_app),
        json={"implementation": "TraktList", "name": "test", "fields": {}},
    )
    # Not asserting success - the payload is deliberately thin. Asserting
    # only that it is never rejected for being an unrecognized instance.
    assert "Only radarr and sonarr" not in resp.text

"""Phase 6 (PLANS.md) validation for services/watchstate/router.py.

Three behaviours carry the weight here, all of them places where WatchState's
API says something that reads like a failure but isn't, or vice versa:

- an empty history is a **404 with an error body**, which is the normal state
  before the first import finishes and must not surface as a failure;
- an import is **queued, not run** - the response says so rather than implying
  the data is already there;
- `export_enabled` is reported because it is deliberately off (export writes
  watch state back into Plex), so a silent flip has somewhere to show up.

The rest is auth gating and the header the whole API depends on.
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


def _service_key_header(main_module):
    from core.security import hash_api_key
    from models.api_key import ApiKey

    db = main_module.SessionLocal()
    try:
        db.add(ApiKey(name="test-key", key_hash=hash_api_key("raw-service-key")))
        db.commit()
    finally:
        db.close()
    return {"X-Api-Key": "raw-service-key"}


def _resp(json_body, status_code=200):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_body
    return r


VERSION = {"version": "v1.10.2"}

BACKEND = {
    "name": "plex",
    "type": "plex",
    "url": "http://test-plex:32400",
    "import": {"enabled": True, "lastSync": 1786571546},
    "export": {"enabled": False, "lastSync": None},
    "urls": {"webhook": "/v1/api/webhook?apikey=secret-token"},
}

TASK = {
    "name": "import",
    "enabled": True,
    "timer": "25 0-1,6-23 * * *",
    "next_run": "2026-08-12T18:25:00-04:00",
    "prev_run": "2026-08-12T17:25:00-04:00",
    "queued": False,
}

HISTORY = {
    "history": [
        # `updated` is a unix int and `watched` a 0/1 int - both are what
        # WatchState really returns, not the ISO/bool a reader would assume.
        {"id": 12, "title": "The Wire", "type": "episode", "year": 2002,
         "season": 1, "episode": 3, "watched": 1, "via": "plex",
         "updated": 1786570698},
    ],
    "paging": {"total": 4231, "perpage": 1, "current_page": 1},
}


def _mock_watchstate(monkeypatch, *, history=HISTORY, history_status=200,
                     backends=None, task=None, seen=None):
    """Stand in for WatchState's version / backends / tasks / history API."""
    backends = [BACKEND] if backends is None else backends
    task = TASK if task is None else task

    def fake_request(method, url, params=None, headers=None, timeout=None):
        if seen is not None:
            seen.append((method, url, params, headers))
        if url.endswith("/system/version"):
            return _resp(VERSION)
        if url.endswith("/backends"):
            return _resp(backends)
        if url.endswith("/tasks/import/queue"):
            return _resp({"id": "1f196988-06d6-6418", "status": 0, "event": "run_task"})
        if url.endswith("/tasks/import"):
            return _resp(task)
        if url.endswith("/history"):
            return _resp(history, history_status)
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr("services.watchstate.router.httpx.request", fake_request)


# --- auth -------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("GET", "/api/watchstate/status"),
    ("POST", "/api/watchstate/import"),
    ("GET", "/api/watchstate/history"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    assert client.request(method, path).status_code == 401


def test_every_call_carries_the_api_key_header(cp_main_app, monkeypatch):
    """WS_SECURE_API_ENDPOINTS is on, so an unauthenticated call gets a 400
    from WatchState that reads like a malformed request rather than a missing
    key."""
    seen = []
    _mock_watchstate(monkeypatch, seen=seen)
    client = TestClient(cp_main_app.app)
    client.get("/api/watchstate/status", headers=_service_key_header(cp_main_app))
    assert seen
    assert all(h.get("X-apikey") == "test-watchstate-key" for _, _, _, h in seen)


# --- status -----------------------------------------------------------

def test_status_reports_backend_task_and_totals(cp_main_app, monkeypatch):
    _mock_watchstate(monkeypatch)
    client = TestClient(cp_main_app.app)
    body = client.get("/api/watchstate/status", headers=_service_key_header(cp_main_app)).json()
    assert body["version"] == "v1.10.2"
    assert body["tracked"] == 4231
    assert body["backend"]["import_enabled"] is True
    assert body["task"]["timer"] == "25 0-1,6-23 * * *"
    assert body["task"]["next_run"] == "2026-08-12T18:25:00-04:00"


def test_status_surfaces_export_being_enabled(cp_main_app, monkeypatch):
    """Export writes watch state back INTO Plex and is off by design. If it is
    ever on, this is where that becomes visible."""
    flipped = {**BACKEND, "export": {"enabled": True, "lastSync": None}}
    _mock_watchstate(monkeypatch, backends=[flipped])
    client = TestClient(cp_main_app.app)
    body = client.get("/api/watchstate/status", headers=_service_key_header(cp_main_app)).json()
    assert body["backend"]["export_enabled"] is True


def test_status_calls_out_a_missing_backend(cp_main_app, monkeypatch):
    """No backend means every import is a no-op that reports success, so it
    has to name the fix rather than read as idle."""
    _mock_watchstate(monkeypatch, backends=[])
    client = TestClient(cp_main_app.app)
    body = client.get("/api/watchstate/status", headers=_service_key_header(cp_main_app)).json()
    assert body["backend"] is None
    assert "watchstate-provision" in body["message"]


def test_status_ignores_other_backends(cp_main_app, monkeypatch):
    other = {**BACKEND, "name": "jellyfin", "url": "http://elsewhere:8096"}
    _mock_watchstate(monkeypatch, backends=[other, BACKEND])
    client = TestClient(cp_main_app.app)
    body = client.get("/api/watchstate/status", headers=_service_key_header(cp_main_app)).json()
    assert body["backend"]["url"] == "http://test-plex:32400"


def test_status_survives_an_empty_history(cp_main_app, monkeypatch):
    """404 'No Results.' is what an un-imported database answers - the normal
    state on first boot, not a failure."""
    _mock_watchstate(monkeypatch, history={"error": {"code": 404, "message": "No Results."}},
                     history_status=404)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/watchstate/status", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    assert resp.json()["tracked"] == 0


def test_status_says_when_an_import_is_queued(cp_main_app, monkeypatch):
    _mock_watchstate(monkeypatch, task={**TASK, "queued": True})
    client = TestClient(cp_main_app.app)
    body = client.get("/api/watchstate/status", headers=_service_key_header(cp_main_app)).json()
    assert "queued" in body["message"].lower()


# --- import -----------------------------------------------------------

def test_import_queues_rather_than_claiming_it_ran(cp_main_app, monkeypatch):
    """WatchState enqueues an event and a separate dispatcher runs it, so
    reporting 'imported' here would be a lie that hides a stuck queue."""
    _mock_watchstate(monkeypatch)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/watchstate/import", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    body = resp.json()
    assert body["event_id"] == "1f196988-06d6-6418"
    assert "queued" in body["message"].lower()


def test_import_reports_a_rejection(cp_main_app, monkeypatch):
    def fake_request(method, url, params=None, headers=None, timeout=None):
        if url.endswith("/tasks/import/queue"):
            return _resp({"error": {"code": 404, "message": "Task not found."}}, 404)
        raise AssertionError(url)

    monkeypatch.setattr("services.watchstate.router.httpx.request", fake_request)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/watchstate/import", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 502
    assert "Task not found." in resp.json()["detail"]["message"]


# --- history ----------------------------------------------------------

def test_history_shapes_rows_with_their_source(cp_main_app, monkeypatch):
    """`via` and `updated_at` are how a webhook-delivered event is told apart
    from one the scheduled import picked up."""
    _mock_watchstate(monkeypatch)
    client = TestClient(cp_main_app.app)
    body = client.get("/api/watchstate/history", headers=_service_key_header(cp_main_app)).json()
    row = body["history"][0]
    assert row["title"] == "The Wire"
    assert row["via"] == "plex"
    assert row["watched"] is True
    # Rendered, not the raw epoch: a bare 1786570698 in a terminal answers
    # nothing about whether the webhook or the scheduled import wrote it.
    assert row["updated_at"].startswith("2026-08-12T")
    assert body["total"] == 4231


def test_history_passes_through_an_already_formatted_timestamp(cp_main_app, monkeypatch):
    """Dropping an unparseable timestamp would lose the only timing
    information a row carries."""
    odd = {"history": [{"id": 1, "title": "X", "updated": "yesterday"}], "paging": {"total": 1}}
    _mock_watchstate(monkeypatch, history=odd)
    client = TestClient(cp_main_app.app)
    body = client.get("/api/watchstate/history", headers=_service_key_header(cp_main_app)).json()
    assert body["history"][0]["updated_at"] == "yesterday"


def test_history_passes_the_title_filter_through(cp_main_app, monkeypatch):
    seen = []
    _mock_watchstate(monkeypatch, seen=seen)
    client = TestClient(cp_main_app.app)
    client.get("/api/watchstate/history?item=The%20Wire&limit=5",
               headers=_service_key_header(cp_main_app))
    params = next(p for m, u, p, h in seen if u.endswith("/history"))
    assert params["title"] == "The Wire"
    assert params["perpage"] == 5


def test_history_omits_the_filter_when_blank(cp_main_app, monkeypatch):
    """The CLI sends an omitted optional argument as an empty string, which
    must mean 'everything', not 'titled empty string'."""
    seen = []
    _mock_watchstate(monkeypatch, seen=seen)
    client = TestClient(cp_main_app.app)
    client.get("/api/watchstate/history?item=", headers=_service_key_header(cp_main_app))
    params = next(p for m, u, p, h in seen if u.endswith("/history"))
    assert "title" not in params


def test_history_reports_empty_without_erroring(cp_main_app, monkeypatch):
    _mock_watchstate(monkeypatch, history={"error": {"code": 404, "message": "No Results."}},
                     history_status=404)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/watchstate/history?item=Nothing",
                      headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    body = resp.json()
    assert body["history"] == []
    assert body["total"] == 0
    assert "watchstate-status" in body["message"]


def test_history_rejects_a_nonpositive_limit(cp_main_app, monkeypatch):
    _mock_watchstate(monkeypatch)
    client = TestClient(cp_main_app.app)
    assert client.get("/api/watchstate/history?limit=0",
                      headers=_service_key_header(cp_main_app)).status_code == 400


def test_history_surfaces_a_real_failure(cp_main_app, monkeypatch):
    """A 500 is not the empty-history case and must not be flattened into
    'no results'."""
    _mock_watchstate(monkeypatch, history={"error": {"code": 500, "message": "db locked"}},
                     history_status=500)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/watchstate/history", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 502
    assert "db locked" in resp.json()["detail"]["message"]

"""Coverage for scripts/watchstate-provision.py.

Two things here are easy to get wrong and expensive to get wrong:

- **Re-running must not re-add the backend.** A fresh add issues a new webhook
  token, and Plex keeps posting to the old one - the webhook silently stops
  working while everything still reports healthy.
- **The webhook URL must come from WatchState**, token and all. Hand-building
  `/v1/api/webhook` without the backend's own token produces a URL that
  answers but attributes nothing.
"""
import pytest

ENV = {
    "WS_API_KEY": "ws-key",
    "PLEX_URL": "http://plex:32400",
    "PLEX_TOKEN": "plex-token",
    "HOST_IP": "192.168.4.20",
}

BACKEND = {
    "name": "plex",
    "url": "http://plex:32400",
    "urls": {"webhook": "/v1/api/webhook?apikey=backend-token"},
}

USERS = [
    {"id": 379894006, "name": "guest", "admin": False},
    {"id": 277265765, "name": "james_nealon", "admin": True},
]


def _fake_request(calls, *, backends=None, users=None, add_status=201):
    backends = [] if backends is None else backends
    users = USERS if users is None else users

    def request(method, path, api_key, body=None):
        calls.append((method, path, body))
        if method == "GET" and path == "/system/version":
            return 200, {"version": "v1.10.2"}
        if method == "GET" and path == "/backends":
            return 200, backends
        if path == "/backends/uuid/plex":
            return 200, {"identifier": "server-uuid"}
        if path == "/backends/users/plex":
            return 200, users
        if method == "POST" and path == "/backends":
            return add_status, BACKEND
        if path.endswith("/webhook"):
            return 200, {"message": "ok"}
        raise AssertionError(f"unexpected call: {method} {path}")

    return request


def _paths(calls, method=None):
    return [p for m, p, _ in calls if method is None or m == method]


# --- backend -----------------------------------------------------------

def test_add_sends_uuid_and_admin_user(watchstate_provision, monkeypatch):
    """Both are required in practice: the uuid becomes Plex's
    X-Plex-Client-Identifier header, and without the user id the add fails on
    the literal unsubstituted placeholder '{id}'."""
    calls = []
    monkeypatch.setattr(watchstate_provision, "request", _fake_request(calls))
    watchstate_provision.provision_backend(ENV, "ws-key", dry_run=False)

    body = next(b for m, p, b in calls if m == "POST" and p == "/backends")
    assert body["uuid"] == "server-uuid"
    assert body["user"] == 277265765
    assert body["import"]["enabled"] is True
    assert body["export"]["enabled"] is False


def test_the_admin_user_is_picked_not_the_first(watchstate_provision, monkeypatch):
    """This server also has a restricted 'guest' account. Tracking it would
    record whatever the guest watched as Bear's own watch state."""
    calls = []
    monkeypatch.setattr(watchstate_provision, "request", _fake_request(calls))
    assert watchstate_provision.admin_user_id(ENV, "ws-key", "server-uuid") == 277265765


def test_no_admin_user_is_fatal(watchstate_provision, monkeypatch):
    calls = []
    monkeypatch.setattr(watchstate_provision, "request",
                        _fake_request(calls, users=[{"id": 1, "name": "guest", "admin": False}]))
    with pytest.raises(SystemExit, match="no admin user"):
        watchstate_provision.admin_user_id(ENV, "ws-key", "server-uuid")


def test_an_existing_backend_is_left_alone(watchstate_provision, monkeypatch):
    """Re-adding would issue a new webhook token and orphan the one Plex
    already posts to, with nothing reporting a failure."""
    calls = []
    monkeypatch.setattr(watchstate_provision, "request", _fake_request(calls, backends=[BACKEND]))
    backend = watchstate_provision.provision_backend(ENV, "ws-key", dry_run=False)

    assert backend == BACKEND
    assert "/backends" not in _paths(calls, "POST")


def test_dry_run_writes_nothing(watchstate_provision, monkeypatch):
    calls = []
    monkeypatch.setattr(watchstate_provision, "request", _fake_request(calls))
    watchstate_provision.provision_backend(ENV, "ws-key", dry_run=True)
    assert _paths(calls, "POST") == []


def test_a_failed_add_is_fatal(watchstate_provision, monkeypatch):
    calls = []
    monkeypatch.setattr(watchstate_provision, "request", _fake_request(calls, add_status=400))
    with pytest.raises(SystemExit, match="add failed"):
        watchstate_provision.provision_backend(ENV, "ws-key", dry_run=False)


def test_missing_plex_credentials_are_fatal(watchstate_provision, monkeypatch):
    calls = []
    monkeypatch.setattr(watchstate_provision, "request", _fake_request(calls))
    with pytest.raises(SystemExit, match="PLEX_TOKEN"):
        watchstate_provision.provision_backend({"PLEX_URL": "http://plex:32400"}, "ws-key", dry_run=False)


# --- webhook -----------------------------------------------------------

def test_webhook_url_is_the_host_ip_and_carries_the_backend_token(watchstate_provision, monkeypatch):
    """plex runs network_mode: host in this stack, so it cannot resolve
    'watchstate' - PLANS.md 6.4's docker-network URL would never fire. The
    token identifies which backend is posting; one endpoint serves them all."""
    calls = []
    monkeypatch.setattr(watchstate_provision, "request", _fake_request(calls))
    watchstate_provision.provision_webhook(BACKEND, ENV, "ws-key", dry_run=False)

    body = next(b for m, p, b in calls if p.endswith("/webhook"))
    assert body["webhook_url"] == "http://192.168.4.20:8705/v1/api/webhook?apikey=backend-token"
    assert "watchstate:8080" not in body["webhook_url"]


def test_webhook_registration_failure_is_fatal(watchstate_provision, monkeypatch):
    def request(method, path, api_key, body=None):
        return 400, {"error": {"code": 400, "message": "Invalid webhook URL provided."}}

    monkeypatch.setattr(watchstate_provision, "request", request)
    with pytest.raises(SystemExit, match="Invalid webhook URL"):
        watchstate_provision.provision_webhook(BACKEND, ENV, "ws-key", dry_run=False)


def test_a_backend_without_a_webhook_url_is_fatal(watchstate_provision, monkeypatch):
    """Better to stop than to hand-build the URL: without the backend's token
    the endpoint answers but attributes the event to nothing."""
    monkeypatch.setattr(watchstate_provision, "request", _fake_request([]))
    with pytest.raises(SystemExit, match="did not report a webhook URL"):
        watchstate_provision.provision_webhook({"name": "plex"}, ENV, "ws-key", dry_run=False)


def test_webhook_dry_run_writes_nothing(watchstate_provision, monkeypatch):
    calls = []
    monkeypatch.setattr(watchstate_provision, "request", _fake_request(calls))
    watchstate_provision.provision_webhook(BACKEND, ENV, "ws-key", dry_run=True)
    assert calls == []


def test_the_token_is_kept_out_of_stdout(watchstate_provision, monkeypatch, capsys):
    """This script's output lands in terminals and commit notes."""
    calls = []
    monkeypatch.setattr(watchstate_provision, "request", _fake_request(calls))
    watchstate_provision.provision_webhook(BACKEND, ENV, "ws-key", dry_run=False)
    assert "backend-token" not in capsys.readouterr().out

"""Shared fixtures for the media-stack unit test suite."""
import importlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROL_PANEL_DIR = REPO_ROOT / "control-panel"
SCRIPTS_DIR = REPO_ROOT / "scripts"


@pytest.fixture
def cp_main_app(monkeypatch, tmp_path):
    """Fresh import of control-panel/main.py (the evolved backend, Phase 1
    of .claude/plans/evolved-control-panel-backend.plan.md) against a
    throwaway sqlite file - never the real /data mount. Same fresh-import-
    per-test rationale as cp_app: module-level state (the FastAPI app
    object, its startup-created engine) shouldn't leak between tests."""
    db_path = tmp_path / "control-panel-test.db"
    monkeypatch.setenv("CONTROL_PANEL_DB_PATH", str(db_path))
    monkeypatch.setenv("CONTROL_PANEL_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("CONTROL_PANEL_SECRET_KEY", "test-secret-key-not-for-prod")
    # main.py's verify_same_origin middleware (Phase 2) checks the Host
    # header against HOST_IP - TestClient's default Host is "testserver",
    # so it needs to be in ALLOWED_HOSTS or every mutating-route test 403s.
    monkeypatch.setenv("HOST_IP", "testserver")
    # core.docker_client calls docker.from_env() at import time (imported
    # transitively via services.host.router) - same real-socket problem
    # cp_app's fixture solves for app.py, same fix.
    monkeypatch.setattr("docker.from_env", lambda: MagicMock())
    # core.arr_client (Phase 3) indexes these directly (os.environ[...], not
    # .get) to build ARR_APPS at import time - same reasoning as cp_app's
    # fixture above for app.py's own ARR_APPS.
    monkeypatch.setenv("RADARR_API_KEY", "test-radarr-key")
    monkeypatch.setenv("SONARR_API_KEY", "test-sonarr-key")
    monkeypatch.setenv("PROWLARR_API_KEY", "test-prowlarr-key")
    # core.plex_client reads these with os.environ.get (default "") so
    # module import never KeyErrors without them, but plex_headers() fails
    # a real request at call time if either is unset - needed for Phase 4
    # Plex route tests to reach their mocked httpx calls instead of a 503.
    monkeypatch.setenv("PLEX_URL", "http://test-plex:32400")
    monkeypatch.setenv("PLEX_TOKEN", "test-plex-token")
    # core.nzbdav_client reads this with os.environ.get - same call-time-
    # not-import-time failure mode as PLEX_URL/PLEX_TOKEN above.
    monkeypatch.setenv("FRONTEND_BACKEND_API_KEY", "test-nzbdav-key")
    # services/watchstate/router.py indexes this per request (os.environ[...])
    # to build the X-apikey header - a missing key is a deployment fault, not
    # something to send an unauthenticated request over.
    monkeypatch.setenv("WS_API_KEY", "test-watchstate-key")
    monkeypatch.delenv("CONTROL_PANEL_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("CONTROL_PANEL_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("CONTROL_PANEL_SERVICE_API_KEY", raising=False)

    # Must clear every submodule (models.user, models.api_key, ...), not
    # just the package names - leaving e.g. models.user cached meant its
    # User class stayed bound to the PREVIOUS test's core.db.Base, so the
    # next test's Base.metadata.create_all() created tables for an empty,
    # unrelated metadata object (confirmed live: intermittent "no such
    # table" failures that depended on test run order).
    _cp_prefixes = ("main", "core", "models", "services")

    def _clear_cp_modules():
        for mod_name in list(sys.modules):
            if mod_name in _cp_prefixes or mod_name.split(".")[0] in _cp_prefixes:
                sys.modules.pop(mod_name, None)

    sys.path.insert(0, str(CONTROL_PANEL_DIR))
    _clear_cp_modules()
    try:
        module = importlib.import_module("main")
        yield module
    finally:
        _clear_cp_modules()
        sys.path.remove(str(CONTROL_PANEL_DIR))


def _import_script(name: str):
    """Import scripts/<name>.py by file path under a private module-cache
    key. Needed because names like `arr-app-backup` aren't valid Python
    module names, so a plain `import` can't reach them even with the
    scripts dir on sys.path."""
    path = SCRIPTS_DIR / f"{name}.py"
    mod_name = f"_script_{name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


# One module-scoped fixture per tested script - each imports once per test
# module and hands back the live module object, so tests can call its
# functions directly and monkeypatch its globals.
@pytest.fixture(scope="module")
def setup_wizard():
    return _import_script("setup_wizard")


@pytest.fixture(scope="module")
def scrape_letterboxd():
    return _import_script("scrape_letterboxd")


@pytest.fixture(scope="module")
def audit_tmdb_links():
    return _import_script("audit-tmdb-links")


@pytest.fixture(scope="module")
def arr_app_backup():
    return _import_script("arr-app-backup")


@pytest.fixture(scope="module")
def enable_recycle_bin():
    return _import_script("enable-recycle-bin")


@pytest.fixture(scope="module")
def bearmount_prune_history():
    return _import_script("bearmount-prune-history")


@pytest.fixture(scope="module")
def plex_health_monitor():
    return _import_script("plex-health-monitor")


@pytest.fixture(scope="module")
def plex_webhook_listener():
    return _import_script("plex-webhook-listener")


@pytest.fixture(scope="module")
def plex_library_report():
    return _import_script("plex-library-report")


@pytest.fixture(scope="module")
def poster_sync_fanart():
    return _import_script("poster-sync-fanart")


@pytest.fixture(scope="module")
def watchstate_provision():
    return _import_script("watchstate-provision")


@pytest.fixture(scope="module")
def mdblist_toplists_import():
    return _import_script("mdblist_toplists_import")


@pytest.fixture(scope="module")
def provision_cleanuparr_instances():
    return _import_script("provision-cleanuparr-instances")

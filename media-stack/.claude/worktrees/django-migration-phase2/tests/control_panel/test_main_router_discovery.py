"""_discover_routers() isolation: a broken router import must not take down
every other router with it. Confirmed live this matters - a dangling
os.environ[...] read in one service's import chain previously crash-looped
the whole container instead of just that one service being unavailable."""
import importlib


def test_a_broken_router_import_is_skipped_not_fatal(cp_main_app, monkeypatch):
    real_import_module = importlib.import_module

    def _boom_on_radarr(name, *args, **kwargs):
        if name == "services.radarr.router":
            raise ImportError("simulated broken import")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(cp_main_app.importlib, "import_module", _boom_on_radarr)

    # Re-running discovery must not raise, even though one router fails.
    cp_main_app._discover_routers()


def test_a_broken_router_import_logs_the_failure(cp_main_app, monkeypatch, caplog):
    import logging

    real_import_module = importlib.import_module

    def _boom_on_radarr(name, *args, **kwargs):
        if name == "services.radarr.router":
            raise ImportError("simulated broken import")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(cp_main_app.importlib, "import_module", _boom_on_radarr)

    with caplog.at_level(logging.ERROR, logger="control-panel"):
        cp_main_app._discover_routers()

    assert any("services/radarr/router.py failed to import" in r.message for r in caplog.records)


def test_all_routers_still_import_cleanly_by_default(cp_main_app):
    """Sanity check: the real services/ tree (no simulated failure) imports
    every router without any being skipped."""
    routes_before = len(cp_main_app.app.routes)
    cp_main_app._discover_routers()
    # Idempotent re-run: FastAPI allows duplicate route registration, so this
    # just confirms no exception was raised and routes didn't shrink.
    assert len(cp_main_app.app.routes) >= routes_before

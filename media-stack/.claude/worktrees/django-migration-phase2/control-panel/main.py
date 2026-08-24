"""Control-panel backend entrypoint - the evolved backend from
.claude/plans/evolved-control-panel-backend.plan.md. Cutover from the
retired app.py completed 2026-08-05; this is the only backend module.
"""
import importlib
import os
import socket
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import models  # noqa: F401  (registers every table on Base before create_all)
from core.db import Base, SessionLocal, engine
from core.docker_client import docker_client
from core.logging_config import logger
from core.security import hash_api_key, hash_password
from models.api_key import ApiKey
from models.user import User

app = FastAPI(title="Control Panel (evolved backend)")

# Defense-in-depth alongside the real session auth added in Phase 1 - ported
# 1:1 from app.py's verify_same_origin (fixed under /cso, commit e360961).
# Session cookies are already SameSite=Lax/httponly, but this Host/Origin
# check stays: the plan's Phase 1 "Mirror" note requires auth to be at
# least as strong as this check, not a replacement for it.
HOST_IP = os.environ.get("HOST_IP")
ALLOWED_HOSTS = {h for h in (HOST_IP, "localhost", "127.0.0.1") if h}


def _own_network_gateway() -> str | None:
    try:
        self_container = docker_client.containers.get(socket.gethostname())
        for net in self_container.attrs.get("NetworkSettings", {}).get("Networks", {}).values():
            if net.get("Gateway"):
                return net["Gateway"]
    except Exception:
        pass
    return None


LOOPBACK_IPS = {"127.0.0.1", "::1"}
if _gw := _own_network_gateway():
    LOOPBACK_IPS.add(_gw)


@app.middleware("http")
async def verify_same_origin(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in ALLOWED_HOSTS:
            return JSONResponse(
                status_code=403,
                content={"ok": False, "message": "Rejected: Host header did not match this panel's configured HOST_IP."},
            )
        if host in ("localhost", "127.0.0.1"):
            client_host = request.client.host if request.client else None
            if client_host not in LOOPBACK_IPS:
                return JSONResponse(
                    status_code=403,
                    content={"ok": False, "message": "Rejected: Host header claimed localhost but the connection wasn't actually local."},
                )
        origin = request.headers.get("origin")
        if origin:
            origin_host = origin.split("://", 1)[-1].split(":")[0].split("/")[0]
            if origin_host not in ALLOWED_HOSTS:
                return JSONResponse(
                    status_code=403,
                    content={"ok": False, "message": "Rejected: Origin did not match this panel's host."},
                )
    return await call_next(request)


def _bootstrap_admin(db) -> None:
    """Creates the single admin account on first boot only - matches the
    plan's single-operator auth model. No-op if any user already exists,
    or if the env vars aren't set (e.g. during tests)."""
    username = os.environ.get("CONTROL_PANEL_ADMIN_USERNAME")
    password = os.environ.get("CONTROL_PANEL_ADMIN_PASSWORD")
    if not username or not password:
        return
    if db.query(User).count() > 0:
        return
    db.add(User(username=username, password_hash=hash_password(password), is_admin=True))
    db.commit()


def _bootstrap_service_key(db) -> None:
    """Upserts the health-check-loop's service API key by name, so
    rotating CONTROL_PANEL_SERVICE_API_KEY and recreating the container
    replaces the old hash instead of accumulating stale rows."""
    raw_key = os.environ.get("CONTROL_PANEL_SERVICE_API_KEY")
    if not raw_key:
        return
    key_hash = hash_api_key(raw_key)
    existing = db.query(ApiKey).filter(ApiKey.name == "healthcheck-cron").first()
    if existing is not None:
        existing.key_hash = key_hash
    else:
        db.add(ApiKey(name="healthcheck-cron", key_hash=key_hash))
    db.commit()


def _startup() -> None:
    """Runs at import time, not as an ASGI startup hook - app.py already
    does its own setup (docker.from_env(), ARR_APPS) at import time (see
    tests/conftest.py's cp_app fixture comments), and this avoids a real
    footgun: FastAPI's on_event/lifespan hooks only fire for a TestClient
    used as a context manager, which silently skipped table creation the
    first time this was written as an on_event hook."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _bootstrap_admin(db)
        _bootstrap_service_key(db)
    finally:
        db.close()


_startup()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


SERVICES_DIR = Path(__file__).parent / "services"


def _discover_routers() -> None:
    """Mounts every services/<name>/router.py's `router` - adding a new
    integration means adding a new directory, not editing this file.

    Each router's import is isolated: a bad import in one service (missing
    env var, broken dependency) logs and is skipped rather than taking down
    every other router along with it. Confirmed this matters in practice -
    a single dangling os.environ[...] read in a service's import chain
    previously crash-looped the whole container instead of just that
    service being unavailable."""
    for entry in sorted(SERVICES_DIR.iterdir()):
        if not entry.is_dir() or not (entry / "router.py").is_file():
            continue
        try:
            module = importlib.import_module(f"services.{entry.name}.router")
        except Exception as e:
            logger.error(f"_discover_routers: services/{entry.name}/router.py failed to import, skipping: {e}")
            continue
        router = getattr(module, "router", None)
        if router is not None:
            app.include_router(router)


_discover_routers()
logger.info("control-panel startup complete")

# Absolute path, not "static" - unlike app.py (which the test fixture
# chdir()s into control-panel/ before importing), this module's own test
# fixture (cp_main_app) does not chdir, so a relative path here 500s at
# import time under pytest even though it works fine from the real
# container's WORKDIR.
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

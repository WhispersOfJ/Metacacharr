"""Shared response-shaping helpers, ported 1:1 from app.py's own
now()/ok()/fail() (app.py:414-423) so every phase's ported routes return
the same envelope shape the existing frontend already expects."""
from datetime import datetime, timezone

from fastapi import HTTPException

from core.logging_config import logger


def now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")


def ok(message: str, **extra):
    return {"ok": True, "message": message, "time": now(), **extra}


def fail(message: str, status_code: int = 502):
    logger.error(message)
    raise HTTPException(status_code=status_code, detail={"ok": False, "message": message, "time": now()})

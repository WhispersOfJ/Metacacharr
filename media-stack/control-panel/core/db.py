"""SQLite engine/session for the evolved control-panel backend (Phase 1 of
.claude/plans/evolved-control-panel-backend.plan.md). DB file lives under
/data - the container's only writable volume (docker-compose.yml's
control-panel block: `./config/control-panel:/data`), same mount
settings_store.py already writes settings.json into.

Overridable via CONTROL_PANEL_DB_PATH so tests can point at a tmp path
instead of the real /data mount.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_PATH = os.environ.get("CONTROL_PANEL_DB_PATH", "/data/control-panel.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

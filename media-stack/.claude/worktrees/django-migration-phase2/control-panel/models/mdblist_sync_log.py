from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.db import Base


class MDBListSyncLog(Base):
    """One row per import-list (or scheduled sync-tick) run - surfaced by
    GET /api/mdblist/history, mirrors models/letterboxd_sync_log.py."""

    __tablename__ = "mdblist_sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_url: Mapped[str] = mapped_column(String, nullable=False, index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    radarr_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    radarr_already: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    radarr_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sonarr_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sonarr_already: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sonarr_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_detail: Mapped[str | None] = mapped_column(String, nullable=True)

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.db import Base


class LetterboxdSyncLog(Base):
    """One row per add-from-letterboxd-list (or scheduled sync-tick) run -
    surfaced by GET /api/arr/letterboxd/history so a silently degrading
    list (404s, zero match rate) is visible instead of only living in
    container logs."""

    __tablename__ = "letterboxd_sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_url: Mapped[str] = mapped_column(String, nullable=False, index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmatched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    already: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tv_crossover: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_detail: Mapped[str | None] = mapped_column(String, nullable=True)

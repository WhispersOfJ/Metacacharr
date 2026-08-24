from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.db import Base


class MDBListTrackedList(Base):
    """An MDBList list registered for the nightly diff-only sync
    (services/mdblist/sync.py, scripts/mdblist-sync.py) - mirrors
    models/letterboxd_tracked_list.py's shape. Row presence IS the
    registration - there's no separate enabled flag, untrack deletes
    the row."""

    __tablename__ = "mdblist_tracked_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    # Which Radarr instance (core.arr_client.RADARR_APPS) this list's movies
    # get added to. A single base instance since the 2026-08-18 anime merge.
    app: Mapped[str] = mapped_column(String, nullable=False, default="radarr")
    # Which Sonarr instance (core.arr_client.SONARR_APPS) this list's shows
    # get added to. A single base instance since the 2026-08-18 anime merge.
    sonarr_app: Mapped[str] = mapped_column(String, nullable=False, default="sonarr")
    radarr_root_folder: Mapped[str | None] = mapped_column(String, nullable=True)
    radarr_quality_profile: Mapped[str | None] = mapped_column(String, nullable=True)
    sonarr_root_folder: Mapped[str | None] = mapped_column(String, nullable=True)
    sonarr_quality_profile: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

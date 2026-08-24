from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.db import Base


class LetterboxdTrackedList(Base):
    """A Letterboxd list/watchlist registered for the nightly diff-only
    sync (services/letterboxd/sync.py, scripts/letterboxd-sync.py). Row
    presence IS the registration - there's no separate enabled flag,
    untrack deletes the row."""

    __tablename__ = "letterboxd_tracked_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    root_folder: Mapped[str | None] = mapped_column(String, nullable=True)
    quality_profile: Mapped[str | None] = mapped_column(String, nullable=True)
    # JSON-encoded dict[str, str] of {"letterboxd rating 1-10": "radarr quality profile name"} -
    # same JSON-in-a-string-column pattern as models/setting.py's value_json.
    rating_quality_map_json: Mapped[str | None] = mapped_column(String, nullable=True)
    tags_as_radarr_tags: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Which Radarr instance (core.arr_client.RADARR_APPS) this list's films
    # get added to. A single base instance since the 2026-08-18 anime merge.
    app: Mapped[str] = mapped_column(String, nullable=False, default="radarr")
    # Which Sonarr instance (core.arr_client.SONARR_APPS) sonarr_crossover
    # TV matches get added to. A single base instance since the 2026-08-18
    # anime merge.
    sonarr_app: Mapped[str] = mapped_column(String, nullable=False, default="sonarr")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

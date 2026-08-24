from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.db import Base


class LetterboxdTmdbCache(Base):
    """slug -> TMDb id, so a re-scraped list/watchlist doesn't re-fetch
    every film's own Letterboxd page just to re-derive an id that never
    changes. tmdb_id is nullable: a slug with no TMDb match (unmatched at
    scrape time) is cached too, so re-runs don't keep re-fetching known
    dead ends - see services/letterboxd/cache.py."""

    __tablename__ = "letterboxd_tmdb_cache"

    slug: Mapped[str] = mapped_column(String, primary_key=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_type: Mapped[str] = mapped_column(String, nullable=False, default="movie")
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

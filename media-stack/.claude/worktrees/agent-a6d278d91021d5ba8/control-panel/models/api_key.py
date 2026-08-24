from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.db import Base


class ApiKey(Base):
    """Service-account credential, checked as an alternative to a session
    cookie (see core/security.py's current_user_or_service) - lets the
    recurring health-check cron and stack-* scripts hit read-only routes
    without an interactive login. Only key_hash is stored, never the raw
    key - same discipline as password_hash on User."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    key_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

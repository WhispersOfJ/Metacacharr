from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class Setting(Base):
    """Key/value settings store, DB-backed replacement for
    settings_store.py's flat-JSON file. value_json holds a JSON-encoded
    value so a single table covers every setting's type (bool, int, dict)
    without a column per type."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value_json: Mapped[str] = mapped_column(String, nullable=False)

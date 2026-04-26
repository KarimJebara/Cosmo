from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from cosmo.models.base import Base, TimestampMixin


class ImportSource(Base, TimestampMixin):
    """Track CSV/bank import history for dedup and last-imported-at."""

    __tablename__ = "import_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users_v2.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # 'revolut_csv' | 'wise_csv' | 'n26_csv' | 'generic_csv'
    last_imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

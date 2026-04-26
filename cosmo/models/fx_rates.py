from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as Date

from sqlalchemy import Date as SADate
from sqlalchemy import DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from cosmo.models.base import Base


class FxRate(Base):
    """Snapshot of an FX rate for a specific date.

    ``rate`` represents how many units of ``quote_currency`` equal one unit of
    ``base_currency``. Sourced from ``frankfurter`` by default (ECB rates).
    """

    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint(
            "base_currency", "quote_currency", "date",
            name="uq_fx_pair_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    rate: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    date: Mapped[Date] = mapped_column(SADate, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

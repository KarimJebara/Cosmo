from __future__ import annotations

from datetime import date as Date
from typing import Optional

from sqlalchemy import Date as SADate, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from cosmo.models.base import Base, TimestampMixin


class Budget(Base, TimestampMixin):
    __tablename__ = "budgets_v2"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "category_id", "period", "starts_on",
            name="uq_budget_user_cat_period_start",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users_v2.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    period: Mapped[str] = mapped_column(String(8), default="monthly", nullable=False)
    # 'monthly' | 'weekly'
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    starts_on: Mapped[Date] = mapped_column(SADate, nullable=False)
    ends_on: Mapped[Optional[Date]] = mapped_column(SADate, nullable=True)

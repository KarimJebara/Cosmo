from __future__ import annotations

from datetime import date as Date

from sqlalchemy import Date as SADate
from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from cosmo.models.base import Base, TimestampMixin


class Transaction(Base, TimestampMixin):
    """Unified income/expense/transfer record.

    Invariants:
      - ``original_amount`` and ``original_currency`` are immutable after insert.
      - ``base_amount`` = ``original_amount * fx_rate_used``, snapshotted at the
        date the transaction occurred (not at import time, not "today").
      - For transfers, the paired transaction has the matching ``transfer_pair_id``
        and an opposite-signed ``original_amount``.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_tx_user_date", "user_id", "date"),
        Index("ix_tx_account_date", "account_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users_v2.id", ondelete="CASCADE"), index=True, nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[Date] = mapped_column(SADate, nullable=False)

    original_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    original_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    base_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    fx_rate_used: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)

    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    merchant_normalized: Mapped[str | None] = mapped_column(
        String(256), nullable=True, index=True
    )

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )

    type: Mapped[str] = mapped_column(String(8), nullable=False)
    # 'income' | 'expense' | 'transfer'

    transfer_pair_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(String(2048), nullable=True)

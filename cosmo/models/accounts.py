from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from cosmo.models.base import Base, TimestampMixin


class Account(Base, TimestampMixin):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users_v2.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    type: Mapped[str] = mapped_column(String(32), default="checking", nullable=False)
    opening_balance: Mapped[float] = mapped_column(
        Numeric(18, 4), default=0, nullable=False
    )
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

from __future__ import annotations

from collections.abc import Sequence
from datetime import date as Date

from sqlalchemy import select
from sqlalchemy.orm import Session

from cosmo.models import Budget


class BudgetRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def list_for_user(self, user_id: int) -> Sequence[Budget]:
        stmt = (
            select(Budget)
            .where(Budget.user_id == user_id)
            .order_by(Budget.id)
        )
        return self._s.execute(stmt).scalars().all()

    def get(self, budget_id: int, user_id: int) -> Budget | None:
        stmt = select(Budget).where(Budget.id == budget_id, Budget.user_id == user_id)
        return self._s.execute(stmt).scalar_one_or_none()

    def create(
        self,
        *,
        user_id: int,
        category_id: int,
        amount: float,
        currency: str,
        starts_on: Date,
        period: str = "monthly",
        ends_on: Date | None = None,
    ) -> Budget:
        budget = Budget(
            user_id=user_id,
            category_id=category_id,
            amount=amount,
            currency=currency,
            starts_on=starts_on,
            period=period,
            ends_on=ends_on,
        )
        self._s.add(budget)
        self._s.flush()
        return budget

    def delete(self, budget_id: int, user_id: int) -> bool:
        budget = self.get(budget_id, user_id)
        if budget is None:
            return False
        self._s.delete(budget)
        return True

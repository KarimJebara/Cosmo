from __future__ import annotations

from datetime import date as Date
from typing import Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from cosmo.models import Transaction


class TransactionRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, transaction_id: int, user_id: int) -> Transaction | None:
        stmt = select(Transaction).where(
            Transaction.id == transaction_id, Transaction.user_id == user_id
        )
        return self._s.execute(stmt).scalar_one_or_none()

    def list_for_user(
        self,
        user_id: int,
        *,
        type: str | None = None,
        start_date: Date | None = None,
        end_date: Date | None = None,
        account_id: int | None = None,
        limit: int | None = None,
    ) -> Sequence[Transaction]:
        clauses = [Transaction.user_id == user_id]
        if type is not None:
            clauses.append(Transaction.type == type)
        if start_date is not None:
            clauses.append(Transaction.date >= start_date)
        if end_date is not None:
            clauses.append(Transaction.date <= end_date)
        if account_id is not None:
            clauses.append(Transaction.account_id == account_id)
        stmt = (
            select(Transaction)
            .where(and_(*clauses))
            .order_by(Transaction.date.desc(), Transaction.id.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return self._s.execute(stmt).scalars().all()

    def create(
        self,
        *,
        user_id: int,
        account_id: int,
        date: Date,
        original_amount: float,
        original_currency: str,
        base_amount: float,
        type: str,
        description: str | None = None,
        merchant_normalized: str | None = None,
        category_id: int | None = None,
        fx_rate_used: float | None = None,
        notes: str | None = None,
        transfer_pair_id: int | None = None,
    ) -> Transaction:
        tx = Transaction(
            user_id=user_id,
            account_id=account_id,
            date=date,
            original_amount=original_amount,
            original_currency=original_currency,
            base_amount=base_amount,
            fx_rate_used=fx_rate_used,
            description=description,
            merchant_normalized=merchant_normalized,
            category_id=category_id,
            type=type,
            transfer_pair_id=transfer_pair_id,
            notes=notes,
        )
        self._s.add(tx)
        self._s.flush()
        return tx

    def update_category(
        self, transaction_id: int, user_id: int, category_id: int | None
    ) -> bool:
        tx = self.get(transaction_id, user_id)
        if tx is None:
            return False
        tx.category_id = category_id
        return True

    def delete(self, transaction_id: int, user_id: int) -> bool:
        tx = self.get(transaction_id, user_id)
        if tx is None:
            return False
        self._s.delete(tx)
        return True

    def total_by_category(
        self,
        user_id: int,
        *,
        type: str,
        start_date: Date | None = None,
        end_date: Date | None = None,
    ) -> Sequence[tuple[int | None, float]]:
        """Sum base_amount per category_id within a window."""
        clauses = [Transaction.user_id == user_id, Transaction.type == type]
        if start_date is not None:
            clauses.append(Transaction.date >= start_date)
        if end_date is not None:
            clauses.append(Transaction.date <= end_date)
        stmt = (
            select(Transaction.category_id, func.sum(Transaction.base_amount))
            .where(and_(*clauses))
            .group_by(Transaction.category_id)
        )
        return [(row[0], float(row[1] or 0.0)) for row in self._s.execute(stmt).all()]

    def total_for_user(
        self,
        user_id: int,
        *,
        type: str,
        start_date: Date | None = None,
        end_date: Date | None = None,
    ) -> float:
        clauses = [Transaction.user_id == user_id, Transaction.type == type]
        if start_date is not None:
            clauses.append(Transaction.date >= start_date)
        if end_date is not None:
            clauses.append(Transaction.date <= end_date)
        stmt = select(func.sum(Transaction.base_amount)).where(and_(*clauses))
        return float(self._s.execute(stmt).scalar() or 0.0)

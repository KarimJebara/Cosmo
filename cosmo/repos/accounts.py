from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from cosmo.models import Account


class AccountRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def list_for_user(self, user_id: int, *, include_archived: bool = False) -> Sequence[Account]:
        stmt = select(Account).where(Account.user_id == user_id)
        if not include_archived:
            stmt = stmt.where(Account.archived.is_(False))
        return self._s.execute(stmt.order_by(Account.id)).scalars().all()

    def get(self, account_id: int, user_id: int) -> Account | None:
        stmt = select(Account).where(Account.id == account_id, Account.user_id == user_id)
        return self._s.execute(stmt).scalar_one_or_none()

    def get_default_for_user(self, user_id: int) -> Account | None:
        """Return the user's first non-archived account.

        Used during the route migration where legacy code assumes a single
        implicit account per user. Phase 4 surfaces accounts in the UI
        and this method becomes redundant.
        """
        stmt = (
            select(Account)
            .where(Account.user_id == user_id, Account.archived.is_(False))
            .order_by(Account.id)
            .limit(1)
        )
        return self._s.execute(stmt).scalar_one_or_none()

    def create(
        self,
        *,
        user_id: int,
        name: str,
        currency: str,
        type: str = "checking",
        opening_balance: float = 0.0,
    ) -> Account:
        account = Account(
            user_id=user_id,
            name=name,
            currency=currency,
            type=type,
            opening_balance=opening_balance,
        )
        self._s.add(account)
        self._s.flush()
        return account

    def archive(self, account_id: int, user_id: int) -> bool:
        account = self.get(account_id, user_id)
        if account is None:
            return False
        account.archived = True
        return True

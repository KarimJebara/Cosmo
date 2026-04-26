"""Adapter bridging the legacy app.py route patterns to the v1 schema.

The original app stored transactions in two tables (``expenses`` and
``incomes``) and routed everything through a global ``DataManager``
singleton. This module exposes a small set of functions that route
handlers can call instead — each one opens a fresh SQLAlchemy session,
performs the work via the repositories, and returns either ORM rows or
lightweight view objects shaped like the legacy ones (so the existing
Jinja templates keep working unchanged).

This is intentionally a *thin* layer: it only knows about reads, single-row
mutations, and the fact that legacy code assumed one implicit account per
user. Phase 4 (accounts in the UI) will retire most of these helpers.
"""

from __future__ import annotations

from datetime import date as _date, datetime
from typing import Any, Iterable

from cosmo.db import get_session
from cosmo.repos import AccountRepo, BudgetRepo, CategoryRepo, TransactionRepo


# ---------------------------------------------------------------------------
# View objects
# ---------------------------------------------------------------------------


class _TransactionView:
    """Mirror the legacy ad-hoc ``type('Expense', (), entry)()`` shape.

    Templates and routes access these fields via ``getattr``, so any
    object that exposes them works. We add ``id`` so write paths can
    target a row without composite-key matching.
    """

    __slots__ = ("id", "date", "description", "category", "amount", "currency", "type")

    def __init__(
        self,
        *,
        id: int,
        date: str,
        description: str,
        category: str,
        amount: float,
        currency: str,
        type: str,
    ) -> None:
        self.id = id
        self.date = date
        self.description = description
        self.category = category
        self.amount = amount
        self.currency = currency
        self.type = type


class _BudgetView:
    __slots__ = ("id", "category", "limit")

    def __init__(self, *, id: int, category: str, limit: float) -> None:
        self.id = id
        self.category = category
        self.limit = limit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _isoformat(value: Any) -> str:
    if isinstance(value, (_date, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value or "")


def ensure_default_account(user_id: int) -> int:
    """Return the user's default account id, creating one in EUR if missing."""
    with get_session() as session:
        accounts = AccountRepo(session)
        existing = accounts.get_default_for_user(user_id)
        if existing is not None:
            return existing.id
        created = accounts.create(
            user_id=user_id, name="Default", currency="EUR"
        )
        return created.id


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def _txs_to_views(txs: Iterable, cat_lookup: dict[int, str]) -> list[_TransactionView]:
    out: list[_TransactionView] = []
    for tx in txs:
        out.append(
            _TransactionView(
                id=tx.id,
                date=_isoformat(tx.date),
                description=tx.description or "",
                category=cat_lookup.get(tx.category_id, "Uncategorized"),
                amount=float(tx.original_amount),
                currency=tx.original_currency,
                type=tx.type,
            )
        )
    return out


def get_expenses(user_id: int) -> list[_TransactionView]:
    with get_session() as session:
        cats = {c.id: c.name for c in CategoryRepo(session).list_for_user(user_id)}
        rows = TransactionRepo(session).list_for_user(user_id, type="expense")
        return _txs_to_views(rows, cats)


def get_incomes(user_id: int) -> list[_TransactionView]:
    with get_session() as session:
        cats = {c.id: c.name for c in CategoryRepo(session).list_for_user(user_id)}
        rows = TransactionRepo(session).list_for_user(user_id, type="income")
        return _txs_to_views(rows, cats)


def get_budgets(user_id: int) -> list[_BudgetView]:
    with get_session() as session:
        cats = {c.id: c.name for c in CategoryRepo(session).list_for_user(user_id)}
        rows = BudgetRepo(session).list_for_user(user_id)
        return [
            _BudgetView(
                id=b.id,
                category=cats.get(b.category_id, "Unknown"),
                limit=float(b.amount),
            )
            for b in rows
        ]


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> _date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def add_transaction(
    user_id: int,
    *,
    type: str,
    date: str,
    description: str,
    category: str,
    amount: float,
    currency: str = "EUR",
) -> int:
    """Create a transaction. Returns the new transaction id.

    ``base_amount`` is left equal to ``amount`` for non-EUR currencies until
    the Phase-2 FX service ships. ``fx_rate_used`` stays NULL so a follow-up
    backfill can recompute correct historical conversions.
    """
    if type not in ("income", "expense"):
        raise ValueError(f"Unsupported transaction type: {type!r}")

    parsed_date = _parse_date(date)
    with get_session() as session:
        account_id = AccountRepo(session).get_default_for_user(user_id)
        if account_id is None:
            account_id = AccountRepo(session).create(
                user_id=user_id, name="Default", currency="EUR"
            )
        account_id = account_id.id if hasattr(account_id, "id") else account_id

        category_obj = CategoryRepo(session).get_or_create(user_id, category, type)
        tx = TransactionRepo(session).create(
            user_id=user_id,
            account_id=account_id,
            date=parsed_date,
            original_amount=amount,
            original_currency=currency,
            base_amount=amount,
            type=type,
            description=description,
            category_id=category_obj.id,
        )
        return tx.id


def delete_transaction_by_natural_key(
    user_id: int,
    *,
    type: str,
    date: str,
    amount: float,
    description: str,
) -> bool:
    """Delete a transaction matched on the legacy composite key (date, amount, description).

    The legacy URLs encode the natural key in the path. Phase 5 replaces these
    routes with /transactions/<int:id> and this helper goes away.
    """
    parsed_date = _parse_date(date)
    with get_session() as session:
        txs = TransactionRepo(session)
        candidates = txs.list_for_user(user_id, type=type, start_date=parsed_date, end_date=parsed_date)
        for tx in candidates:
            if (
                (tx.description or "") == description
                and abs(float(tx.original_amount) - float(amount)) < 0.01
            ):
                return txs.delete(tx.id, user_id)
        return False


def change_category_by_natural_key(
    user_id: int,
    *,
    type: str,
    date: str,
    amount: float,
    description: str,
    new_category: str,
) -> tuple[int, str | None]:
    """Update the matched transaction *and* every other transaction with the same description.

    Returns ``(updated_count, merchant)`` so the caller can persist a merchant
    rule. Returns ``(0, None)`` if no row matched.
    """
    parsed_date = _parse_date(date)
    with get_session() as session:
        txs_repo = TransactionRepo(session)
        cats_repo = CategoryRepo(session)

        candidates = txs_repo.list_for_user(
            user_id, type=type, start_date=parsed_date, end_date=parsed_date
        )
        target = None
        for tx in candidates:
            if (
                (tx.description or "") == description
                and abs(float(tx.original_amount) - float(amount)) < 0.01
            ):
                target = tx
                break
        if target is None:
            return 0, None

        merchant = target.description or ""
        new_cat = cats_repo.get_or_create(user_id, new_category, type)

        # Update every transaction (of this type) sharing the description.
        all_of_type = txs_repo.list_for_user(user_id, type=type)
        updated = 0
        for tx in all_of_type:
            if (tx.description or "") == merchant:
                tx.category_id = new_cat.id
                updated += 1
        return updated, merchant


def set_budget(user_id: int, *, category: str, limit_amount: float) -> int:
    """Upsert a monthly budget for the named expense category. Returns the budget id."""
    today = datetime.now().date().replace(day=1)
    with get_session() as session:
        cats = CategoryRepo(session)
        budgets = BudgetRepo(session)
        cat = cats.get_or_create(user_id, category, "expense")
        # Hand-rolled upsert keyed on (user, category, period, starts_on)
        for existing in budgets.list_for_user(user_id):
            if existing.category_id == cat.id and existing.period == "monthly" and existing.starts_on == today:
                existing.amount = limit_amount
                return existing.id
        created = budgets.create(
            user_id=user_id,
            category_id=cat.id,
            amount=limit_amount,
            currency="EUR",
            starts_on=today,
            period="monthly",
        )
        return created.id


def delete_budget(user_id: int, budget_id: int) -> bool:
    with get_session() as session:
        return BudgetRepo(session).delete(budget_id, user_id)

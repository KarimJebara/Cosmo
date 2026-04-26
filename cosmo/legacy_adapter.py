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

from cosmo.categorize import (
    find_match,
    learn_from_correction,
    normalize_merchant,
    record_match_used,
)
from cosmo.db import get_session
from cosmo.fx.service import default_service as default_fx_service
from cosmo.repos import AccountRepo, BudgetRepo, CategoryRepo, TransactionRepo

# Until the user-level base_currency is exposed in the UI (Phase 4), every
# user reports in EUR. The FX service still snapshots historical rates by
# date, so this constant only changes the *reporting* currency, not what's
# stored on the transaction.
_DEFAULT_BASE_CURRENCY = "EUR"


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

    For non-base-currency transactions we look up the FX rate for the
    transaction date and snapshot ``base_amount`` and ``fx_rate_used``.
    If no rate is available (rare — providers down + no cached neighbour),
    we still create the transaction with ``base_amount = original`` and
    ``fx_rate_used = NULL`` so a later backfill can fix it.
    """
    if type not in ("income", "expense"):
        raise ValueError(f"Unsupported transaction type: {type!r}")

    parsed_date = _parse_date(date)
    base_currency = _DEFAULT_BASE_CURRENCY
    base_amount = float(amount)
    fx_rate_used: float | None = None

    if currency.upper() != base_currency.upper():
        rate = default_fx_service().get_rate(parsed_date, currency, base_currency)
        if rate is not None:
            base_amount = float(amount) * rate
            fx_rate_used = rate

    with get_session() as session:
        account = AccountRepo(session).get_default_for_user(user_id)
        if account is None:
            account = AccountRepo(session).create(
                user_id=user_id, name="Default", currency=base_currency
            )
        account_id = account.id

        category_obj = CategoryRepo(session).get_or_create(user_id, category, type)

        # Bookkeeping: if an existing merchant rule already maps this
        # description to the same category, count it as a hit. Otherwise
        # treat the user-supplied category as a teaching event and create /
        # update the rule. Both paths only run for expense/income (the only
        # types add_transaction accepts), and only when there's a description
        # worth learning from.
        if description:
            match = find_match(session, user_id, description)
            if match is not None and match.category_id == category_obj.id:
                record_match_used(session, match.rule_id)
            else:
                learn_from_correction(
                    session,
                    user_id=user_id,
                    raw_description=description,
                    category_id=category_obj.id,
                )

        tx = TransactionRepo(session).create(
            user_id=user_id,
            account_id=account_id,
            date=parsed_date,
            original_amount=amount,
            original_currency=currency,
            base_amount=base_amount,
            fx_rate_used=fx_rate_used,
            type=type,
            description=description,
            merchant_normalized=normalize_merchant(description) or None,
            category_id=category_obj.id,
        )
        return tx.id


def auto_categorize(user_id: int, description: str, type: str) -> str | None:
    """Look up the best-matching MerchantRule for ``description`` and return
    the category *name* the rule points at, or None if no rule matches.

    Replacement for the legacy ``merchant_mapper.auto_categorize_transaction``
    that read a global, exact-match-only JSON file. This is per-user, fuzzy,
    and falls back to None silently when nothing's a good fit.
    """
    if not description:
        return None
    with get_session() as session:
        match = find_match(session, user_id, description)
        if match is None:
            return None
        category = CategoryRepo(session).get(match.category_id, user_id)
        if category is None or category.type != type:
            # Rule points at a category that's been deleted, or to the wrong
            # type (e.g. an income-side rule applied to an expense).
            return None
        return category.name


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

        # Teach the categorizer: future transactions whose descriptor
        # normalizes to the same canonical form will auto-pick this category.
        learn_from_correction(
            session,
            user_id=user_id,
            raw_description=merchant,
            category_id=new_cat.id,
        )

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


# ---------------------------------------------------------------------------
# Merchant rules — read/delete for the /rules page
# ---------------------------------------------------------------------------


class _RuleView:
    __slots__ = (
        "id", "pattern", "match_type", "category_name",
        "source", "hit_count", "last_used_at_display",
    )

    def __init__(
        self,
        *,
        id: int,
        pattern: str,
        match_type: str,
        category_name: str,
        source: str,
        hit_count: int,
        last_used_at_display: str,
    ) -> None:
        self.id = id
        self.pattern = pattern
        self.match_type = match_type
        self.category_name = category_name
        self.source = source
        self.hit_count = hit_count
        self.last_used_at_display = last_used_at_display


def get_merchant_rules(user_id: int) -> list[_RuleView]:
    """List the user's MerchantRule rows decorated with category names for
    the /rules page. Sorted by hit_count desc (most-trusted first)."""
    from cosmo.repos import MerchantRuleRepo

    with get_session() as session:
        rules = MerchantRuleRepo(session).list_for_user(user_id)
        cats = {c.id: c.name for c in CategoryRepo(session).list_for_user(user_id)}

        def _fmt(when) -> str:
            if when is None:
                return ""
            return when.strftime("%Y-%m-%d %H:%M")

        return [
            _RuleView(
                id=r.id,
                pattern=r.pattern,
                match_type=r.match_type,
                category_name=cats.get(r.category_id, "Unknown"),
                source=r.source,
                hit_count=r.hit_count or 0,
                last_used_at_display=_fmt(r.last_used_at),
            )
            for r in rules
        ]


def delete_merchant_rule(user_id: int, rule_id: int) -> bool:
    from cosmo.repos import MerchantRuleRepo

    with get_session() as session:
        return MerchantRuleRepo(session).delete(rule_id, user_id)

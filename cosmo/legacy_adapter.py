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

import logging
from datetime import date as _date, datetime
from typing import Any, Iterable

logger = logging.getLogger(__name__)

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


def import_transactions(
    user_id: int,
    *,
    source: str,
    records,
) -> tuple[int, int]:
    """Bulk-insert imported transactions with per-currency account routing.

    For each ``ImportRecord`` we:

    1. Resolve the right account for ``record.currency``. If the user
       doesn't have an account in that currency yet, create one named
       ``f"{currency} Account"``. This is the moment cosmo's multi-currency
       story actually surfaces — a Revolut CSV with EUR/GBP/USD lines lands
       in three distinct accounts.
    2. Skip the row if a transaction already exists with the same date,
       description, and absolute amount on that account (idempotent
       re-imports are the norm, not the exception).
    3. Look up the historical FX rate for the transaction's date and
       compute base_amount.
    4. Run ``auto_categorize`` to suggest a category; fall back to "Other".
    5. Create the transaction with ``type='income'`` for positive amounts,
       ``'expense'`` otherwise.

    Returns ``(imported_count, skipped_duplicates_count)``.
    """
    base_currency = _DEFAULT_BASE_CURRENCY
    imported = 0
    skipped = 0

    # Pre-fetch every FX rate we'll need *before* opening the import write
    # session. Each ``get_rate`` call internally opens its own session to
    # check the cache and persist a new rate, and on SQLite that contends
    # with the long-running write transaction below.
    rate_lookup: dict[tuple, float | None] = {}
    fx_service = default_fx_service()
    for record in records:
        ccy = (record.currency or base_currency).upper()
        if ccy == base_currency.upper():
            continue
        key = (record.date, ccy, base_currency)
        if key not in rate_lookup:
            rate_lookup[key] = fx_service.get_rate(*key)

    with get_session() as session:
        accounts_repo = AccountRepo(session)
        cats_repo = CategoryRepo(session)
        txs_repo = TransactionRepo(session)

        # Cache (currency -> account_id) so we don't re-create per row.
        account_id_by_ccy: dict[str, int] = {}
        for acc in accounts_repo.list_for_user(user_id):
            account_id_by_ccy[acc.currency.upper()] = acc.id

        # Cache existing transaction signatures for fast dedup.
        existing_keys: set[tuple[int, str, str, float]] = set()
        for tx in txs_repo.list_for_user(user_id):
            existing_keys.add(
                (
                    tx.account_id,
                    tx.date.isoformat() if hasattr(tx.date, "isoformat") else str(tx.date),
                    tx.description or "",
                    abs(float(tx.original_amount)),
                )
            )

        for record in records:
            ccy = (record.currency or base_currency).upper()

            # Account routing.
            account_id = account_id_by_ccy.get(ccy)
            if account_id is None:
                # Use 'Default' as the name when the new account happens to
                # be in the base currency and no other account exists yet —
                # otherwise it'd be an awkward duplicate-named pair when
                # the user later creates an explicit base-currency account.
                if not account_id_by_ccy and ccy == base_currency.upper():
                    name = "Default"
                else:
                    name = f"{ccy} Account"
                created = accounts_repo.create(user_id=user_id, name=name, currency=ccy)
                account_id = created.id
                account_id_by_ccy[ccy] = account_id

            # Dedup.
            abs_amount = abs(float(record.amount))
            sig = (
                account_id,
                record.date.isoformat(),
                record.description or "",
                abs_amount,
            )
            if sig in existing_keys:
                skipped += 1
                continue
            existing_keys.add(sig)

            # FX conversion at the transaction's date (not today's rate),
            # using the rates pre-fetched above so we don't take a fresh
            # DB write lock per row.
            if ccy == base_currency.upper():
                base_amount = abs_amount
                fx_rate_used: float | None = None
            else:
                rate = rate_lookup.get((record.date, ccy, base_currency))
                if rate is not None:
                    base_amount = abs_amount * rate
                    fx_rate_used = rate
                else:
                    base_amount = abs_amount
                    fx_rate_used = None

            tx_type = "income" if record.amount >= 0 else "expense"

            # Categorization — find a learned rule first, fall back to 'Other'.
            category_name = None
            match = find_match(session, user_id, record.description)
            if match is not None:
                category = CategoryRepo(session).get(match.category_id, user_id)
                if category is not None and category.type == tx_type:
                    category_name = category.name
                    record_match_used(session, match.rule_id)
            if category_name is None:
                category_name = "Other"

            category_obj = cats_repo.get_or_create(user_id, category_name, tx_type)

            txs_repo.create(
                user_id=user_id,
                account_id=account_id,
                date=record.date,
                original_amount=abs_amount,
                original_currency=ccy,
                base_amount=base_amount,
                fx_rate_used=fx_rate_used,
                type=tx_type,
                description=record.description,
                merchant_normalized=normalize_merchant(record.description) or None,
                category_id=category_obj.id,
            )
            imported += 1

    logger.info(
        "Import complete: source=%s user=%s imported=%s skipped=%s",
        source, user_id, imported, skipped,
    )
    return imported, skipped


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


# ---------------------------------------------------------------------------
# Accounts — list / create / archive for the /accounts page
# ---------------------------------------------------------------------------


class _AccountView:
    __slots__ = (
        "id", "name", "currency", "type", "balance",
        "balance_in_base", "transaction_count", "archived",
    )

    def __init__(
        self,
        *,
        id: int,
        name: str,
        currency: str,
        type: str,
        balance: float,
        balance_in_base: float,
        transaction_count: int,
        archived: bool,
    ) -> None:
        self.id = id
        self.name = name
        self.currency = currency
        self.type = type
        self.balance = balance
        self.balance_in_base = balance_in_base
        self.transaction_count = transaction_count
        self.archived = archived


def get_accounts(user_id: int, *, include_archived: bool = False) -> list[_AccountView]:
    """List the user's accounts decorated with balance figures.

    ``balance`` is denominated in the account's own currency (sum of income
    minus expenses on that account). ``balance_in_base`` is the same total
    aggregated via each transaction's snapshotted base_amount, so it's
    historically accurate (no re-conversion at today's rate).
    """
    base_currency = _DEFAULT_BASE_CURRENCY

    with get_session() as session:
        accounts = AccountRepo(session).list_for_user(
            user_id, include_archived=include_archived
        )
        txs_repo = TransactionRepo(session)

        views: list[_AccountView] = []
        for acc in accounts:
            txs = txs_repo.list_for_user(user_id, account_id=acc.id)
            balance = float(acc.opening_balance or 0)
            balance_base = 0.0
            count = 0
            for tx in txs:
                count += 1
                if tx.type == "transfer":
                    # Transfers can be a credit or debit; rely on the sign
                    # the original_amount carries (we'll set it on creation).
                    sign = 1 if float(tx.original_amount) >= 0 else -1
                    balance += sign * abs(float(tx.original_amount))
                    balance_base += sign * abs(float(tx.base_amount))
                elif tx.type == "income":
                    balance += float(tx.original_amount)
                    balance_base += float(tx.base_amount)
                else:  # expense
                    balance -= float(tx.original_amount)
                    balance_base -= float(tx.base_amount)

            views.append(
                _AccountView(
                    id=acc.id,
                    name=acc.name,
                    currency=acc.currency,
                    type=acc.type,
                    balance=balance,
                    balance_in_base=balance_base,
                    transaction_count=count,
                    archived=bool(acc.archived),
                )
            )
        return views


def create_account(user_id: int, *, name: str, currency: str, type: str = "checking") -> int:
    """Create a new account for the user. Returns the new account id."""
    with get_session() as session:
        acc = AccountRepo(session).create(
            user_id=user_id,
            name=name,
            currency=currency.upper(),
            type=type,
        )
        return acc.id


def archive_account(user_id: int, account_id: int) -> bool:
    with get_session() as session:
        return AccountRepo(session).archive(account_id, user_id)


# ---------------------------------------------------------------------------
# Transfers — paired transactions between two accounts
# ---------------------------------------------------------------------------


def create_transfer(
    user_id: int,
    *,
    from_account_id: int,
    to_account_id: int,
    amount: float,
    date: str,
    description: str = "",
) -> tuple[int, int]:
    """Create a paired (debit, credit) transfer.

    Both rows have ``type='transfer'`` and share a ``transfer_pair_id``
    pointing at the *other* row. The debit row stores a negative
    ``original_amount``, the credit row a positive one — so a single SUM
    across all transfers nets to zero, and the balance computation in
    ``get_accounts`` walks each side correctly.

    When the two accounts are in different currencies, the credit side's
    amount is converted via the FX rate for ``date``.

    Returns ``(debit_id, credit_id)``.
    """
    if from_account_id == to_account_id:
        raise ValueError("Cannot transfer from an account to itself")
    if amount <= 0:
        raise ValueError("Transfer amount must be positive")

    parsed_date = _parse_date(date)
    base_currency = _DEFAULT_BASE_CURRENCY

    # Pull the account snapshot data we need before the session closes,
    # so we don't end up with detached instances downstream.
    with get_session() as session:
        accounts_repo = AccountRepo(session)
        from_acc = accounts_repo.get(from_account_id, user_id)
        to_acc = accounts_repo.get(to_account_id, user_id)
        if from_acc is None or to_acc is None:
            raise ValueError("One or both accounts not found")
        from_ccy = from_acc.currency.upper()
        to_ccy = to_acc.currency.upper()
        from_name = from_acc.name
        to_name = to_acc.name

    fx_service = default_fx_service()

    def _resolve(amount_, ccy_):
        if ccy_ == base_currency.upper():
            return float(amount_), None
        rate = fx_service.get_rate(parsed_date, ccy_, base_currency)
        if rate is None:
            return float(amount_), None
        return float(amount_) * rate, rate

    from_base, from_rate = _resolve(amount, from_ccy)

    if from_ccy == to_ccy:
        to_amount = float(amount)
    else:
        # Cross-currency: convert via the base currency at the snapshot date.
        # Pre-fetch each leg, then derive to_amount from base.
        to_rate_to_base = (
            1.0 if to_ccy == base_currency.upper()
            else fx_service.get_rate(parsed_date, to_ccy, base_currency)
        )
        if to_rate_to_base is None or to_rate_to_base == 0:
            # Fall back to face value — better to record the transfer than drop it.
            to_amount = float(amount)
        else:
            to_amount = from_base / to_rate_to_base

    to_base, to_rate = _resolve(to_amount, to_ccy)

    with get_session() as session:
        txs_repo = TransactionRepo(session)

        debit = txs_repo.create(
            user_id=user_id,
            account_id=from_account_id,
            date=parsed_date,
            original_amount=-abs(amount),
            original_currency=from_ccy,
            base_amount=-abs(from_base),
            fx_rate_used=from_rate,
            type="transfer",
            description=description or f"Transfer to {to_name}",
        )
        credit = txs_repo.create(
            user_id=user_id,
            account_id=to_account_id,
            date=parsed_date,
            original_amount=abs(to_amount),
            original_currency=to_ccy,
            base_amount=abs(to_base),
            fx_rate_used=to_rate,
            type="transfer",
            description=description or f"Transfer from {from_name}",
            transfer_pair_id=debit.id,
        )
        # Backfill the link on the debit side now that we have credit.id.
        debit.transfer_pair_id = credit.id

        return debit.id, credit.id

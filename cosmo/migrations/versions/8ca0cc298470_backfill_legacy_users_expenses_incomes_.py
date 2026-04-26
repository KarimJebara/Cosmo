"""Backfill legacy users/expenses/incomes/budgets into the v1 schema.

For each legacy user this revision:

1. Copies the row into ``users_v2`` (preserving id so FKs from any code that
   already references the old id keep working). ``base_currency`` defaults to
   'EUR'.
2. Creates a single default account per user in EUR (legacy data has no
   account concept — everything was implicitly one bucket).
3. Walks the user's distinct ``(category, type)`` strings across expenses and
   incomes and creates ``categories`` rows.
4. Copies expenses → transactions (type='expense') and incomes →
   transactions (type='income'). For non-EUR rows ``base_amount`` is left
   equal to the original amount and ``fx_rate_used`` is NULL — the FX
   service will recompute correct historical rates in a Phase-2 backfill
   once it can pull rates by date.
5. Copies budgets → ``budgets_v2`` keyed on the Category created above,
   defaulting to ``period='monthly'`` with ``starts_on`` = first day of the
   current month.

Idempotent: re-running is a no-op once data is in the v1 tables.
This revision is data-only; no schema changes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8ca0cc298470"
down_revision: str | None = "72ec70b2de44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _legacy_tables_present(conn) -> bool:
    rows = conn.execute(
        sa.text(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('users', 'expenses', 'incomes', 'budgets')"
        )
    ).fetchall()
    return len(rows) >= 1


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def upgrade() -> None:
    bind = op.get_bind()
    if not _legacy_tables_present(bind):
        return  # Fresh DB — nothing to backfill.

    now = datetime.now(UTC)
    today = date.today()
    month_start = today.replace(day=1)

    legacy_users = bind.execute(
        sa.text("SELECT id, username, password_hash, created_at FROM users")
    ).fetchall()

    for user in legacy_users:
        user_id = user.id

        # Skip if already migrated (idempotent).
        already = bind.execute(
            sa.text("SELECT 1 FROM users_v2 WHERE id = :uid"), {"uid": user_id}
        ).fetchone()
        if already:
            continue

        # 1. Mirror user row.
        bind.execute(
            sa.text(
                "INSERT INTO users_v2 (id, username, password_hash, base_currency, created_at) "
                "VALUES (:id, :username, :pw, :ccy, :ts)"
            ),
            {
                "id": user_id,
                "username": user.username,
                "pw": user.password_hash,
                "ccy": "EUR",
                "ts": user.created_at or now,
            },
        )

        # 2. Default account.
        result = bind.execute(
            sa.text(
                "INSERT INTO accounts (user_id, name, currency, type, opening_balance, "
                "archived, created_at, updated_at) "
                "VALUES (:uid, :name, :ccy, :type, 0, 0, :ts, :ts)"
            ),
            {"uid": user_id, "name": "Default", "ccy": "EUR", "type": "checking", "ts": now},
        )
        account_id = result.lastrowid

        # 3. Build category lookup (name, type) -> id.
        # Access columns positionally — Row attribute access across UNION
        # queries is unreliable on some drivers.
        cat_lookup: dict[tuple[str, str], int] = {}
        seen_categories = bind.execute(
            sa.text(
                "SELECT DISTINCT category, 'expense' AS t FROM expenses WHERE user_id = :uid "
                "UNION "
                "SELECT DISTINCT category, 'income' AS t FROM incomes WHERE user_id = :uid"
            ),
            {"uid": user_id},
        ).fetchall()
        for row in seen_categories:
            cat_name = row[0]
            cat_type = row[1]
            res = bind.execute(
                sa.text(
                    "INSERT INTO categories (user_id, name, type, archived) "
                    "VALUES (:uid, :name, :type, 0)"
                ),
                {"uid": user_id, "name": cat_name, "type": cat_type},
            )
            cat_lookup[(cat_name, cat_type)] = res.lastrowid

        # 4a. Expenses → transactions.
        for row in bind.execute(
            sa.text(
                "SELECT date, description, category, amount, currency, created_at "
                "FROM expenses WHERE user_id = :uid"
            ),
            {"uid": user_id},
        ).fetchall():
            tx_date = _parse_date(row.date) or today
            cat_id = cat_lookup.get((row.category, "expense"))
            ccy = row.currency or "EUR"
            bind.execute(
                sa.text(
                    "INSERT INTO transactions (user_id, account_id, date, original_amount, "
                    "original_currency, base_amount, fx_rate_used, description, "
                    "category_id, type, created_at, updated_at) "
                    "VALUES (:uid, :aid, :dt, :amt, :occy, :amt, NULL, :desc, :cat, "
                    "'expense', :ts, :ts)"
                ),
                {
                    "uid": user_id,
                    "aid": account_id,
                    "dt": tx_date,
                    "amt": row.amount,
                    "occy": ccy,
                    "desc": row.description,
                    "cat": cat_id,
                    "ts": row.created_at or now,
                },
            )

        # 4b. Incomes → transactions.
        for row in bind.execute(
            sa.text(
                "SELECT date, description, category, amount, currency, created_at "
                "FROM incomes WHERE user_id = :uid"
            ),
            {"uid": user_id},
        ).fetchall():
            tx_date = _parse_date(row.date) or today
            cat_id = cat_lookup.get((row.category, "income"))
            ccy = row.currency or "EUR"
            bind.execute(
                sa.text(
                    "INSERT INTO transactions (user_id, account_id, date, original_amount, "
                    "original_currency, base_amount, fx_rate_used, description, "
                    "category_id, type, created_at, updated_at) "
                    "VALUES (:uid, :aid, :dt, :amt, :occy, :amt, NULL, :desc, :cat, "
                    "'income', :ts, :ts)"
                ),
                {
                    "uid": user_id,
                    "aid": account_id,
                    "dt": tx_date,
                    "amt": row.amount,
                    "occy": ccy,
                    "desc": row.description,
                    "cat": cat_id,
                    "ts": row.created_at or now,
                },
            )

        # 5. Budgets → budgets_v2.
        for row in bind.execute(
            sa.text(
                "SELECT category, limit_amount FROM budgets WHERE user_id = :uid"
            ),
            {"uid": user_id},
        ).fetchall():
            cat_id = cat_lookup.get((row.category, "expense"))
            if cat_id is None:
                # Legacy budgets reference categories that may not have any
                # transactions; create a stub category so the budget survives.
                res = bind.execute(
                    sa.text(
                        "INSERT INTO categories (user_id, name, type, archived) "
                        "VALUES (:uid, :name, 'expense', 0)"
                    ),
                    {"uid": user_id, "name": row.category},
                )
                cat_id = res.lastrowid
                cat_lookup[(row.category, "expense")] = cat_id

            bind.execute(
                sa.text(
                    "INSERT INTO budgets_v2 (user_id, category_id, period, amount, currency, "
                    "starts_on, ends_on, created_at, updated_at) "
                    "VALUES (:uid, :cat, 'monthly', :amt, 'EUR', :start, NULL, :ts, :ts)"
                ),
                {
                    "uid": user_id,
                    "cat": cat_id,
                    "amt": row.limit_amount,
                    "start": month_start,
                    "ts": now,
                },
            )


def downgrade() -> None:
    """Wipe all data from v1 tables (the legacy tables are untouched)."""
    bind = op.get_bind()
    for table in (
        "transactions",
        "budgets_v2",
        "merchant_rules",
        "categories",
        "import_sources",
        "accounts",
        "users_v2",
    ):
        bind.execute(sa.text(f"DELETE FROM {table}"))

"""Repository unit tests against an in-memory SQLite.

These intentionally don't go through Flask — repos are pure data-access
classes and shouldn't need the web app.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from cosmo.models import Base, User
from cosmo.repos import AccountRepo, BudgetRepo, CategoryRepo, TransactionRepo


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _r):
        c = dbapi_conn.cursor()
        c.execute("PRAGMA foreign_keys = ON")
        c.close()

    Base.metadata.create_all(engine)
    s = Session(engine, future=True)
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def alice(session):
    user = User(username="alice", password_hash="x", base_currency="EUR")
    session.add(user)
    session.flush()
    return user


def test_account_repo_create_and_list(session, alice):
    repo = AccountRepo(session)
    repo.create(user_id=alice.id, name="EUR Main", currency="EUR")
    repo.create(user_id=alice.id, name="GBP Travel", currency="GBP")
    accounts = repo.list_for_user(alice.id)
    assert [a.name for a in accounts] == ["EUR Main", "GBP Travel"]
    assert repo.get_default_for_user(alice.id).name == "EUR Main"


def test_account_repo_archive_excludes_from_default_list(session, alice):
    repo = AccountRepo(session)
    a1 = repo.create(user_id=alice.id, name="Old", currency="EUR")
    repo.create(user_id=alice.id, name="New", currency="EUR")
    assert repo.archive(a1.id, alice.id) is True
    assert [a.name for a in repo.list_for_user(alice.id)] == ["New"]
    assert len(repo.list_for_user(alice.id, include_archived=True)) == 2


def test_category_get_or_create_is_idempotent(session, alice):
    repo = CategoryRepo(session)
    c1 = repo.get_or_create(alice.id, "Groceries", "expense")
    c2 = repo.get_or_create(alice.id, "Groceries", "expense")
    assert c1.id == c2.id
    # Same name but different type → distinct row
    c3 = repo.get_or_create(alice.id, "Groceries", "income")
    assert c3.id != c1.id


def test_transaction_repo_create_and_query(session, alice):
    accounts = AccountRepo(session)
    cats = CategoryRepo(session)
    txs = TransactionRepo(session)

    acc = accounts.create(user_id=alice.id, name="Default", currency="EUR")
    groc = cats.get_or_create(alice.id, "Groceries", "expense")

    txs.create(
        user_id=alice.id, account_id=acc.id, date=date(2026, 4, 10),
        original_amount=10.0, original_currency="EUR", base_amount=10.0,
        type="expense", description="Tesco", category_id=groc.id,
    )
    txs.create(
        user_id=alice.id, account_id=acc.id, date=date(2026, 4, 12),
        original_amount=20.0, original_currency="EUR", base_amount=20.0,
        type="expense", description="Cafe", category_id=groc.id,
    )

    expense_total = txs.total_for_user(
        alice.id, type="expense", start_date=date(2026, 4, 1), end_date=date(2026, 4, 30)
    )
    assert expense_total == 30.0

    by_cat = dict(
        txs.total_by_category(
            alice.id, type="expense",
            start_date=date(2026, 4, 1), end_date=date(2026, 4, 30),
        )
    )
    assert by_cat[groc.id] == 30.0


def test_transaction_repo_update_category_and_delete(session, alice):
    accounts = AccountRepo(session)
    cats = CategoryRepo(session)
    txs = TransactionRepo(session)
    acc = accounts.create(user_id=alice.id, name="Default", currency="EUR")
    old_cat = cats.get_or_create(alice.id, "Misc", "expense")
    new_cat = cats.get_or_create(alice.id, "Groceries", "expense")
    tx = txs.create(
        user_id=alice.id, account_id=acc.id, date=date(2026, 4, 10),
        original_amount=10.0, original_currency="EUR", base_amount=10.0,
        type="expense", description="Tesco", category_id=old_cat.id,
    )

    assert txs.update_category(tx.id, alice.id, new_cat.id) is True
    assert txs.get(tx.id, alice.id).category_id == new_cat.id

    assert txs.delete(tx.id, alice.id) is True
    assert txs.get(tx.id, alice.id) is None


def test_repo_isolates_users(session):
    """User A must never read/write user B's rows even via id collisions."""
    cats = CategoryRepo(session)
    a = User(username="a", password_hash="x", base_currency="EUR")
    b = User(username="b", password_hash="x", base_currency="EUR")
    session.add_all([a, b])
    session.flush()

    cat_a = cats.get_or_create(a.id, "Groceries", "expense")
    cat_b = cats.get_or_create(b.id, "Groceries", "expense")
    assert cat_a.id != cat_b.id  # distinct rows despite identical names

    # b cannot fetch a's category by id
    assert cats.get(cat_a.id, b.id) is None
    assert cats.get(cat_a.id, a.id) is not None


def test_budget_repo_create_list_delete(session, alice):
    cats = CategoryRepo(session)
    budgets = BudgetRepo(session)
    cat = cats.get_or_create(alice.id, "Groceries", "expense")
    b = budgets.create(
        user_id=alice.id, category_id=cat.id, amount=400.0,
        currency="EUR", starts_on=date(2026, 4, 1),
    )
    assert [x.id for x in budgets.list_for_user(alice.id)] == [b.id]
    assert budgets.delete(b.id, alice.id) is True
    assert budgets.list_for_user(alice.id) == []

"""Tests for transfers between accounts."""

from __future__ import annotations

import database
from cosmo import legacy_adapter
from cosmo.fx.service import FxService, set_default_service


class _StubProvider:
    name = "stub"

    def fetch_rate(self, on_date, base, quote):
        if base == "GBP" and quote == "EUR":
            return 1.17
        if base == "EUR" and quote == "GBP":
            return 0.85
        if base == quote:
            return 1.0
        return None


def teardown_function(_func):
    set_default_service(None)


def _make_two_accounts(authenticated_client):
    """Returns (eur_account_id, gbp_account_id)."""
    authenticated_client.post(
        '/accounts',
        data={'name': 'GBP Travel', 'currency': 'GBP', 'type': 'checking'},
    )
    with database.get_db() as conn:
        rows = conn.execute(
            "SELECT id, currency FROM accounts WHERE user_id = 1 ORDER BY id"
        ).fetchall()
    eur_id = next(r['id'] for r in rows if r['currency'] == 'EUR')
    gbp_id = next(r['id'] for r in rows if r['currency'] == 'GBP')
    return eur_id, gbp_id


def test_transfer_page_warns_with_one_account(authenticated_client):
    response = authenticated_client.get('/transfer')
    assert response.status_code == 200
    assert b'You need at least two accounts' in response.data


def test_same_currency_transfer(authenticated_client):
    """EUR→EUR transfer: both legs same amount, paired."""
    set_default_service(FxService(providers=(_StubProvider(),)))
    authenticated_client.post(
        '/accounts',
        data={'name': 'Savings', 'currency': 'EUR', 'type': 'savings'},
    )

    with database.get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM accounts WHERE user_id = 1 ORDER BY id"
        ).fetchall()
    a, b = rows[0]['id'], rows[1]['id']

    debit_id, credit_id = legacy_adapter.create_transfer(
        user_id=1,
        from_account_id=a, to_account_id=b,
        amount=100.0, date='2026-04-10', description='Move savings',
    )
    assert debit_id != credit_id

    with database.get_db() as conn:
        rows = conn.execute(
            "SELECT id, account_id, original_amount, type, transfer_pair_id "
            "FROM transactions ORDER BY id"
        ).fetchall()
    assert len(rows) == 2
    assert all(r['type'] == 'transfer' for r in rows)
    assert rows[0]['original_amount'] == -100.0
    assert rows[1]['original_amount'] == 100.0
    assert rows[0]['transfer_pair_id'] == rows[1]['id']
    assert rows[1]['transfer_pair_id'] == rows[0]['id']


def test_cross_currency_transfer_uses_fx(authenticated_client):
    """EUR→GBP transfer: GBP leg amount is FX-converted from the EUR amount."""
    set_default_service(FxService(providers=(_StubProvider(),)))
    eur_id, gbp_id = _make_two_accounts(authenticated_client)

    legacy_adapter.create_transfer(
        user_id=1,
        from_account_id=eur_id, to_account_id=gbp_id,
        amount=117.0, date='2026-04-10', description='Top up travel',
    )

    with database.get_db() as conn:
        rows = conn.execute(
            "SELECT account_id, original_amount, original_currency "
            "FROM transactions ORDER BY id"
        ).fetchall()
    debit = next(r for r in rows if r['account_id'] == eur_id)
    credit = next(r for r in rows if r['account_id'] == gbp_id)
    assert debit['original_currency'] == 'EUR'
    assert debit['original_amount'] == -117.0
    assert credit['original_currency'] == 'GBP'
    # 117 EUR / 1.17 (GBP→EUR) = 100 GBP
    assert abs(credit['original_amount'] - 100.0) < 0.01


def test_transfer_to_self_rejected(authenticated_client):
    set_default_service(FxService(providers=(_StubProvider(),)))
    with database.get_db() as conn:
        row = conn.execute(
            "SELECT id FROM accounts WHERE user_id = 1 LIMIT 1"
        ).fetchone()
    aid = row['id']

    import pytest
    with pytest.raises(ValueError, match="itself"):
        legacy_adapter.create_transfer(
            user_id=1, from_account_id=aid, to_account_id=aid,
            amount=10.0, date='2026-04-10',
        )


def test_transfer_excluded_from_dashboard_totals(authenticated_client):
    """Transfers must not inflate income or expense totals."""
    set_default_service(FxService(providers=(_StubProvider(),)))
    eur_id, gbp_id = _make_two_accounts(authenticated_client)

    # Add a real income + a real expense
    authenticated_client.post('/income', data={
        'date': '2026-04-01', 'category': 'Salary',
        'description': 'Salary', 'amount': '3000', 'currency': 'EUR',
    })
    authenticated_client.post('/expenses', data={
        'date': '2026-04-05', 'category': 'Food',
        'description': 'Tesco', 'amount': '50', 'currency': 'EUR',
    })

    # Transfer should not show up in either total
    legacy_adapter.create_transfer(
        user_id=1, from_account_id=eur_id, to_account_id=gbp_id,
        amount=200.0, date='2026-04-10',
    )

    with database.get_db() as conn:
        income_total = conn.execute(
            "SELECT COALESCE(SUM(base_amount), 0) FROM transactions "
            "WHERE user_id = 1 AND type = 'income'"
        ).fetchone()[0]
        expense_total = conn.execute(
            "SELECT COALESCE(SUM(base_amount), 0) FROM transactions "
            "WHERE user_id = 1 AND type = 'expense'"
        ).fetchone()[0]
    assert float(income_total) == 3000.0
    assert float(expense_total) == 50.0

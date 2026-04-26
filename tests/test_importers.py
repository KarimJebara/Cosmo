"""Tests for the importer framework — multi-account routing on mixed-currency CSV."""

from __future__ import annotations

import sqlite3

import database
from cosmo import legacy_adapter
from cosmo.fx.service import FxService, set_default_service
from cosmo.importers import get_importer


class _StubProvider:
    """Returns a fixed rate so tests are deterministic."""
    name = "stub"

    def __init__(self, rates):
        self._rates = rates  # dict[(base,quote), float]

    def fetch_rate(self, on_date, base, quote):
        return self._rates.get((base.upper(), quote.upper()))


def _setup_fx_stub():
    set_default_service(
        FxService(
            providers=(
                _StubProvider({
                    ("USD", "EUR"): 0.92,
                    ("GBP", "EUR"): 1.17,
                }),
            )
        )
    )


def teardown_function(_func):
    """Reset the FX service singleton between tests so the real one comes back."""
    set_default_service(None)


REVOLUT_MIXED_CSV = """\
Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance
CARD_PAYMENT,Current,2026-04-10 12:30:00,2026-04-10 12:30:00,Tesco Stores 1234,-12.50,0,GBP,COMPLETED,500.00
CARD_PAYMENT,Current,2026-04-11 09:15:00,2026-04-11 09:15:00,NYC Coffee,-4.50,0,USD,COMPLETED,200.00
TRANSFER,Current,2026-04-01 00:00:00,2026-04-01 00:00:00,Salary,3000.00,0,EUR,COMPLETED,3500.00
CARD_PAYMENT,Current,2026-04-12 18:00:00,2026-04-12 18:00:00,Albert Heijn,-25.30,0,EUR,COMPLETED,3474.70
"""


def test_revolut_importer_parses_canonical_records():
    importer = get_importer('revolut')
    records = list(importer.parse(REVOLUT_MIXED_CSV))

    assert len(records) == 4
    currencies = {r.currency for r in records}
    assert currencies == {"GBP", "USD", "EUR"}

    # Amounts retain their bank-supplied sign (positive=income).
    salary = next(r for r in records if r.description == "Salary")
    assert salary.amount == 3000.00
    coffee = next(r for r in records if r.description == "NYC Coffee")
    assert coffee.amount == -4.50


def test_import_creates_account_per_currency(authenticated_client):
    """Mixed-currency Revolut CSV must spawn one account per currency
    and route each transaction to the right one."""
    _setup_fx_stub()

    importer = get_importer('revolut')
    records = list(importer.parse(REVOLUT_MIXED_CSV))

    # The authenticated_client fixture already created user_id=1 + a default
    # EUR account. We expect import to add GBP and USD accounts.
    imported, skipped = legacy_adapter.import_transactions(
        user_id=1, source='revolut', records=records,
    )
    assert imported == 4
    assert skipped == 0

    with database.get_db() as conn:
        accounts = conn.execute(
            "SELECT name, currency FROM accounts WHERE user_id = 1 ORDER BY currency"
        ).fetchall()
    currencies = {a['currency'] for a in accounts}
    assert currencies == {"EUR", "GBP", "USD"}


def test_import_uses_historical_fx_for_base_amount(authenticated_client):
    _setup_fx_stub()

    importer = get_importer('revolut')
    records = list(importer.parse(REVOLUT_MIXED_CSV))
    legacy_adapter.import_transactions(user_id=1, source='revolut', records=records)

    with database.get_db() as conn:
        usd_tx = conn.execute(
            "SELECT original_amount, base_amount, fx_rate_used "
            "FROM transactions WHERE original_currency = 'USD'"
        ).fetchone()
    assert usd_tx is not None
    # 4.50 USD * 0.92 = 4.14 EUR
    assert abs(float(usd_tx['base_amount']) - 4.14) < 0.001
    assert abs(float(usd_tx['fx_rate_used']) - 0.92) < 0.001


def test_import_dedups_on_second_run(authenticated_client):
    _setup_fx_stub()
    importer = get_importer('revolut')
    records = list(importer.parse(REVOLUT_MIXED_CSV))

    first_imported, _ = legacy_adapter.import_transactions(
        user_id=1, source='revolut', records=records,
    )
    second_imported, second_skipped = legacy_adapter.import_transactions(
        user_id=1, source='revolut', records=records,
    )
    assert first_imported == 4
    assert second_imported == 0
    assert second_skipped == 4


def test_revolut_route_smoke(authenticated_client):
    """End-to-end: POST to /revolut_import with the CSV blob."""
    _setup_fx_stub()
    response = authenticated_client.post(
        '/revolut_import',
        data={'revolut_csv': (
            __import__('io').BytesIO(REVOLUT_MIXED_CSV.encode('utf-8')),
            'statement.csv',
        )},
        follow_redirects=True,
        content_type='multipart/form-data',
    )
    assert response.status_code == 200
    assert b'Successfully imported 4' in response.data

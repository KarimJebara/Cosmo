"""Unit tests for cosmo.analytics.insights — pure functions over canned txs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from cosmo.analytics.insights import (
    category_drift,
    cumulative_balance_series,
    currency_exposure,
    detect_subscriptions,
    saving_rate,
    spend_by_account,
    top_merchants,
)


# Minimal test double matching the legacy_adapter._TransactionView shape.
@dataclass
class FakeTx:
    date: str
    amount: float
    base_amount: float
    currency: str = "EUR"
    type: str = "expense"
    description: str = ""
    category: str = "Other"
    account_id: int = 1
    merchant_normalized: str | None = None


@dataclass
class FakeAccount:
    id: int
    name: str
    currency: str


def _today_minus(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# currency_exposure
# ---------------------------------------------------------------------------


def test_currency_exposure_groups_and_sorts():
    txs = [
        FakeTx(date="2026-04-01", amount=1000, base_amount=1000, currency="EUR"),
        FakeTx(date="2026-04-02", amount=500, base_amount=575, currency="GBP"),
        FakeTx(date="2026-04-03", amount=300, base_amount=345, currency="GBP"),
        FakeTx(date="2026-04-04", amount=200, base_amount=180, currency="USD"),
    ]
    out = currency_exposure(txs)

    assert [s.currency for s in out] == ["EUR", "GBP", "USD"]
    assert out[0].base_total == 1000.0
    assert out[1].native_total == 800.0  # 500 + 300
    assert out[1].base_total == 920.0
    assert sum(s.share_pct for s in out) == pytest.approx(100.0, abs=0.5)


def test_currency_exposure_empty():
    assert currency_exposure([]) == []


# ---------------------------------------------------------------------------
# spend_by_account
# ---------------------------------------------------------------------------


def test_spend_by_account_aggregates():
    accounts = [
        FakeAccount(id=1, name="Default", currency="EUR"),
        FakeAccount(id=2, name="UK Flat", currency="GBP"),
        FakeAccount(id=3, name="Idle", currency="USD"),
    ]
    txs = [
        FakeTx(date="2026-04-01", amount=100, base_amount=100, account_id=1),
        FakeTx(date="2026-04-02", amount=50, base_amount=50, account_id=1),
        FakeTx(date="2026-04-03", amount=200, base_amount=230, account_id=2),
    ]
    out = spend_by_account(txs, accounts)

    assert out[0].name == "UK Flat"
    assert out[0].base_total == 230.0
    assert out[1].name == "Default"
    assert out[1].transaction_count == 2
    assert out[2].name == "Idle"
    assert out[2].base_total == 0.0


# ---------------------------------------------------------------------------
# detect_subscriptions
# ---------------------------------------------------------------------------


def test_detect_subscriptions_finds_monthly_with_stable_amount():
    # Three monthly Netflix charges within 5% of each other.
    txs = [
        FakeTx(
            date=_today_minus(d),
            amount=12.99,
            base_amount=12.99,
            description="Netflix",
            merchant_normalized="NETFLIX",
        )
        for d in (3, 33, 63)
    ]
    out = detect_subscriptions(txs)
    assert len(out) == 1
    assert out[0].merchant == "NETFLIX"
    assert out[0].occurrences == 3
    assert 12 <= out[0].monthly_eur <= 14


def test_detect_subscriptions_rejects_unstable_amounts():
    # Amounts vary by 50% — not a subscription.
    txs = [
        FakeTx(date=_today_minus(d), amount=a, base_amount=a, description="Restaurant")
        for d, a in [(3, 20), (33, 30), (63, 45)]
    ]
    assert detect_subscriptions(txs) == []


def test_detect_subscriptions_requires_min_occurrences():
    txs = [
        FakeTx(date=_today_minus(d), amount=10, base_amount=10, description="Spotify")
        for d in (3, 33)
    ]
    assert detect_subscriptions(txs, min_occurrences=3) == []


# ---------------------------------------------------------------------------
# cumulative_balance_series
# ---------------------------------------------------------------------------


def test_cumulative_balance_series_walks_forward():
    incomes = [
        FakeTx(date="2026-04-01", amount=4000, base_amount=4000, type="income"),
    ]
    expenses = [
        FakeTx(date="2026-04-05", amount=1000, base_amount=1000),
        FakeTx(date="2026-04-10", amount=500, base_amount=500),
    ]
    out = cumulative_balance_series(incomes, expenses, starting_balance=0)

    assert [p.date for p in out] == ["2026-04-01", "2026-04-05", "2026-04-10"]
    assert [p.balance for p in out] == [4000, 3000, 2500]


def test_cumulative_balance_series_empty():
    assert cumulative_balance_series([], []) == []


# ---------------------------------------------------------------------------
# saving_rate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "income,expenses,expected_band",
    [
        (1000, 1100, "negative"),
        (1000, 950, "low"),
        (1000, 800, "good"),
        (1000, 600, "great"),
        (0, 100, "negative"),
    ],
)
def test_saving_rate_bands(income, expenses, expected_band):
    out = saving_rate(income, expenses)
    assert out.band == expected_band


# ---------------------------------------------------------------------------
# top_merchants
# ---------------------------------------------------------------------------


def test_top_merchants_groups_and_sorts():
    txs = [
        FakeTx(date="2026-04-01", amount=10, base_amount=10, description="Continente"),
        FakeTx(date="2026-04-02", amount=15, base_amount=15, description="Continente"),
        FakeTx(date="2026-04-03", amount=50, base_amount=50, description="Ryanair"),
        FakeTx(date="2026-04-04", amount=8, base_amount=8, description="Continente"),
    ]
    out = top_merchants(txs)

    assert out[0].merchant == "RYANAIR"
    assert out[0].count == 1

    cont = next(s for s in out if s.merchant == "CONTINENTE")
    assert cont.count == 3
    assert cont.total_eur == 33.0
    assert cont.avg_eur == 11.0


# ---------------------------------------------------------------------------
# category_drift
# ---------------------------------------------------------------------------


def test_category_drift_flags_above_baseline():
    current = [
        FakeTx(date="2026-04-01", amount=300, base_amount=300, category="Food"),
    ]
    baseline = [
        FakeTx(date="2026-01-15", amount=200, base_amount=200, category="Food"),
        FakeTx(date="2026-02-15", amount=200, base_amount=200, category="Food"),
        FakeTx(date="2026-03-15", amount=200, base_amount=200, category="Food"),
    ]
    out = category_drift(current, baseline, baseline_periods=3)
    food = next(d for d in out if d.category == "Food")

    # Baseline avg = 600/3 = 200; current = 300 → +50% above baseline
    assert food.direction == "above"
    assert food.delta_pct == 50.0


def test_category_drift_skips_no_baseline():
    current = [FakeTx(date="2026-04-01", amount=100, base_amount=100, category="NewCat")]
    out = category_drift(current, [], baseline_periods=3)
    assert all(d.category != "NewCat" for d in out)

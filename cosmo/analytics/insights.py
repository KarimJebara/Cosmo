"""Pure analytics functions over lists of transaction views.

Designed to be cheap (single-pass, no DB access) and easy to test. Callers
in ``app.py`` pull the underlying transactions via ``legacy_adapter``,
filter them by timeframe, and pass the lists in.

All money figures returned by these functions are in the user's base
currency (EUR), unless explicitly noted via ``native_total`` etc.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _amount_eur(tx: Any) -> float:
    """Get a transaction's value in EUR base.

    Falls back to original_amount when base_amount is unset (legacy rows
    pre-FX-snapshot or manually entered EUR). For original_currency != EUR
    rows without a stored base_amount, this is wrong but rare.
    """
    base = float(getattr(tx, "base_amount", 0) or 0)
    if base > 0:
        return base
    return float(getattr(tx, "amount", 0) or 0)


# ---------------------------------------------------------------------------
# 1. Currency exposure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CurrencyExposureSlice:
    currency: str
    native_total: float
    base_total: float
    share_pct: float


def currency_exposure(
    txs: Sequence[Any],
) -> list[CurrencyExposureSlice]:
    """Group transactions by their original currency.

    Returns slices sorted by base_total (EUR-equivalent) descending,
    each carrying both the native-currency total and the base-currency
    total. ``share_pct`` is the percentage of the base-currency total.
    """
    by_ccy_native: dict[str, float] = defaultdict(float)
    by_ccy_base: dict[str, float] = defaultdict(float)

    for tx in txs:
        ccy = (getattr(tx, "currency", "EUR") or "EUR").upper()
        by_ccy_native[ccy] += float(getattr(tx, "amount", 0) or 0)
        by_ccy_base[ccy] += _amount_eur(tx)

    grand_total = sum(by_ccy_base.values())

    out = []
    for ccy in by_ccy_base:
        share = (by_ccy_base[ccy] / grand_total * 100) if grand_total > 0 else 0
        out.append(
            CurrencyExposureSlice(
                currency=ccy,
                native_total=round(by_ccy_native[ccy], 2),
                base_total=round(by_ccy_base[ccy], 2),
                share_pct=round(share, 1),
            )
        )
    out.sort(key=lambda s: s.base_total, reverse=True)
    return out


# ---------------------------------------------------------------------------
# 2. Spend by account
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccountSpendSlice:
    account_id: int
    name: str
    currency: str
    base_total: float
    transaction_count: int


def spend_by_account(
    expenses: Sequence[Any],
    accounts: Sequence[Any],
) -> list[AccountSpendSlice]:
    """Total expense per account in EUR.

    ``accounts`` is the list of ``_AccountView`` objects from
    ``legacy_adapter.get_accounts``. Accounts with no expenses in the
    period are still listed (useful to spot dormant accounts).
    """
    totals: dict[int, float] = defaultdict(float)
    counts: dict[int, int] = defaultdict(int)

    for tx in expenses:
        aid = getattr(tx, "account_id", 0) or 0
        if not aid:
            continue
        totals[aid] += _amount_eur(tx)
        counts[aid] += 1

    out = []
    for acc in accounts:
        out.append(
            AccountSpendSlice(
                account_id=acc.id,
                name=acc.name,
                currency=acc.currency,
                base_total=round(totals.get(acc.id, 0.0), 2),
                transaction_count=counts.get(acc.id, 0),
            )
        )
    out.sort(key=lambda s: s.base_total, reverse=True)
    return out


# ---------------------------------------------------------------------------
# 3. Subscription detector
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Subscription:
    merchant: str
    monthly_eur: float
    last_charge: str
    next_expected: str
    occurrences: int
    avg_amount_eur: float


# Crude normalizer for merchants that lack `merchant_normalized`. Strips
# trailing digits, common bank prefixes, and uppercases.
_BANK_PREFIXES = re.compile(
    r"^(POS\s+|CARD PURCHASE\s+|CONTACTLESS\s+|DIRECT DEBIT\s+|DD\s+)",
    re.IGNORECASE,
)
_TRAIL_DIGITS = re.compile(r"\s*\d{3,}\s*$")


def _fallback_merchant(description: str) -> str:
    if not description:
        return ""
    s = _BANK_PREFIXES.sub("", description.strip())
    s = _TRAIL_DIGITS.sub("", s)
    return s.strip().upper()


def detect_subscriptions(
    expenses: Sequence[Any],
    *,
    lookback_days: int = 90,
    min_occurrences: int = 3,
    amount_tolerance_pct: float = 10.0,
) -> list[Subscription]:
    """Find merchants that look like recurring subscriptions.

    A subscription is a merchant that appears ≥ ``min_occurrences`` times
    within the lookback window with amounts within ``amount_tolerance_pct``
    of each other (CV-based). The "monthly" amount is the median, scaled
    by detected interval (~30 days per cycle).

    This is heuristic — we don't try to detect annual or weekly cycles
    explicitly. Anything roughly periodic with stable amounts qualifies.
    """
    if not expenses:
        return []

    cutoff = datetime.now() - timedelta(days=lookback_days)

    # Group txs by normalized merchant key.
    by_merchant: dict[str, list[tuple[datetime, float, float]]] = defaultdict(list)
    for tx in expenses:
        date = _parse_date(getattr(tx, "date", "") or "")
        if date is None or date < cutoff:
            continue
        key = (
            getattr(tx, "merchant_normalized", None)
            or _fallback_merchant(getattr(tx, "description", "") or "")
        )
        if not key:
            continue
        by_merchant[key].append((date, _amount_eur(tx), float(getattr(tx, "amount", 0))))

    out: list[Subscription] = []
    for merchant, charges in by_merchant.items():
        if len(charges) < min_occurrences:
            continue
        amounts = [c[1] for c in charges]
        median_amt = statistics.median(amounts)
        if median_amt <= 0:
            continue
        # Use coefficient of variation; cheaper than full per-pair check.
        spread = max(amounts) - min(amounts)
        if median_amt > 0 and (spread / median_amt) * 100 > amount_tolerance_pct:
            continue

        charges.sort(key=lambda c: c[0])
        last_date = charges[-1][0]

        # Interval estimate: average gap between consecutive charges.
        if len(charges) >= 2:
            gaps = [
                (charges[i + 1][0] - charges[i][0]).days
                for i in range(len(charges) - 1)
            ]
            avg_gap_days = max(1, sum(gaps) // len(gaps))
        else:
            avg_gap_days = 30

        # Monthly equivalent = median × (30 / interval). For ~monthly this
        # collapses to median; for weekly subs, multiplies up by ~4.3.
        monthly = median_amt * (30 / avg_gap_days)
        next_expected = last_date + timedelta(days=avg_gap_days)

        out.append(
            Subscription(
                merchant=merchant,
                monthly_eur=round(monthly, 2),
                last_charge=last_date.strftime("%Y-%m-%d"),
                next_expected=next_expected.strftime("%Y-%m-%d"),
                occurrences=len(charges),
                avg_amount_eur=round(median_amt, 2),
            )
        )
    out.sort(key=lambda s: s.monthly_eur, reverse=True)
    return out


# ---------------------------------------------------------------------------
# 4. Cumulative balance series
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CumulativePoint:
    date: str
    balance: float


def cumulative_balance_series(
    incomes: Sequence[Any],
    expenses: Sequence[Any],
    *,
    starting_balance: float = 0.0,
) -> list[CumulativePoint]:
    """Daily running net balance over the union of income and expense dates.

    Aggregates incomes and expenses by day, then walks the timeline forward
    accumulating ``+income - expense`` per day. Days with no activity are
    skipped (chart still draws straight lines between points).
    """
    daily: dict[str, float] = defaultdict(float)

    for tx in incomes:
        date = getattr(tx, "date", "")
        if not date:
            continue
        daily[date] += _amount_eur(tx)

    for tx in expenses:
        date = getattr(tx, "date", "")
        if not date:
            continue
        daily[date] -= _amount_eur(tx)

    if not daily:
        return []

    running = starting_balance
    out = []
    for date in sorted(daily.keys()):
        running += daily[date]
        out.append(CumulativePoint(date=date, balance=round(running, 2)))
    return out


# ---------------------------------------------------------------------------
# 5. Saving rate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SavingRate:
    rate_pct: float
    band: str  # 'negative' | 'low' | 'good' | 'great'
    label: str


def saving_rate(total_income: float, total_expenses: float) -> SavingRate:
    """(income - expenses) / income, banded into 4 zones."""
    if total_income <= 0:
        return SavingRate(rate_pct=0.0, band="negative", label="No income recorded")

    rate = (total_income - total_expenses) / total_income * 100

    if rate < 0:
        band = "negative"
        label = "Spending more than you earn"
    elif rate < 15:
        band = "low"
        label = "Below average — most experts suggest 15%+"
    elif rate < 30:
        band = "good"
        label = "Healthy — well above the average household"
    else:
        band = "great"
        label = "Exceptional — top tier"

    return SavingRate(rate_pct=round(rate, 1), band=band, label=label)


# ---------------------------------------------------------------------------
# 6. Top merchants leaderboard
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MerchantStat:
    merchant: str
    total_eur: float
    count: int
    avg_eur: float


def top_merchants(expenses: Sequence[Any], n: int = 10) -> list[MerchantStat]:
    """Top merchants by total spend in EUR base."""
    by_m: dict[str, list[float]] = defaultdict(list)

    for tx in expenses:
        key = (
            getattr(tx, "merchant_normalized", None)
            or _fallback_merchant(getattr(tx, "description", "") or "")
        )
        if not key:
            continue
        by_m[key].append(_amount_eur(tx))

    stats = [
        MerchantStat(
            merchant=m,
            total_eur=round(sum(amts), 2),
            count=len(amts),
            avg_eur=round(sum(amts) / len(amts), 2),
        )
        for m, amts in by_m.items()
    ]
    stats.sort(key=lambda s: s.total_eur, reverse=True)
    return stats[:n]


# ---------------------------------------------------------------------------
# 7. Category drift / anomaly flag
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CategoryDrift:
    category: str
    current_total: float
    baseline_avg: float
    delta_pct: float
    direction: str  # 'above' | 'below' | 'normal'


def category_drift(
    current_expenses: Sequence[Any],
    baseline_expenses: Sequence[Any],
    *,
    baseline_periods: int = 3,
    threshold_pct: float = 25.0,
) -> list[CategoryDrift]:
    """Compare current-period spend per category against a baseline.

    ``baseline_expenses`` should cover ``baseline_periods`` periods of the
    same length as ``current_expenses``. The function divides the baseline
    total by ``baseline_periods`` to get a per-period average, then flags
    categories where the current value differs by more than
    ``threshold_pct``.
    """
    cur: dict[str, float] = defaultdict(float)
    base: dict[str, float] = defaultdict(float)

    for tx in current_expenses:
        cur[getattr(tx, "category", "Uncategorized") or "Uncategorized"] += _amount_eur(tx)
    for tx in baseline_expenses:
        base[getattr(tx, "category", "Uncategorized") or "Uncategorized"] += _amount_eur(tx)

    out = []
    for cat in cur:
        baseline_avg = base.get(cat, 0) / max(baseline_periods, 1)
        if baseline_avg <= 0:
            # No baseline data — skip rather than report misleading deltas.
            continue
        delta_pct = (cur[cat] - baseline_avg) / baseline_avg * 100

        if delta_pct >= threshold_pct:
            direction = "above"
        elif delta_pct <= -threshold_pct:
            direction = "below"
        else:
            direction = "normal"

        out.append(
            CategoryDrift(
                category=cat,
                current_total=round(cur[cat], 2),
                baseline_avg=round(baseline_avg, 2),
                delta_pct=round(delta_pct, 1),
                direction=direction,
            )
        )

    # Sort by absolute drift, biggest first.
    out.sort(key=lambda d: abs(d.delta_pct), reverse=True)
    return out


__all__ = [
    "AccountSpendSlice",
    "CategoryDrift",
    "CumulativePoint",
    "CurrencyExposureSlice",
    "MerchantStat",
    "SavingRate",
    "Subscription",
    "category_drift",
    "cumulative_balance_series",
    "currency_exposure",
    "detect_subscriptions",
    "saving_rate",
    "spend_by_account",
    "top_merchants",
]

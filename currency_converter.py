"""Deprecated module — kept as a compatibility shim.

The real implementations now live in ``cosmo.fx.format`` (formatting) and
``cosmo.fx.service`` (rate fetching, caching, snap-back). This file just
re-exports the surface app.py imports so the rest of the migration can
proceed in small steps. New code should import from cosmo.fx directly.
"""

from __future__ import annotations

from datetime import date as _Date

from cosmo.fx.format import format_currency as _format_currency
from cosmo.fx.format import format_with_conversion as _format_with_conversion
from cosmo.fx.service import default_service


def get_exchange_rates() -> dict[str, float]:
    """Legacy single-base-EUR rate dict. Returns {} on any failure.

    Kept only because some templates may still reference it. New code should
    use ``cosmo.fx.service.default_service().get_rate(date, base, quote)``.
    """
    today = _Date.today()
    targets = ("USD", "GBP", "CHF", "JPY", "CAD", "AUD", "SEK", "NOK", "DKK")
    rates: dict[str, float] = {"EUR": 1.0}
    service = default_service()
    for code in targets:
        rate = service.get_rate(today, "EUR", code)
        if rate is not None:
            rates[code] = rate
    return rates


def convert_to_eur(amount: float, from_currency: str) -> float:
    """Convert amount in ``from_currency`` to EUR using today's rate.

    Returns the original amount if no rate is available — matching legacy
    behaviour. The new code path on transaction creation uses the service
    directly with the transaction's date, not today's.
    """
    if not amount:
        return 0
    if from_currency.upper() == "EUR":
        return float(amount)
    rate = default_service().get_rate(_Date.today(), from_currency, "EUR")
    if rate is None:
        return float(amount)
    return float(amount) * rate


def format_currency(amount, currency="EUR"):
    return _format_currency(float(amount), currency)


def format_amount_with_conversion(amount, original_currency):
    return _format_with_conversion(float(amount), original_currency)

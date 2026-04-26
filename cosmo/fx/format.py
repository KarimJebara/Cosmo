"""Currency formatting for the UI.

Replaces the old ``currency_converter.format_currency`` /
``format_amount_with_conversion`` helpers. The full set of ISO 4217 symbols
is too long to ship inline; we cover the common ones and fall back to
``"<amount> <CCY>"`` for anything else (which is the correct rendering for
codes without a unique symbol anyway).
"""

from __future__ import annotations

from datetime import date as Date

from cosmo.fx.service import default_service

# Symbols for the currencies cosmo's target audience hits most often. Adding a
# code here is a one-liner; please keep alphabetical for readability.
_SYMBOLS: dict[str, str] = {
    "AUD": "A$",
    "BRL": "R$",
    "CAD": "C$",
    "CHF": "CHF ",  # CHF<nbsp>
    "CNY": "¥",
    "EUR": "€",
    "GBP": "£",
    "HKD": "HK$",
    "INR": "₹",
    "JPY": "¥",
    "KRW": "₩",
    "MXN": "$",
    "NOK": "kr ",
    "NZD": "NZ$",
    "PLN": "zł",
    "SEK": "kr ",
    "SGD": "S$",
    "THB": "฿",
    "TRY": "₺",
    "USD": "$",
    "ZAR": "R",
}

# Currencies that are conventionally rendered with no decimal places.
_ZERO_DECIMAL: frozenset[str] = frozenset({"JPY", "KRW", "VND", "CLP"})


def format_currency(amount: float, currency: str = "EUR") -> str:
    """Render an amount in the given currency. Examples:

    >>> format_currency(12.5, 'EUR')
    '€12.50'
    >>> format_currency(1500, 'JPY')
    '¥1500'
    >>> format_currency(99.0, 'XYZ')
    '99.00 XYZ'
    """
    code = currency.upper()
    decimals = 0 if code in _ZERO_DECIMAL else 2
    formatted_number = f"{amount:.{decimals}f}"

    symbol = _SYMBOLS.get(code)
    if symbol is None:
        return f"{formatted_number} {code}"
    return f"{symbol}{formatted_number}"


def format_with_conversion(
    amount: float,
    original_currency: str,
    *,
    base_currency: str = "EUR",
    on_date: Date | None = None,
) -> str:
    """Render the amount in the original currency, with the base-currency
    conversion appended in parentheses.

    Returns just the original-currency rendering when ``original_currency``
    already matches the user's base currency, or when no rate is available.
    """
    original_formatted = format_currency(amount, original_currency)
    if original_currency.upper() == base_currency.upper():
        return original_formatted

    if on_date is None:
        from datetime import date as _D

        on_date = _D.today()

    rate = default_service().get_rate(on_date, original_currency, base_currency)
    if rate is None:
        return original_formatted

    converted = amount * rate
    return f"{original_formatted} ({format_currency(converted, base_currency)})"

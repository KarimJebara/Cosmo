# Currency conversion tests
from currency_converter import (
    convert_to_eur,
    format_amount_with_conversion,
    format_currency,
    get_exchange_rates,
)


def test_get_exchange_rates():
    """Test fetching exchange rates from API."""
    rates = get_exchange_rates()
    assert isinstance(rates, dict)
    assert 'EUR' in rates


def test_exchange_rates_caching():
    """Test exchange rates are cached."""
    rates1 = get_exchange_rates()
    rates2 = get_exchange_rates()
    assert rates1 == rates2


def test_convert_eur_to_eur():
    """Test EUR to EUR conversion (no change)."""
    result = convert_to_eur(100.0, 'EUR')
    assert result == 100.0


def test_convert_gbp_to_eur():
    """Test GBP to EUR conversion."""
    result = convert_to_eur(100.0, 'GBP')
    assert isinstance(result, float)
    assert result > 0


def test_convert_usd_to_eur():
    """Test USD to EUR conversion."""
    result = convert_to_eur(100.0, 'USD')
    assert isinstance(result, float)
    assert result > 0


def test_convert_unknown_currency():
    """Test conversion with unknown currency."""
    result = convert_to_eur(100.0, 'UNKNOWN')
    assert result == 100.0


def test_format_currency_eur():
    """Test formatting EUR currency."""
    result = format_currency(100.0, 'EUR')
    assert '€' in result or 'EUR' in result


def test_format_currency_gbp():
    """Test formatting GBP currency."""
    result = format_currency(100.0, 'GBP')
    assert '£' in result or 'GBP' in result


def test_format_currency_usd():
    """Test formatting USD currency."""
    result = format_currency(100.0, 'USD')
    assert '$' in result or 'USD' in result


def test_format_amount_with_conversion_eur():
    """Test EUR amount formatting (no conversion)."""
    result = format_amount_with_conversion(100.0, 'EUR')
    assert '€' in result or 'EUR' in result
    assert '100' in result


def test_format_amount_with_conversion_non_eur():
    """Test non-EUR amount formatting with conversion."""
    result = format_amount_with_conversion(100.0, 'GBP')
    assert isinstance(result, str)
    assert len(result) > 0


def test_format_amount_display_format():
    """Test display format is (original) converted."""
    result = format_amount_with_conversion(100.0, 'GBP')
    assert isinstance(result, str)
    assert 'GBP' in result or '£' in result


def test_currency_conversion_precision():
    """Test conversion maintains proper decimal precision."""
    result = convert_to_eur(100.50, 'EUR')
    assert abs(result - 100.50) < 0.01

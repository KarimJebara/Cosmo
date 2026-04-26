"""Tests for the Wise + N26 + generic CSV importers."""

from __future__ import annotations

from datetime import date

from cosmo.importers import (
    GenericMapping,
    get_importer,
)
from cosmo.importers.generic import GenericCsvImporter

WISE_CSV = """\
Date,Description,Amount,Currency
2026-04-10,Coffee in London,-4.50,GBP
2026-04-11,Salary,3000.00,EUR
2026-04-12,Tokyo dinner,-2500,JPY
"""


def test_wise_parses_three_currencies():
    importer = get_importer('wise')
    records = list(importer.parse(WISE_CSV))
    assert len(records) == 3
    assert {r.currency for r in records} == {"GBP", "EUR", "JPY"}
    coffee = next(r for r in records if r.description == "Coffee in London")
    assert coffee.amount == -4.50
    assert coffee.date == date(2026, 4, 10)


N26_CSV = """\
Booking Date,Value Date,Partner Name,Partner Iban,Type,Payment Reference,Account Name,Amount (EUR),Original Amount,Original Currency,Exchange Rate
2026-04-10,2026-04-10,Tesco Stores,DE00000,Card Payment,Reference 123,Main,-12.50,,,
2026-04-11,2026-04-11,,DE00000,Direct Debit,Spotify Subscription,Main,-9.99,,,
"""


def test_n26_parses_eur_only_with_partner_fallback():
    importer = get_importer('n26')
    records = list(importer.parse(N26_CSV))
    assert len(records) == 2
    assert all(r.currency == "EUR" for r in records)

    tesco = records[0]
    assert tesco.description == "Tesco Stores"
    assert tesco.amount == -12.50

    # Empty Partner Name → fall back to Payment Reference
    spotify = records[1]
    assert spotify.description == "Spotify Subscription"


GENERIC_CSV = """\
trans_date,merchant,amt,ccy
10/04/2026,Boulangerie,-5.50,EUR
11/04/2026,Wages,2500.00,EUR
"""


def test_generic_with_custom_mapping():
    importer = GenericCsvImporter().configure(
        GenericMapping(
            date_col="trans_date",
            description_col="merchant",
            amount_col="amt",
            currency_col="ccy",
            date_format="%d/%m/%Y",
        )
    )
    records = list(importer.parse(GENERIC_CSV))
    assert len(records) == 2
    assert records[0].date == date(2026, 4, 10)
    assert records[0].description == "Boulangerie"
    assert records[0].amount == -5.50
    assert records[1].amount == 2500.00


def test_generic_unconfigured_raises():
    importer = GenericCsvImporter()
    import pytest

    with pytest.raises(RuntimeError, match="not configured"):
        list(importer.parse("date,amount\n2026-01-01,100"))

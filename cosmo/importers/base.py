"""Importer framework — base classes and the canonical ``ImportRecord``.

Each bank's CSV format is its own little dialect. The job of every importer
is to take a string of CSV bytes and yield ``ImportRecord`` instances in a
canonical shape that the rest of the import pipeline can consume:

* signed amount (positive = inflow / income, negative = outflow / expense),
* original currency preserved untouched,
* parsed date,
* free-text description.

The pipeline (in ``cosmo.legacy_adapter.import_transactions``) does the rest:
auto-categorization, FX conversion to the base currency, dedup, account
routing by currency.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date as Date
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ImportRecord:
    date: Date
    amount: float           # signed: positive=income, negative=expense
    currency: str           # ISO 4217
    description: str


@runtime_checkable
class BaseImporter(Protocol):
    """A CSV-driven bank importer."""

    name: str               # 'revolut' | 'wise' | 'n26' | 'generic'

    def parse(self, csv_content: str) -> Iterable[ImportRecord]:
        """Yield records from a CSV blob. Skips malformed rows silently."""
        ...

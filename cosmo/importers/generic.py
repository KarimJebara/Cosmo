"""Generic CSV importer with configurable column mapping.

For banks that don't have a dedicated adapter. The user picks which CSV
column maps to which canonical field (date / amount / currency /
description) when they upload, and this importer parses accordingly.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import logging
from dataclasses import dataclass
from typing import Iterable

from cosmo.importers.base import ImportRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenericMapping:
    """Maps the canonical fields to actual CSV column names."""
    date_col: str
    amount_col: str
    description_col: str
    currency_col: str | None = None  # None = use ``default_currency``
    default_currency: str = "EUR"
    date_format: str = "%Y-%m-%d"


class GenericCsvImporter:
    """Stateful — needs a ``GenericMapping`` configured before ``parse``."""

    name = "generic"

    def __init__(self, mapping: GenericMapping | None = None) -> None:
        self.mapping = mapping

    def configure(self, mapping: GenericMapping) -> "GenericCsvImporter":
        self.mapping = mapping
        return self

    def parse(self, csv_content: str) -> Iterable[ImportRecord]:
        if self.mapping is None:
            raise RuntimeError(
                "GenericCsvImporter not configured — call configure(mapping) first."
            )
        m = self.mapping

        reader = csv.reader(io.StringIO(csv_content))
        try:
            header = next(reader)
        except StopIteration:
            return

        try:
            i_date = header.index(m.date_col)
            i_amount = header.index(m.amount_col)
            i_desc = header.index(m.description_col)
            i_currency = header.index(m.currency_col) if m.currency_col else None
        except ValueError as e:
            raise ValueError(
                f"Generic CSV missing column from mapping: {e}. "
                f"Header was: {header}"
            ) from e

        for row in reader:
            if not row:
                continue
            try:
                parsed_date = _dt.datetime.strptime(row[i_date], m.date_format).date()
                amount = float(row[i_amount].replace(",", ""))
                currency = (
                    row[i_currency].upper()
                    if i_currency is not None
                    else m.default_currency
                )
                yield ImportRecord(
                    date=parsed_date,
                    amount=amount,
                    currency=currency,
                    description=row[i_desc],
                )
            except (ValueError, IndexError) as exc:
                logger.warning("Generic: skipping malformed row %s: %s", row, exc)
                continue

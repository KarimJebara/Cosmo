"""Wise (formerly TransferWise) CSV importer.

Wise's "Transactions" CSV uses these columns:
``Date`` (YYYY-MM-DD), ``Description``, ``Amount``, ``Currency``. Like
Revolut, amounts are signed so we pass them through.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import logging
from collections.abc import Iterable

from cosmo.importers.base import ImportRecord

logger = logging.getLogger(__name__)


class WiseImporter:
    name = "wise"

    def parse(self, csv_content: str) -> Iterable[ImportRecord]:
        reader = csv.reader(io.StringIO(csv_content))
        try:
            header = next(reader)
        except StopIteration:
            return

        try:
            i_date = header.index("Date")
            i_desc = header.index("Description")
            i_amount = header.index("Amount")
            i_currency = header.index("Currency")
        except ValueError as e:
            raise ValueError(
                f"Wise CSV missing required column: {e}. "
                "Expected 'Date', 'Description', 'Amount', 'Currency'."
            ) from e

        for row in reader:
            if not row:
                continue
            try:
                parsed_date = _dt.datetime.strptime(row[i_date], "%Y-%m-%d").date()
                yield ImportRecord(
                    date=parsed_date,
                    amount=float(row[i_amount]),
                    currency=row[i_currency].upper(),
                    description=row[i_desc],
                )
            except (ValueError, IndexError) as exc:
                logger.warning("Wise: skipping malformed row %s: %s", row, exc)
                continue

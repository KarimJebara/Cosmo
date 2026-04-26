"""Revolut CSV importer — port of api/revolut_importer.py to the new framework.

Revolut's "Statement" CSV exports use these columns of interest:
``Started Date`` (YYYY-MM-DD HH:MM:SS), ``Description``, ``Amount``,
``Currency``. Amounts are already signed (positive=income, negative=expense)
so we pass them through unchanged.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import logging
from collections.abc import Iterable

from cosmo.importers.base import ImportRecord

logger = logging.getLogger(__name__)


class RevolutImporter:
    name = "revolut"

    def parse(self, csv_content: str) -> Iterable[ImportRecord]:
        reader = csv.reader(io.StringIO(csv_content))
        try:
            header = next(reader)
        except StopIteration:
            return

        try:
            i_date = header.index("Started Date")
            i_desc = header.index("Description")
            i_amount = header.index("Amount")
            i_currency = header.index("Currency")
        except ValueError as e:
            raise ValueError(
                f"Revolut CSV missing required column: {e}. "
                "Expected 'Started Date', 'Description', 'Amount', 'Currency'."
            ) from e

        for row in reader:
            if not row:
                continue
            try:
                date_str = row[i_date]
                description = row[i_desc]
                amount = float(row[i_amount])
                currency = row[i_currency].upper()
                # 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DD'
                if " " in date_str:
                    parsed_date = _dt.datetime.strptime(
                        date_str, "%Y-%m-%d %H:%M:%S"
                    ).date()
                else:
                    parsed_date = _dt.datetime.strptime(date_str, "%Y-%m-%d").date()
            except (ValueError, IndexError) as exc:
                logger.warning("Revolut: skipping malformed row %s: %s", row, exc)
                continue

            yield ImportRecord(
                date=parsed_date,
                amount=amount,
                currency=currency,
                description=description,
            )

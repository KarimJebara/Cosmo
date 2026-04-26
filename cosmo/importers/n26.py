"""N26 CSV importer.

N26's "Account Statement" CSV uses these columns:
``Booking Date`` (YYYY-MM-DD), ``Partner Name`` (the merchant/payee),
``Amount (EUR)``, plus ``Type`` and ``Payment Reference``. N26 is EUR-only
so currency is always 'EUR'. We use Partner Name + Payment Reference as the
description (Partner Name preferred, falling back to Payment Reference).
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import logging
from collections.abc import Iterable

from cosmo.importers.base import ImportRecord

logger = logging.getLogger(__name__)


class N26Importer:
    name = "n26"

    def parse(self, csv_content: str) -> Iterable[ImportRecord]:
        reader = csv.reader(io.StringIO(csv_content))
        try:
            header = next(reader)
        except StopIteration:
            return

        try:
            i_date = header.index("Booking Date")
            i_partner = header.index("Partner Name")
            i_amount = header.index("Amount (EUR)")
        except ValueError as e:
            raise ValueError(
                f"N26 CSV missing required column: {e}. "
                "Expected 'Booking Date', 'Partner Name', 'Amount (EUR)'."
            ) from e

        i_reference = (
            header.index("Payment Reference") if "Payment Reference" in header else None
        )

        for row in reader:
            if not row:
                continue
            try:
                parsed_date = _dt.datetime.strptime(row[i_date], "%Y-%m-%d").date()
                description = row[i_partner].strip()
                if not description and i_reference is not None:
                    description = row[i_reference].strip()
                yield ImportRecord(
                    date=parsed_date,
                    amount=float(row[i_amount]),
                    currency="EUR",
                    description=description,
                )
            except (ValueError, IndexError) as exc:
                logger.warning("N26: skipping malformed row %s: %s", row, exc)
                continue

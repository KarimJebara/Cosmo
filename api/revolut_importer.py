from __future__ import annotations

import csv
import datetime as _dt
import io
import logging
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransactionRecord:
    date: _dt.date
    amount: float
    description: str
    currency: str = "EUR"


class RevolutImporter:
    # Removed __init__ and all API-related methods

    @staticmethod
    def parse_csv(csv_content: str) -> List[TransactionRecord]:
        transactions: List[TransactionRecord] = []
        f = io.StringIO(csv_content)
        reader = csv.reader(f)
        
        header = next(reader) 
        
        try:
            started_date_col_idx = header.index('Started Date')
            description_col_idx = header.index('Description')
            amount_col_idx = header.index('Amount')
            currency_col_idx = header.index('Currency')
        except ValueError as e:
            raise ValueError(f"Missing expected CSV column: {e}. Required columns: 'Started Date', 'Description', 'Amount', 'Currency'")

        for row in reader:
            if not row:
                continue

            try:
                date_str_with_time = row[started_date_col_idx]
                description = row[description_col_idx]
                amount_str = row[amount_col_idx]
                currency = row[currency_col_idx]

                # Parse date in 'YYYY-MM-DD HH:MM:SS' format
                date = _dt.datetime.strptime(date_str_with_time, '%Y-%m-%d %H:%M:%S').date()
                amount = float(amount_str)

                transactions.append(TransactionRecord(date=date, amount=amount, description=description, currency=currency))
            except (ValueError, IndexError) as e:
                logger.warning("Skipping malformed row %s: %s", row, e)
                continue
        return transactions

    # Removed import_transactions as it was for API

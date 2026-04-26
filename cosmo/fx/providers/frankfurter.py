"""Frankfurter — primary FX provider.

https://www.frankfurter.app — free, no API key, sources ECB reference rates.
Returns NULL for weekends/holidays (ECB doesn't publish on those days), in
which case the service snaps back to the prior business day.
"""

from __future__ import annotations

import logging
from datetime import date as Date

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.frankfurter.app"
_TIMEOUT_SECONDS = 5


class FrankfurterProvider:
    name = "frankfurter"

    def __init__(self, base_url: str = _BASE_URL, timeout: float = _TIMEOUT_SECONDS) -> None:
        self._base_url = base_url
        self._timeout = timeout

    def fetch_rate(self, on_date: Date, base: str, quote: str) -> float | None:
        if base == quote:
            return 1.0
        url = f"{self._base_url}/{on_date.isoformat()}"
        try:
            response = requests.get(
                url,
                params={"from": base, "to": quote},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException:
            logger.warning("Frankfurter request failed: %s %s->%s", on_date, base, quote)
            raise

        body = response.json()
        rates = body.get("rates") or {}
        rate = rates.get(quote)
        if rate is None:
            return None
        return float(rate)

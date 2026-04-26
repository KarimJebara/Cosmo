"""exchangerate.host — fallback FX provider.

Used when Frankfurter is unreachable or has no data for the requested day.
Free, no API key for the base endpoints. Same response shape as Frankfurter.
"""

from __future__ import annotations

import logging
from datetime import date as Date

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.exchangerate.host"
_TIMEOUT_SECONDS = 5


class ExchangerateHostProvider:
    name = "exchangerate.host"

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
                params={"base": base, "symbols": quote},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException:
            logger.warning(
                "exchangerate.host request failed: %s %s->%s", on_date, base, quote
            )
            raise

        body = response.json()
        rates = body.get("rates") or {}
        rate = rates.get(quote)
        if rate is None:
            return None
        return float(rate)

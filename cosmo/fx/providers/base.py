"""FX provider protocol.

A provider knows how to fetch a single rate for ``base -> quote`` on a given
date. Implementations are stateless and cheap to instantiate.

The abstraction is deliberately tiny: the FX *service* handles caching,
date-snapping, fallback to a secondary provider, and persistence. Providers
just answer the network question.
"""

from __future__ import annotations

from datetime import date as Date
from typing import Protocol, runtime_checkable


@runtime_checkable
class FxProvider(Protocol):
    """Anything that can return a single rate."""

    name: str

    def fetch_rate(self, on_date: Date, base: str, quote: str) -> float | None:
        """Return the rate or ``None`` if the provider has no data for that day.

        Implementations must NOT raise on a missing-data response; only on
        true network/transport failures. A returned ``None`` tells the
        service to try the next provider or snap back a day.
        """
        ...

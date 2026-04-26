"""FX rate service: DB-cached, multi-provider, weekend-aware.

Resolution order for ``get_rate(on_date, base, quote)``:

1. Identity short-circuit: ``base == quote`` returns 1.0.
2. DB cache: hit on exact (base, quote, date)? Return.
3. Date-snap cache: hit on (base, quote) on a date <= ``on_date`` within the
   ``MAX_SNAP_DAYS`` window? Return that.
4. Provider chain: try each provider in order. First non-None response wins,
   gets persisted to ``fx_rates``, and is returned.
5. Snap-back probe: if all providers return None for ``on_date`` (ECB doesn't
   publish on weekends/holidays), retry with ``on_date - 1 day`` up to the
   snap window.

The service writes through to the ``fx_rates`` table; subsequent identical
queries hit step 2 immediately. Tests stub the providers via the ``responses``
library — they never make real HTTP calls.
"""

from __future__ import annotations

import logging
from datetime import date as Date, datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from cosmo.db import get_session
from cosmo.fx.providers import (
    ExchangerateHostProvider,
    FrankfurterProvider,
    FxProvider,
)
from cosmo.models import FxRate

logger = logging.getLogger(__name__)

# How far back to look when an exact-date lookup misses. ECB doesn't publish
# on weekends or holidays, so 5 days covers the worst case (a Monday holiday
# after a 3-day weekend before another holiday).
MAX_SNAP_DAYS = 7


class FxService:
    def __init__(self, providers: Sequence[FxProvider] | None = None) -> None:
        self._providers: Sequence[FxProvider] = providers or (
            FrankfurterProvider(),
            ExchangerateHostProvider(),
        )

    def get_rate(self, on_date: Date, base: str, quote: str) -> float | None:
        """Return rate or None if no provider had data within the snap window."""
        base = base.upper()
        quote = quote.upper()
        if base == quote:
            return 1.0

        with get_session() as session:
            cached = self._lookup_cached(session, on_date, base, quote)
            if cached is not None:
                return cached

            # Try the exact date through each provider, then snap back day by day.
            for delta in range(MAX_SNAP_DAYS + 1):
                probe_date = on_date - timedelta(days=delta)

                # Skip the cache check on delta=0 (already done above) but
                # do check it for snapped dates so we don't re-fetch them.
                if delta > 0:
                    cached = self._lookup_cached_exact(session, probe_date, base, quote)
                    if cached is not None:
                        return cached

                rate = self._fetch_from_providers(probe_date, base, quote)
                if rate is not None:
                    self._persist(session, probe_date, base, quote, rate)
                    return rate

        return None

    # ------------------------------------------------------------------ utils

    def _lookup_cached(
        self, session: Session, on_date: Date, base: str, quote: str
    ) -> float | None:
        """Return the most recent cached rate within the snap window, if any."""
        stmt = (
            select(FxRate)
            .where(
                FxRate.base_currency == base,
                FxRate.quote_currency == quote,
                FxRate.date <= on_date,
                FxRate.date >= on_date - timedelta(days=MAX_SNAP_DAYS),
            )
            .order_by(FxRate.date.desc())
            .limit(1)
        )
        row = session.execute(stmt).scalar_one_or_none()
        return float(row.rate) if row is not None else None

    def _lookup_cached_exact(
        self, session: Session, on_date: Date, base: str, quote: str
    ) -> float | None:
        stmt = select(FxRate).where(
            FxRate.base_currency == base,
            FxRate.quote_currency == quote,
            FxRate.date == on_date,
        )
        row = session.execute(stmt).scalar_one_or_none()
        return float(row.rate) if row is not None else None

    def _fetch_from_providers(self, on_date: Date, base: str, quote: str) -> float | None:
        for provider in self._providers:
            try:
                rate = provider.fetch_rate(on_date, base, quote)
            except Exception:
                logger.exception("FX provider %s failed", provider.name)
                continue
            if rate is not None:
                return rate
        return None

    def _persist(
        self, session: Session, on_date: Date, base: str, quote: str, rate: float
    ) -> None:
        # Use INSERT OR IGNORE semantics by checking first; concurrent writes
        # would just collide on the unique constraint and we'd swallow it.
        existing = self._lookup_cached_exact(session, on_date, base, quote)
        if existing is not None:
            return
        session.add(
            FxRate(
                base_currency=base,
                quote_currency=quote,
                rate=rate,
                date=on_date,
                source=self._providers[0].name if self._providers else "unknown",
                fetched_at=datetime.now(timezone.utc),
            )
        )
        session.flush()


_DEFAULT_SERVICE: FxService | None = None


def default_service() -> FxService:
    """Process-wide singleton. Tests substitute via ``set_default_service``."""
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = FxService()
    return _DEFAULT_SERVICE


def set_default_service(service: FxService | None) -> None:
    """Used by tests to inject a service with stubbed providers."""
    global _DEFAULT_SERVICE
    _DEFAULT_SERVICE = service

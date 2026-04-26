"""Tests for cosmo.fx.service — DB-cached, multi-provider, weekend-aware."""

from __future__ import annotations

from datetime import date

import pytest
import responses

import database
from cosmo.fx.providers import ExchangerateHostProvider, FrankfurterProvider
from cosmo.fx.service import FxService


@pytest.fixture(autouse=True)
def _reset_fx(monkeypatch):
    """Use a fresh FxService for every test and clear the fx_rates table."""
    database.drop_all_users_and_data()
    yield
    database.drop_all_users_and_data()


@pytest.fixture
def service():
    return FxService(
        providers=(
            FrankfurterProvider(base_url="https://api.frankfurter.app"),
            ExchangerateHostProvider(base_url="https://api.exchangerate.host"),
        )
    )


# ---------------------------------------------------------------------------
# Identity short-circuit
# ---------------------------------------------------------------------------


def test_identity_returns_one_without_network(service):
    # No `responses` mock registered — would fail if service tried to fetch.
    assert service.get_rate(date(2026, 4, 10), "EUR", "EUR") == 1.0
    assert service.get_rate(date(2026, 4, 10), "usd", "USD") == 1.0


# ---------------------------------------------------------------------------
# Frankfurter happy path → caches → second call hits DB, not network
# ---------------------------------------------------------------------------


@responses.activate
def test_first_lookup_fetches_then_caches(service):
    responses.get(
        "https://api.frankfurter.app/2026-04-10",
        json={"amount": 1.0, "base": "USD", "date": "2026-04-10", "rates": {"EUR": 0.92}},
        status=200,
    )

    rate = service.get_rate(date(2026, 4, 10), "USD", "EUR")
    assert rate == pytest.approx(0.92)

    # A second call must NOT hit the network — only one mocked response is
    # registered, and `responses` will fail on unmatched calls.
    rate2 = service.get_rate(date(2026, 4, 10), "USD", "EUR")
    assert rate2 == pytest.approx(0.92)
    assert len(responses.calls) == 1


# ---------------------------------------------------------------------------
# Weekend snap-back: empty rates payload → snap to prior business day
# ---------------------------------------------------------------------------


@responses.activate
def test_snaps_back_when_no_rate_for_date(service):
    # Saturday — empty rates from frankfurter
    responses.get(
        "https://api.frankfurter.app/2026-04-11",
        json={"amount": 1.0, "base": "USD", "date": "2026-04-11", "rates": {}},
        status=200,
    )
    # exchangerate.host also empty
    responses.get(
        "https://api.exchangerate.host/2026-04-11",
        json={"base": "USD", "date": "2026-04-11", "rates": {}},
        status=200,
    )
    # Friday — frankfurter has it
    responses.get(
        "https://api.frankfurter.app/2026-04-10",
        json={"amount": 1.0, "base": "USD", "date": "2026-04-10", "rates": {"EUR": 0.92}},
        status=200,
    )

    rate = service.get_rate(date(2026, 4, 11), "USD", "EUR")
    assert rate == pytest.approx(0.92)


# ---------------------------------------------------------------------------
# Provider chain fallback
# ---------------------------------------------------------------------------


@responses.activate
def test_falls_back_to_secondary_provider_when_primary_errors(service):
    # Frankfurter explodes
    responses.get(
        "https://api.frankfurter.app/2026-04-10",
        json={"error": "boom"},
        status=500,
    )
    responses.get(
        "https://api.exchangerate.host/2026-04-10",
        json={"base": "USD", "date": "2026-04-10", "rates": {"EUR": 0.91}},
        status=200,
    )

    rate = service.get_rate(date(2026, 4, 10), "USD", "EUR")
    assert rate == pytest.approx(0.91)


# ---------------------------------------------------------------------------
# Cache window: a rate cached 2 days ago is reused for today
# ---------------------------------------------------------------------------


@responses.activate
def test_uses_cached_neighbour_within_snap_window(service):
    # Seed cache via a first call for Friday
    responses.get(
        "https://api.frankfurter.app/2026-04-10",
        json={"amount": 1.0, "base": "USD", "date": "2026-04-10", "rates": {"EUR": 0.92}},
        status=200,
    )
    service.get_rate(date(2026, 4, 10), "USD", "EUR")

    # Saturday, Sunday — no new mocks registered. Service should reuse
    # cached Friday rate without hitting network.
    rate_sat = service.get_rate(date(2026, 4, 11), "USD", "EUR")
    rate_sun = service.get_rate(date(2026, 4, 12), "USD", "EUR")
    assert rate_sat == pytest.approx(0.92)
    assert rate_sun == pytest.approx(0.92)


# ---------------------------------------------------------------------------
# Total provider failure → returns None (caller decides what to do)
# ---------------------------------------------------------------------------


@responses.activate
def test_returns_none_when_all_providers_fail(service):
    for delta in range(8):  # MAX_SNAP_DAYS+1 days probed
        for url_template in (
            "https://api.frankfurter.app/2026-04-{:02d}",
            "https://api.exchangerate.host/2026-04-{:02d}",
        ):
            url = url_template.format(10 - delta if 10 - delta > 0 else 1)
            responses.get(url, json={"rates": {}}, status=200)

    assert service.get_rate(date(2026, 4, 10), "ZZZ", "EUR") is None

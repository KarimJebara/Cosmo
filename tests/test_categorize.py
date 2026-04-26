"""Tests for cosmo.categorize — normalize, match, learn."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from cosmo.categorize import (
    find_match,
    learn_from_correction,
    normalize_merchant,
    record_match_used,
)
from cosmo.models import Base, Category, User
from cosmo.repos import MerchantRuleRepo

# ---------------------------------------------------------------------------
# normalize_merchant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Casing
        ("Tesco", "TESCO"),
        # Trailing terminal id
        ("TESCO STORES 1234", "TESCO STORES"),
        # Trailing country code
        ("TESCO STORES LONDON GB", "TESCO STORES LONDON"),
        # Multiple trailing fragments
        ("TESCO STORES 1234 LONDON GB", "TESCO STORES"),
        # POS prefix
        ("POS Albert Heijn 9876", "ALBERT HEIJN"),
        # Card purchase prefix
        ("CARD PURCHASE - REVOLUT*Spotify Premium", "SPOTIFY PREMIUM"),
        # Aggregator: Square
        ("SQ *COFFEE BAR", "COFFEE BAR"),
        # Aggregator: Amazon Marketplace IE
        ("AMZN MKTP IE*ABCD12", "ABCD12"),  # not great but stable
        # Trailing date
        ("CAFE NOIR 2026-04-10", "CAFE NOIR"),
        # Whitespace
        ("   N26   PURCHASE   ", "N26 PURCHASE"),
        # Empty / whitespace-only
        ("", ""),
        ("   ", ""),
        # Only digits/country = should leave non-empty descriptor preserved
        ("LIDL DE", "LIDL"),
        # Trailing punctuation
        ("UBER*EATS---", "UBER*EATS"),
    ],
)
def test_normalize_merchant_table(raw, expected):
    assert normalize_merchant(raw) == expected


# ---------------------------------------------------------------------------
# Fixtures for matcher / learner — in-memory SQLite, no Flask
# ---------------------------------------------------------------------------


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _r):
        c = dbapi_conn.cursor()
        c.execute("PRAGMA foreign_keys = ON")
        c.close()

    Base.metadata.create_all(engine)
    s = Session(engine, future=True)
    try:
        yield s
        s.commit()
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def alice_with_groceries(session):
    user = User(username="alice", password_hash="x", base_currency="EUR")
    session.add(user)
    session.flush()
    cat = Category(user_id=user.id, name="Groceries", type="expense")
    session.add(cat)
    session.flush()
    return user, cat


# ---------------------------------------------------------------------------
# find_match
# ---------------------------------------------------------------------------


def test_no_rules_returns_none(session, alice_with_groceries):
    user, _ = alice_with_groceries
    assert find_match(session, user.id, "TESCO STORES 1234") is None


def test_exact_match_via_normalization(session, alice_with_groceries):
    user, cat = alice_with_groceries
    MerchantRuleRepo(session).upsert(
        user_id=user.id,
        pattern="TESCO STORES",
        category_id=cat.id,
        match_type="exact",
    )
    # Different terminal IDs and country codes still resolve to the same
    # canonical form.
    for desc in (
        "TESCO STORES 1234",
        "Tesco stores 9876 LONDON GB",
        "POS Tesco Stores 4321",
    ):
        match = find_match(session, user.id, desc)
        assert match is not None, desc
        assert match.category_id == cat.id
        assert match.confidence == 100


def test_contains_match(session, alice_with_groceries):
    user, cat = alice_with_groceries
    MerchantRuleRepo(session).upsert(
        user_id=user.id, pattern="TESCO", category_id=cat.id, match_type="contains"
    )
    match = find_match(session, user.id, "Tesco Express Brighton")
    assert match is not None
    assert match.match_type == "contains"
    assert match.confidence == 90


def test_fuzzy_match_within_threshold(session, alice_with_groceries):
    user, cat = alice_with_groceries
    MerchantRuleRepo(session).upsert(
        user_id=user.id, pattern="TESCO STORES", category_id=cat.id, match_type="fuzzy"
    )
    # token_set_ratio handles word reordering and extras well
    match = find_match(session, user.id, "STORES TESCO")
    assert match is not None
    assert match.match_type == "fuzzy"
    assert match.confidence >= 88


def test_fuzzy_below_threshold_returns_none(session, alice_with_groceries):
    user, cat = alice_with_groceries
    MerchantRuleRepo(session).upsert(
        user_id=user.id, pattern="TESCO STORES", category_id=cat.id, match_type="fuzzy"
    )
    assert find_match(session, user.id, "completely unrelated payee") is None


def test_higher_confidence_wins(session, alice_with_groceries):
    user, cat = alice_with_groceries
    other = Category(user_id=user.id, name="Wrong", type="expense")
    session.add(other)
    session.flush()

    repo = MerchantRuleRepo(session)
    repo.upsert(
        user_id=user.id, pattern="TESCO", category_id=other.id, match_type="contains"
    )
    repo.upsert(
        user_id=user.id, pattern="TESCO STORES", category_id=cat.id, match_type="exact"
    )

    match = find_match(session, user.id, "TESCO STORES 1234")
    assert match is not None
    assert match.category_id == cat.id  # exact (100) beats contains (90)


# ---------------------------------------------------------------------------
# Per-user isolation
# ---------------------------------------------------------------------------


def test_users_dont_see_each_others_rules(session):
    a = User(username="a", password_hash="x", base_currency="EUR")
    b = User(username="b", password_hash="x", base_currency="EUR")
    session.add_all([a, b])
    session.flush()

    cat_a = Category(user_id=a.id, name="Groceries", type="expense")
    cat_b = Category(user_id=b.id, name="Travel", type="expense")
    session.add_all([cat_a, cat_b])
    session.flush()

    MerchantRuleRepo(session).upsert(
        user_id=a.id, pattern="TESCO", category_id=cat_a.id, match_type="exact"
    )

    # User a's rule fires for a, but not for b.
    assert find_match(session, a.id, "TESCO") is not None
    assert find_match(session, b.id, "TESCO") is None


# ---------------------------------------------------------------------------
# Learner
# ---------------------------------------------------------------------------


def test_learn_from_correction_creates_rule(session, alice_with_groceries):
    user, cat = alice_with_groceries
    rule = learn_from_correction(
        session,
        user_id=user.id,
        raw_description="POS Tesco Stores 1234",
        category_id=cat.id,
    )
    assert rule is not None
    assert rule.pattern == "TESCO STORES"  # normalized
    assert rule.category_id == cat.id
    assert rule.source == "user"


def test_learn_from_correction_is_idempotent(session, alice_with_groceries):
    user, cat = alice_with_groceries
    r1 = learn_from_correction(
        session, user_id=user.id, raw_description="Tesco Stores", category_id=cat.id
    )
    r2 = learn_from_correction(
        session, user_id=user.id, raw_description="TESCO STORES 9999", category_id=cat.id
    )
    assert r1 is not None and r2 is not None
    assert r1.id == r2.id  # both normalize to "TESCO STORES"


def test_learn_then_match_round_trip(session, alice_with_groceries):
    """The end-to-end story: user re-categorizes once, future txs auto-match."""
    user, cat = alice_with_groceries
    learn_from_correction(
        session,
        user_id=user.id,
        raw_description="Tesco Express 1234",
        category_id=cat.id,
    )
    # A future similar transaction should now match.
    match = find_match(session, user.id, "TESCO EXPRESS 9876 BRIGHTON GB")
    assert match is not None
    assert match.category_id == cat.id


def test_record_match_used_increments_hit_count(session, alice_with_groceries):
    user, cat = alice_with_groceries
    rule = MerchantRuleRepo(session).upsert(
        user_id=user.id, pattern="TESCO", category_id=cat.id, match_type="exact"
    )
    assert rule.hit_count == 0
    record_match_used(session, rule.id)
    record_match_used(session, rule.id)
    session.refresh(rule)
    assert rule.hit_count == 2
    assert rule.last_used_at is not None


def test_empty_description_does_not_create_rule(session, alice_with_groceries):
    user, cat = alice_with_groceries
    assert (
        learn_from_correction(
            session, user_id=user.id, raw_description="", category_id=cat.id
        )
        is None
    )
    assert (
        learn_from_correction(
            session, user_id=user.id, raw_description="   ", category_id=cat.id
        )
        is None
    )

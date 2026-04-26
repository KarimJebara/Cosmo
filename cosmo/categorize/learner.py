"""Adaptive merchant rules — learns from user corrections.

When a user re-categorizes a transaction (``change_category_by_natural_key``
in legacy_adapter), we upsert a per-user MerchantRule on the *normalized*
descriptor. Future transactions whose descriptor normalizes to the same
canonical form will auto-pick that category.

When a user *accepts* an auto-suggested category (i.e. add_transaction
with a fuzzy-matched suggestion that the user didn't override), the rule's
hit_count gets bumped.

Phase 3 ships with two strategies:

- ``learn_from_correction(...)`` — called when user supplies the category
  manually. Creates an ``exact`` rule on the normalized merchant.
- ``record_match_used(...)`` — called when find_match returned a rule and
  the caller decided to apply it. Bumps hit_count and last_used_at.

The "demote rules that misfire 3 times" idea from the plan needs a
correction-event log to detect, which is bigger than this phase. Tracking
hit_count alone is enough to surface the most-trusted rules in the UI.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from cosmo.categorize.normalize import normalize_merchant
from cosmo.models import MerchantRule
from cosmo.repos import MerchantRuleRepo

logger = logging.getLogger(__name__)


def learn_from_correction(
    session: Session,
    *,
    user_id: int,
    raw_description: str,
    category_id: int,
) -> MerchantRule | None:
    """Upsert an exact rule on the normalized merchant. Returns the rule, or
    None if the description normalizes to something empty/useless.
    """
    normalized = normalize_merchant(raw_description)
    if not normalized:
        return None

    rule = MerchantRuleRepo(session).upsert(
        user_id=user_id,
        pattern=normalized,
        category_id=category_id,
        match_type="exact",
        source="user",
    )
    logger.info(
        "Learned merchant rule: user=%s pattern=%r -> category_id=%s",
        user_id, normalized, category_id,
    )
    return rule


def record_match_used(session: Session, rule_id: int) -> None:
    """Bump hit_count + last_used_at on a matched rule."""
    MerchantRuleRepo(session).record_hit(rule_id)

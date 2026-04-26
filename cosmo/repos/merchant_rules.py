from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from cosmo.models import MerchantRule


class MerchantRuleRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def list_for_user(self, user_id: int) -> Sequence[MerchantRule]:
        stmt = (
            select(MerchantRule)
            .where(MerchantRule.user_id == user_id)
            .order_by(MerchantRule.hit_count.desc(), MerchantRule.id)
        )
        return self._s.execute(stmt).scalars().all()

    def get(self, rule_id: int, user_id: int) -> MerchantRule | None:
        stmt = select(MerchantRule).where(
            MerchantRule.id == rule_id, MerchantRule.user_id == user_id
        )
        return self._s.execute(stmt).scalar_one_or_none()

    def get_by_pattern(
        self, user_id: int, pattern: str, match_type: str = "exact"
    ) -> MerchantRule | None:
        stmt = select(MerchantRule).where(
            MerchantRule.user_id == user_id,
            MerchantRule.pattern == pattern,
            MerchantRule.match_type == match_type,
        )
        return self._s.execute(stmt).scalar_one_or_none()

    def upsert(
        self,
        *,
        user_id: int,
        pattern: str,
        category_id: int,
        match_type: str = "exact",
        source: str = "user",
    ) -> MerchantRule:
        existing = self.get_by_pattern(user_id, pattern, match_type)
        if existing is not None:
            existing.category_id = category_id
            existing.source = source
            return existing
        rule = MerchantRule(
            user_id=user_id,
            pattern=pattern,
            match_type=match_type,
            category_id=category_id,
            hit_count=0,
            source=source,
        )
        self._s.add(rule)
        self._s.flush()
        return rule

    def record_hit(self, rule_id: int) -> None:
        rule = self._s.get(MerchantRule, rule_id)
        if rule is None:
            return
        rule.hit_count = (rule.hit_count or 0) + 1
        rule.last_used_at = datetime.now(timezone.utc)
        # Flush so subsequent reads in the same session (including
        # ``session.refresh(rule)``) see the new value.
        self._s.flush()

    def delete(self, rule_id: int, user_id: int) -> bool:
        rule = self.get(rule_id, user_id)
        if rule is None:
            return False
        self._s.delete(rule)
        return True

"""Categorize a merchant descriptor against a user's MerchantRule rows.

Match priority (highest confidence wins, ties broken by hit_count):

1. **Exact** on the normalized descriptor — confidence 100.
2. **Contains** — pattern is a substring of the normalized descriptor — 90.
3. **Fuzzy** — rapidfuzz token_set_ratio ≥ FUZZY_THRESHOLD on the normalized
   descriptor vs. the rule pattern — score 0..100.
4. **Regex** — re.search on the *raw* descriptor (rules of type ``regex`` are
   power-user only) — 95 if matched.

Returns ``MatchResult`` or ``None``. The caller decides what to do with low
confidence — e.g. show the suggestion but don't apply it silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from cosmo.categorize.normalize import normalize_merchant
from cosmo.repos import MerchantRuleRepo

FUZZY_THRESHOLD = 88  # rapidfuzz token_set_ratio cutoff


@dataclass(frozen=True)
class MatchResult:
    rule_id: int
    category_id: int
    confidence: int  # 0..100
    match_type: str  # 'exact' | 'contains' | 'fuzzy' | 'regex'


def find_match(
    session: Session,
    user_id: int,
    raw_description: str,
) -> MatchResult | None:
    if not raw_description:
        return None

    normalized = normalize_merchant(raw_description)
    rules = MerchantRuleRepo(session).list_for_user(user_id)
    if not rules:
        return None

    best: MatchResult | None = None

    for rule in rules:
        result = _score_rule(rule, raw_description, normalized)
        if result is None:
            continue
        if best is None or result.confidence > best.confidence:
            best = result

    return best


def _score_rule(rule, raw: str, normalized: str) -> MatchResult | None:
    pattern_norm = normalize_merchant(rule.pattern) if rule.pattern else ""

    if rule.match_type == "exact":
        if pattern_norm and pattern_norm == normalized:
            return MatchResult(rule.id, rule.category_id, 100, "exact")
        return None

    if rule.match_type == "contains":
        if pattern_norm and pattern_norm in normalized:
            return MatchResult(rule.id, rule.category_id, 90, "contains")
        return None

    if rule.match_type == "regex":
        try:
            if re.search(rule.pattern, raw, flags=re.IGNORECASE):
                return MatchResult(rule.id, rule.category_id, 95, "regex")
        except re.error:
            return None
        return None

    if rule.match_type == "fuzzy":
        if not pattern_norm or not normalized:
            return None
        score = int(fuzz.token_set_ratio(normalized, pattern_norm))
        if score >= FUZZY_THRESHOLD:
            return MatchResult(rule.id, rule.category_id, score, "fuzzy")
        return None

    return None

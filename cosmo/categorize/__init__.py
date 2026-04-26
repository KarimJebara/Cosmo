"""Per-user merchant categorization — normalize → match → learn."""

from cosmo.categorize.learner import learn_from_correction, record_match_used
from cosmo.categorize.matcher import FUZZY_THRESHOLD, MatchResult, find_match
from cosmo.categorize.normalize import normalize_merchant

__all__ = [
    "FUZZY_THRESHOLD",
    "MatchResult",
    "find_match",
    "learn_from_correction",
    "normalize_merchant",
    "record_match_used",
]

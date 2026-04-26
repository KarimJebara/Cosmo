"""Merchant string normalization.

Bank descriptors are noisy: ``TESCO STORES 1234 LONDON GB``,
``AMZN MKTP IE*ABCD12``, ``POS Albert Heijn 9876``, ``CARD PURCHASE - REVOLUT*FOO``.
This module collapses these into a stable canonical form so the matcher can
compare apples to apples and the per-user rule table doesn't fragment into
near-duplicates.

Design choices:

- Uppercase everything. ``Tesco`` and ``TESCO`` are the same merchant.
- Strip a fixed set of common bank prefixes (``POS``, ``CARD PURCHASE``, …).
- Strip aggregator wrappers (``REVOLUT*…``, ``SQ *…``, ``AMZN MKTP IE*…``).
- Drop trailing card terminal IDs and reference numbers (``... 1234``).
- Drop trailing 2-letter country codes (``... GB``, ``... US``).
- Drop the "1234 CITY" pattern that appears mid-string in card-network
  descriptors (terminal id followed by branch city).
- Collapse whitespace.

The output is intentionally lossy: ``Tesco Stores 1234 London`` and
``TESCO STORES 5678 BRIGHTON`` both normalize to ``TESCO STORES``. That's the
point — the matcher keys off ``TESCO STORES`` and the user only has to
teach the rule once.
"""

from __future__ import annotations

import re

# Common bank-statement prefixes to strip. Order matters within this tuple —
# longer phrases first so 'CARD PURCHASE - ' matches before 'CARD '.
_PREFIXES = (
    "CARD PURCHASE - ",
    "CARD PURCHASE ",
    "POS PURCHASE ",
    "DEBIT CARD PURCHASE ",
    "PURCHASE AUTHORIZED ON ",
    "POS ",
    "DEBIT ",
    "TRANSFER ",
    "DD ",  # direct debit
    "SEPA ",
)

# Aggregator merchant-of-record prefixes followed by *<their merchant>.
# Longest specific prefixes first so 'AMZN MKTP IE*' wins over 'AMZN MKTP '.
_AGGREGATORS = (
    "AMZN MKTP IE*",
    "AMZN MKTP US*",
    "AMZN MKTP UK*",
    "AMZN MKTP ",
    "REVOLUT*",
    "SQ *",
    "PAYPAL *",
    "PP*",
    "STRIPE*",
)

# Trailing 2-letter ISO country code at end of card-network descriptors.
_TRAILING_COUNTRY_RE = re.compile(r"\s+[A-Z]{2}$")

# Trailing digits-only token (terminal/reference id), one or more times.
_TRAILING_NUMBERS_RE = re.compile(r"(\s+\d+)+$")

# Trailing date in the form 12/06, 2026-04-10, etc.
_TRAILING_DATE_RE = re.compile(r"\s+(\d{1,4}[-/]\d{1,2}([-/]\d{1,4})?)$")

# A *mid-string* digits token followed by 1+ more tokens — typically the
# pattern '<merchant> <terminal-id> <city>'. We strip from the digit token
# to end. Only matches when the digit token is preceded by alpha content
# so we don't blow up plain '1234'.
_MID_DIGITS_TAIL_RE = re.compile(r"(?<=[A-Z])\s+\d+\s+\S+(?:\s+\S+)*$")

# Multiple whitespace → single space.
_WS_RE = re.compile(r"\s+")


def _strip_one_prefix(text: str) -> tuple[str, bool]:
    """Try to strip any single prefix or aggregator. Returns (text, changed)."""
    for prefix in _PREFIXES + _AGGREGATORS:
        if text.startswith(prefix):
            return text[len(prefix):].strip(), True
    return text, False


def normalize_merchant(raw: str) -> str:
    """Return the canonical form of a merchant descriptor.

    >>> normalize_merchant('TESCO STORES 1234 LONDON GB')
    'TESCO STORES'
    >>> normalize_merchant('POS Albert Heijn 9876')
    'ALBERT HEIJN'
    >>> normalize_merchant('CARD PURCHASE - REVOLUT*Spotify Premium')
    'SPOTIFY PREMIUM'
    >>> normalize_merchant('   ')
    ''
    """
    if not raw:
        return ""

    text = raw.upper().strip()

    # Strip prefixes/aggregators — repeat until none apply, since a bank
    # prefix can wrap an aggregator wrapper ('CARD PURCHASE - REVOLUT*X').
    for _ in range(4):
        text, changed = _strip_one_prefix(text)
        if not changed:
            break

    # Iterate the trailing-junk strippers until stable. Order: country first
    # (so '1234 LONDON GB' → '1234 LONDON' → can match the mid-digits rule).
    for _ in range(4):
        prev = text
        text = _TRAILING_DATE_RE.sub("", text).rstrip()
        text = _TRAILING_COUNTRY_RE.sub("", text).rstrip()
        text = _TRAILING_NUMBERS_RE.sub("", text).rstrip()
        text = _MID_DIGITS_TAIL_RE.sub("", text).rstrip()
        if text == prev:
            break

    text = _WS_RE.sub(" ", text).strip()

    # Drop a single trailing punctuation char (* - / etc.)
    while text and text[-1] in "*-/.,":
        text = text[:-1].rstrip()

    return text

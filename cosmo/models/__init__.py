"""ORM model exports.

Importing this module attaches every table to ``Base.metadata``, which Alembic
uses to auto-generate migrations.
"""

from cosmo.models.accounts import Account
from cosmo.models.base import Base
from cosmo.models.budgets import Budget
from cosmo.models.categories import Category
from cosmo.models.fx_rates import FxRate
from cosmo.models.import_sources import ImportSource
from cosmo.models.merchant_rules import MerchantRule
from cosmo.models.transactions import Transaction
from cosmo.models.users import User

__all__ = [
    "Base",
    "User",
    "Account",
    "Category",
    "Transaction",
    "Budget",
    "MerchantRule",
    "FxRate",
    "ImportSource",
]

"""Repository layer.

Each repository is a thin SQLAlchemy-session-based class that owns the queries
for a single aggregate (Account, Category, Transaction, Budget). Routes
acquire a session via ``cosmo.db.get_session()`` and pass it to the repos —
the repos never own session lifecycle.

This replaces the legacy ``models.data_manager.DataManager`` whose ``save()``
method deleted every row for the user and re-inserted everything; that lost
created_at, broke IDs, and was unsafe under concurrent writes.
"""

from cosmo.repos.accounts import AccountRepo
from cosmo.repos.budgets import BudgetRepo
from cosmo.repos.categories import CategoryRepo
from cosmo.repos.transactions import TransactionRepo

__all__ = ["AccountRepo", "BudgetRepo", "CategoryRepo", "TransactionRepo"]

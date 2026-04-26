"""Auth + DB bootstrap.

Auth functions read/write the v1 ``users_v2`` table. ``init_db()`` runs
``alembic upgrade head`` which creates both the v1 schema and (idempotently)
the legacy tables for any DB created before the migration. ``create_user``
also creates a default account for the new user so the rest of the app
always has an account to attach transactions to.
"""

import hashlib
import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

DATABASE_PATH = 'data/budget_tracker.db'

logger = logging.getLogger(__name__)

_HASHER = PasswordHasher()


def _is_legacy_sha256(password_hash: str) -> bool:
    return (
        isinstance(password_hash, str)
        and len(password_hash) == 64
        and all(c in '0123456789abcdef' for c in password_hash.lower())
    )


def ensure_data_directory_exists():
    os.makedirs('data', exist_ok=True)


@contextmanager
def get_db():
    """Raw sqlite3 connection. Used by auth helpers and a handful of legacy callers."""
    ensure_data_directory_exists()
    conn = sqlite3.connect(DATABASE_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Run Alembic to bring the schema to head.

    Falls back to creating the v1 tables directly via SQLAlchemy metadata
    when Alembic isn't available (e.g. some test environments). Either way,
    on return ``users_v2`` and friends exist.
    """
    ensure_data_directory_exists()

    repo_root = Path(__file__).resolve().parent
    db_url = f"sqlite:///{repo_root / DATABASE_PATH}"
    os.environ["DATABASE_URL"] = db_url

    try:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config(str(repo_root / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(repo_root / "cosmo" / "migrations"))
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(alembic_cfg, "head")
    except Exception:
        logger.exception("Alembic upgrade failed; falling back to metadata.create_all")
        from cosmo.db import engine
        from cosmo.models import Base

        Base.metadata.create_all(engine)


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if _is_legacy_sha256(password_hash):
        return hashlib.sha256(password.encode()).hexdigest() == password_hash
    try:
        return _HASHER.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        logger.warning("Unexpected hash format encountered during verify")
        return False


def create_user(username: str, password: str) -> int | None:
    """Create a user in users_v2 + a default EUR account. Returns user id or None on dup."""
    password_hash = hash_password(password)
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO users_v2 (username, password_hash, base_currency, created_at) '
                "VALUES (?, ?, 'EUR', CURRENT_TIMESTAMP)",
                (username, password_hash),
            )
            user_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

        cursor.execute(
            'INSERT INTO accounts (user_id, name, currency, type, opening_balance, '
            "archived, created_at, updated_at) "
            "VALUES (?, 'Default', 'EUR', 'checking', 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (user_id,),
        )
        return user_id


def _upgrade_password_hash_if_needed(user_id: int, password: str, current_hash: str) -> None:
    needs_upgrade = _is_legacy_sha256(current_hash)
    if not needs_upgrade:
        try:
            needs_upgrade = _HASHER.check_needs_rehash(current_hash)
        except Exception:
            needs_upgrade = False
    if not needs_upgrade:
        return
    new_hash = _HASHER.hash(password)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE users_v2 SET password_hash = ? WHERE id = ?',
            (new_hash, user_id),
        )
    logger.info("Upgraded password hash for user_id=%s", user_id)


def authenticate_user(username: str, password: str) -> int | None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, password_hash FROM users_v2 WHERE username = ?',
            (username,),
        )
        user = cursor.fetchone()
    if user and verify_password(password, user['password_hash']):
        _upgrade_password_hash_if_needed(user['id'], password, user['password_hash'])
        return user['id']
    return None


def get_user_by_id(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, username, password_hash FROM users_v2 WHERE id = ?',
            (user_id,),
        )
        return cursor.fetchone()


def drop_all_users_and_data():
    """Wipe every cosmo + legacy table. Used by tests and reset_for_testing.

    Order matters because of foreign keys. Any table that doesn't exist yet
    is silently skipped — useful when running on a partly-migrated DB.
    """
    conn = sqlite3.connect(DATABASE_PATH, timeout=10.0)
    cursor = conn.cursor()

    table_order = [
        # v1 schema (children first)
        'transactions',
        'budgets_v2',
        'merchant_rules',
        'categories',
        'import_sources',
        'accounts',
        'fx_rates',
        'users_v2',
        # legacy
        'budgets',
        'incomes',
        'expenses',
        'users',
    ]

    try:
        for table in table_order:
            try:
                cursor.execute(f'DELETE FROM {table}')
            except sqlite3.OperationalError:
                # Table may not exist (fresh db before alembic, or already dropped)
                pass
        try:
            cursor.execute(
                "DELETE FROM sqlite_sequence WHERE name IN "
                "('users_v2','accounts','categories','transactions','budgets_v2',"
                "'merchant_rules','fx_rates','import_sources',"
                "'users','expenses','incomes','budgets')"
            )
        except sqlite3.OperationalError:
            pass
        conn.commit()
        logger.info("All v1 + legacy tables cleared")
    except sqlite3.Error as e:
        conn.rollback()
        raise RuntimeError(f"Failed to clear database data: {e}") from e
    finally:
        cursor.close()
        conn.close()

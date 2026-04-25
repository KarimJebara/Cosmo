import hashlib
import logging
import os
import sqlite3
from contextlib import contextmanager

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

DATABASE_PATH = 'data/budget_tracker.db'

logger = logging.getLogger(__name__)

# Argon2id with PHC-recommended defaults; tweak via env if needed.
_HASHER = PasswordHasher()


def _is_legacy_sha256(password_hash: str) -> bool:
    """Detect a legacy unsalted SHA-256 hex digest (64 hex chars)."""
    return (
        isinstance(password_hash, str)
        and len(password_hash) == 64
        and all(c in '0123456789abcdef' for c in password_hash.lower())
    )

def ensure_data_directory_exists():
    """Ensure data directory exists"""
    os.makedirs('data', exist_ok=True)

@contextmanager
def get_db():
    """Context manager for database connections"""
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
    """Initialize the database with required tables"""
    ensure_data_directory_exists()
    conn = sqlite3.connect(DATABASE_PATH, timeout=10.0)
    cursor = conn.cursor()
    
    try:
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Expenses table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'EUR',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Incomes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS incomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'EUR',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Budgets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                limit_amount REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, category),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Migration: Add currency column to expenses and incomes tables if it doesn't exist
        cursor.execute("PRAGMA table_info(expenses)")
        expenses_columns = [col[1] for col in cursor.fetchall()]
        if 'currency' not in expenses_columns:
            cursor.execute('ALTER TABLE expenses ADD COLUMN currency TEXT DEFAULT "EUR"')
        
        cursor.execute("PRAGMA table_info(incomes)")
        incomes_columns = [col[1] for col in cursor.fetchall()]
        if 'currency' not in incomes_columns:
            cursor.execute('ALTER TABLE incomes ADD COLUMN currency TEXT DEFAULT "EUR"')
        
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise RuntimeError(f"Database initialization failed: {e}")
    finally:
        cursor.close()
        conn.close()

def hash_password(password: str) -> str:
    """Hash a password using Argon2id (PHC winner, recommended for new code)."""
    return _HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash. Supports legacy unsalted SHA-256 hashes."""
    if _is_legacy_sha256(password_hash):
        return hashlib.sha256(password.encode()).hexdigest() == password_hash
    try:
        return _HASHER.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        # Argon2 raises InvalidHash and friends — treat any non-match as failure.
        logger.warning("Unexpected hash format encountered during verify")
        return False


def create_user(username: str, password: str) -> int | None:
    """Create a new user with an Argon2id-hashed password."""
    with get_db() as conn:
        cursor = conn.cursor()
        password_hash = hash_password(password)
        try:
            cursor.execute(
                'INSERT INTO users (username, password_hash) VALUES (?, ?)',
                (username, password_hash)
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def _upgrade_password_hash_if_needed(user_id: int, password: str, current_hash: str) -> None:
    """Transparently rehash legacy SHA-256 or out-of-date Argon2 params on successful login."""
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
            'UPDATE users SET password_hash = ? WHERE id = ?',
            (new_hash, user_id),
        )
    logger.info("Upgraded password hash for user_id=%s", user_id)


def authenticate_user(username: str, password: str) -> int | None:
    """Authenticate a user and return user_id if successful. Rehashes legacy hashes on success."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, password_hash FROM users WHERE username = ?',
            (username,)
        )
        user = cursor.fetchone()
    if user and verify_password(password, user['password_hash']):
        _upgrade_password_hash_if_needed(user['id'], password, user['password_hash'])
        return user['id']
    return None

def get_user_by_id(user_id):
    """Get user information by user_id"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, password_hash FROM users WHERE id = ?', (user_id,))
        return cursor.fetchone()

def drop_all_users_and_data():
    """Drop all users and their associated data from the database"""
    conn = sqlite3.connect(DATABASE_PATH, timeout=10.0)
    cursor = conn.cursor()
    
    try:
        # Delete all data from all tables (order matters due to foreign keys)
        cursor.execute('DELETE FROM budgets')
        cursor.execute('DELETE FROM incomes')
        cursor.execute('DELETE FROM expenses')
        cursor.execute('DELETE FROM users')
        # Reset autoincrement counters
        cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('users', 'expenses', 'incomes', 'budgets')")
        conn.commit()
        print("All users and associated data have been dropped from the database.")
    except sqlite3.Error as e:
        conn.rollback()
        raise RuntimeError(f"Failed to clear database data: {e}")
    finally:
        cursor.close()
        conn.close()

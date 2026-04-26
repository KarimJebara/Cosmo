# Database tests
import os

import pytest

import database


@pytest.fixture
def setup_database():
    """Setup and teardown for database tests"""
    database.init_db()
    yield
    database.drop_all_users_and_data()


def test_init_db(setup_database):
    """Test database initialization and table creation."""
    assert os.path.exists(database.DATABASE_PATH)


def test_create_user(setup_database):
    """Test user creation in database."""
    user_id = database.create_user('testuser', 'password123')
    assert user_id is not None
    assert isinstance(user_id, int)


def test_authenticate_user(setup_database):
    """Test user authentication against database."""
    database.create_user('testuser', 'password123')
    user_id = database.authenticate_user('testuser', 'password123')
    assert user_id is not None


def test_hash_password(setup_database):
    """Hashes use Argon2id (PHC format) with random salt: never equal each other."""
    password = 'testpassword'
    hashed = database.hash_password(password)
    assert hashed != password
    assert isinstance(hashed, str)
    assert hashed.startswith('$argon2')
    # Each hash should be unique due to random salt
    assert hashed != database.hash_password(password)


def test_verify_password(setup_database):
    """Argon2 hashes verify correctly and reject wrong passwords."""
    password = 'testpassword'
    hashed = database.hash_password(password)
    assert database.verify_password(password, hashed)
    assert not database.verify_password('wrongpassword', hashed)


def test_verify_legacy_sha256_password(setup_database):
    """Legacy unsalted SHA-256 hashes still verify so existing users can log in."""
    import hashlib

    password = 'legacy-user-password'
    legacy_hash = hashlib.sha256(password.encode()).hexdigest()
    assert database.verify_password(password, legacy_hash)
    assert not database.verify_password('wrong', legacy_hash)


def test_authenticate_upgrades_legacy_hash(setup_database):
    """Authenticating with a legacy SHA-256 hash silently rehashes to Argon2."""
    import hashlib

    username = 'legacy_user'
    password = 'legacy-pass-123'
    legacy_hash = hashlib.sha256(password.encode()).hexdigest()

    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users_v2 (username, password_hash, base_currency, created_at) "
            "VALUES (?, ?, 'EUR', CURRENT_TIMESTAMP)",
            (username, legacy_hash),
        )
        user_id = cursor.lastrowid

    assert database.authenticate_user(username, password) == user_id

    # The stored hash should now be Argon2id, not the original SHA-256
    user = database.get_user_by_id(user_id)
    assert user['password_hash'].startswith('$argon2')
    assert user['password_hash'] != legacy_hash


def test_get_user_by_id(setup_database):
    """Test retrieving user by ID."""
    user_id = database.create_user('testuser', 'password123')
    user = database.get_user_by_id(user_id)
    assert user is not None
    assert user['username'] == 'testuser'


def test_duplicate_username(setup_database):
    """Test preventing duplicate usernames."""
    database.create_user('testuser', 'password123')
    result = database.create_user('testuser', 'differentpass')
    assert result is None


def test_create_user_creates_default_account(setup_database):
    """create_user must also seed a default EUR account so transactions can attach."""
    user_id = database.create_user('alice', 'pw123')
    assert user_id is not None
    with database.get_db() as conn:
        rows = conn.execute(
            'SELECT name, currency FROM accounts WHERE user_id = ?', (user_id,)
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]['name'] == 'Default'
    assert rows[0]['currency'] == 'EUR'


def test_drop_all_clears_v1_tables(setup_database):
    """drop_all_users_and_data wipes both legacy and v1 tables."""
    user_id = database.create_user('bob', 'pw123')
    with database.get_db() as conn:
        # Insert a transaction directly via raw SQL to verify drop covers it
        conn.execute(
            "INSERT INTO transactions (user_id, account_id, date, original_amount, "
            "original_currency, base_amount, type, created_at, updated_at) "
            "VALUES (?, (SELECT id FROM accounts WHERE user_id = ? LIMIT 1), "
            "'2026-04-10', 10.0, 'EUR', 10.0, 'expense', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (user_id, user_id),
        )

    database.drop_all_users_and_data()

    with database.get_db() as conn:
        for table in ('users_v2', 'accounts', 'transactions'):
            count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            assert count == 0, f'{table} not cleared'

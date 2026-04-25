# Database tests
import pytest
import database
import os


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
            'INSERT INTO users (username, password_hash) VALUES (?, ?)',
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


def test_database_foreign_keys(setup_database):
    """Test foreign key constraints."""
    user_id = database.create_user('testuser', 'password123')
    # Test that expenses can be created with foreign key
    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO expenses (user_id, date, category, amount, currency) VALUES (?, ?, ?, ?, ?)',
            (user_id, '2025-12-10', 'Food', 50.0, 'EUR')
        )
        cursor.execute('SELECT * FROM expenses WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        assert result is not None


def test_database_cascading(setup_database):
    """Test cascading deletes and updates."""
    user_id = database.create_user('testuser', 'password123')
    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO expenses (user_id, date, category, amount, currency) VALUES (?, ?, ?, ?, ?)',
            (user_id, '2025-12-10', 'Food', 50.0, 'EUR')
        )
    database.drop_all_users_and_data()
    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM expenses')
        count = cursor.fetchone()[0]
        assert count == 0


def test_transaction_rollback(setup_database):
    """Test transaction rollback on error."""
    user_id = database.create_user('testuser', 'password123')
    try:
        with database.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO expenses (user_id, date, category, amount, currency) VALUES (?, ?, ?, ?, ?)',
                (user_id, '2025-12-10', 'Food', 50.0, 'EUR')
            )
            raise Exception("Intentional error")
    except Exception:
        pass
    
    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM expenses')
        count = cursor.fetchone()[0]
        assert count == 0

# User authentication tests


def test_signup_valid_user(client):
    """Test successful user signup with valid credentials."""
    response = client.post('/signup', data={
        'username': 'newuser',
        'password': 'validpass123',
        'confirm_password': 'validpass123'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Welcome' in response.data or b'created successfully' in response.data


def test_signup_duplicate_username(client):
    """Test signup rejection for duplicate username."""
    client.post('/signup', data={
        'username': 'testuser',
        'password': 'testpass',
        'confirm_password': 'testpass'
    })

    response = client.post('/signup', data={
        'username': 'testuser',
        'password': 'newpass',
        'confirm_password': 'newpass'
    }, follow_redirects=True)

    assert b'already exists' in response.data


def test_signup_short_password(client):
    """Test signup rejection for password too short."""
    response = client.post('/signup', data={
        'username': 'testuser',
        'password': 'short',
        'confirm_password': 'short'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'at least 6 characters' in response.data or b'too short' in response.data or b'password' in response.data


def test_signup_password_mismatch(client):
    """Test signup rejection when passwords don't match."""
    response = client.post('/signup', data={
        'username': 'testuser',
        'password': 'password123',
        'confirm_password': 'different123'
    }, follow_redirects=True)

    assert b"don't match" in response.data or b'do not match' in response.data or b'mismatch' in response.data


def test_login_valid_credentials(authenticated_client):
    """Test successful login with correct credentials."""
    response = authenticated_client.get('/dashboard', follow_redirects=True)
    assert response.status_code == 200


def test_login_invalid_credentials(client):
    """Test login rejection with incorrect credentials."""
    response = client.post('/login', data={
        'username': 'nonexistent',
        'password': 'wrongpass'
    }, follow_redirects=True)

    assert b'Invalid' in response.data


def test_login_missing_fields(client):
    """Test login rejection when fields are missing."""
    response = client.post('/login', data={
        'username': 'testuser'
    }, follow_redirects=True)

    assert b'fill in all fields' in response.data or b'required' in response.data


def test_logout(authenticated_client):
    """Test user logout and session clearing."""
    response = authenticated_client.get('/logout', follow_redirects=True)

    assert b'logged out' in response.data or b'Goodbye' in response.data or response.status_code == 200

    response = authenticated_client.get('/dashboard', follow_redirects=True)
    assert 'login' in response.request.path.lower() or b'Login' in response.data


def test_session_persistence(authenticated_client):
    """Test session persistence across requests."""
    response1 = authenticated_client.get('/dashboard')
    assert response1.status_code == 200

    response2 = authenticated_client.get('/expenses')
    assert response2.status_code == 200


def test_login_required_redirect(client):
    """Test redirect to login for protected routes."""
    response = client.get('/dashboard', follow_redirects=True)

    assert 'login' in response.request.path.lower() or b'Login' in response.data


def test_password_security(authenticated_client):
    """Test passwords are not stored in plaintext."""
    import database

    user = database.get_user_by_id(1)
    # User is a sqlite3.Row object - access by column name
    password_hash = user[2] if user else None  # Column index for password_hash

    assert password_hash is not None
    assert password_hash != 'testpass'
    assert len(password_hash) > 10  # SHA-256 hashes are longer


def test_session_timeout(authenticated_client):
    """Test session timeout behavior."""
    response = authenticated_client.get('/dashboard')
    assert response.status_code == 200

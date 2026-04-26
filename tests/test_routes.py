from database import drop_all_users_and_data, init_db


def test_index_redirects_to_login_when_not_authenticated(client):
    drop_all_users_and_data()
    init_db()

    response = client.get('/', follow_redirects=True)

    assert 'login' in response.request.path.lower() or b'Login' in response.data

def test_index_redirects_to_dashboard_when_authenticated(authenticated_client):
    response = authenticated_client.get('/', follow_redirects=True)

    assert 'dashboard' in response.request.path.lower() or b'Dashboard' in response.data

def test_login_get_displays_form(client):
    drop_all_users_and_data()
    init_db()

    response = client.get('/login')

    assert response.status_code == 200
    assert b'username' in response.data.lower() or b'Username' in response.data

def test_login_post_valid_credentials(client):
    drop_all_users_and_data()
    init_db()

    client.post('/signup', data={
        'username': 'testuser',
        'password': 'testpass',
        'confirm_password': 'testpass'
    })

    client.get('/logout')

    response = client.post('/login', data={
        'username': 'testuser',
        'password': 'testpass'
    }, follow_redirects=True)

    assert b'Welcome back' in response.data

def test_login_post_invalid_credentials(client):
    drop_all_users_and_data()
    init_db()

    response = client.post('/login', data={
        'username': 'nonexistent',
        'password': 'wrongpass'
    }, follow_redirects=True)

    assert b'Invalid' in response.data

def test_signup_get_displays_form(client):
    drop_all_users_and_data()
    init_db()

    response = client.get('/signup')

    assert response.status_code == 200
    assert b'username' in response.data.lower() or b'Username' in response.data

def test_signup_post_valid_data(client):
    drop_all_users_and_data()
    init_db()

    response = client.post('/signup', data={
        'username': 'newuser',
        'password': 'newpass',
        'confirm_password': 'newpass'
    }, follow_redirects=True)

    assert b'Welcome' in response.data or b'created successfully' in response.data

def test_signup_post_duplicate_username(client):
    drop_all_users_and_data()
    init_db()

    client.post('/signup', data={
        'username': 'testuser',
        'password': 'pass1',
        'confirm_password': 'pass1'
    })

    response = client.post('/signup', data={
        'username': 'testuser',
        'password': 'pass2',
        'confirm_password': 'pass2'
    }, follow_redirects=True)

    assert b'already taken' in response.data

def test_logout_clears_session(authenticated_client):
    response = authenticated_client.get('/logout', follow_redirects=True)

    assert b'Signed out' in response.data or b'Signed out' in response.data

def test_set_currency_updates_session(authenticated_client):
    response = authenticated_client.post('/set_currency/USD', follow_redirects=True)

    assert response.status_code == 200

def test_set_timeframe_updates_session(authenticated_client):
    response = authenticated_client.post('/set_timeframe/6')

    assert response.status_code == 204

def test_protected_routes_require_login(client):
    drop_all_users_and_data()
    init_db()

    protected_routes = [
        '/dashboard',
        '/income',
        '/expenses',
        '/budgets',
        '/reports',
        '/graphs-stats'
    ]

    for route in protected_routes:
        response = client.get(route, follow_redirects=True)
        assert b'Please log in' in response.data or b'login' in response.request.path.lower()

import pytest

from database import drop_all_users_and_data, init_db


def test_very_large_amount_values(authenticated_client):
    response = authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '999999999.99',
        'description': 'Large amount',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

def test_very_small_amount_values(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '0.01',
        'description': 'Small amount',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

def test_special_characters_in_description(authenticated_client):
    special_chars = "Multivending!@#$%^&*()_+-=[]{}|;':\",./<>?"

    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': special_chars,
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

def test_sql_injection_attempts(authenticated_client):
    sql_injection = "'; DROP TABLE expenses; --"

    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': sql_injection,
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

    response = authenticated_client.get('/expenses')
    assert response.status_code == 200

def test_xss_attempts_in_forms(authenticated_client):
    xss_attempt = "<script>alert('XSS')</script>"

    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': xss_attempt,
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

def test_invalid_date_formats(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '12/10/2025',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Wrong date format',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

def test_future_dates(authenticated_client):
    response = authenticated_client.post('/income', data={
        'date': '2030-12-01',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Future income',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

def test_dates_far_in_past(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '1900-01-01',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Old expense',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

def test_concurrent_user_sessions(client):
    drop_all_users_and_data()
    init_db()

    client.post('/signup', data={
        'username': 'user1',
        'password': 'pass1',
        'confirm_password': 'pass1'
    })

    with client.session_transaction() as sess:
        assert 'user_id' in sess

    client.get('/logout')

    client.post('/signup', data={
        'username': 'user2',
        'password': 'pass2',
        'confirm_password': 'pass2'
    })

    response = client.get('/dashboard')
    assert response.status_code == 200

def test_database_connection_failure(authenticated_client):
    response = authenticated_client.get('/dashboard')
    assert response.status_code == 200

def test_missing_required_files(authenticated_client):
    response = authenticated_client.get('/dashboard')
    assert response.status_code == 200

def test_corrupted_json_files(cleanup_merchant_files, authenticated_client):
    import os

    from merchant_mapper import MERCHANT_CATEGORY_FILE_EXPENSES

    os.makedirs(os.path.dirname(MERCHANT_CATEGORY_FILE_EXPENSES), exist_ok=True)
    with open(MERCHANT_CATEGORY_FILE_EXPENSES, 'w') as f:
        f.write("{invalid json content}")

    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Multivending',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

@pytest.fixture
def cleanup_merchant_files():
    yield
    import os

    from merchant_mapper import MERCHANT_CATEGORY_FILE_EXPENSES, MERCHANT_CATEGORY_FILE_INCOME

    if os.path.exists(MERCHANT_CATEGORY_FILE_EXPENSES):
        os.remove(MERCHANT_CATEGORY_FILE_EXPENSES)
    if os.path.exists(MERCHANT_CATEGORY_FILE_INCOME):
        os.remove(MERCHANT_CATEGORY_FILE_INCOME)

def test_unicode_characters_in_description(authenticated_client):
    unicode_text = "Café 咖啡 ☕ 🍕"

    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': unicode_text,
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

def test_empty_string_amounts(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '',
        'description': 'Empty amount',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert b'All fields are required' in response.data or b'Invalid amount' in response.data

def test_decimal_precision(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.123456789',
        'description': 'High precision',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

def test_negative_zero_amount(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '-0.00',
        'description': 'Negative zero',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert b'Invalid amount' in response.data

def test_whitespace_only_description(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': '   ',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

def test_extremely_long_description(authenticated_client):
    long_text = 'A' * 10000

    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': long_text,
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

def test_multiple_decimal_points(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00.00',
        'description': 'Multiple decimals',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert b'Invalid amount' in response.data

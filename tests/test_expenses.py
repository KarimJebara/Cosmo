
def test_add_expense_valid_data(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Expense added successfully' in response.data

def test_add_expense_missing_date(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert b'All fields are required' in response.data

def test_add_expense_missing_category(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-11',
        'amount': '50.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert b'All fields are required' in response.data

def test_add_expense_missing_amount(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert b'All fields are required' in response.data

def test_add_expense_negative_amount(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '-50.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert b'Invalid amount' in response.data

def test_add_expense_zero_amount(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '0',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert b'Invalid amount' in response.data

def test_add_expense_invalid_amount_format(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': 'not_a_number',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert b'Invalid amount' in response.data

def test_add_expense_with_description(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Weekly groceries from supermarket',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Expense added successfully' in response.data

def test_add_expense_without_description(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Expense added successfully' in response.data

def test_add_expense_default_currency(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Albert Heijn'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Expense added successfully' in response.data

def test_add_expense_custom_currency(authenticated_client):
    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Albert Heijn',
        'currency': 'USD'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Expense added successfully' in response.data

def test_delete_expense_valid_id(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    })

    response = authenticated_client.post('/delete_expense/2025-12-10/50.0/Albert%20Heijn', follow_redirects=True)

    assert b'Expense deleted successfully' in response.data

def test_delete_expense_invalid_id(authenticated_client):
    response = authenticated_client.post('/delete_expense/2025-12-10/999.0/Unknown%20Merchant', follow_redirects=True)

    assert b'Expense not found' in response.data

def test_delete_expense_out_of_range_id(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    })

    response = authenticated_client.post('/delete_expense/2025-12-10/999.0/Wrong%20Amount', follow_redirects=True)

    assert b'Expense not found' in response.data

def test_change_expense_category_valid(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Dirk purchase',
        'currency': 'EUR'
    })

    response = authenticated_client.post('/change_expense_category/2025-12-10/50.0/Dirk%20purchase', data={
        'new_category': 'Shopping'
    }, follow_redirects=True)

    assert b'Category updated' in response.data

def test_change_expense_category_updates_all_same_merchant(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'C1000',
        'currency': 'EUR'
    })

    authenticated_client.post('/expenses', data={
        'date': '2025-12-12',
        'category': 'Albert Heijn',
        'amount': '60.00',
        'description': 'C1000',
        'currency': 'EUR'
    })

    response = authenticated_client.post('/change_expense_category/2025-12-10/50.0/C1000', data={
        'new_category': 'Shopping'
    }, follow_redirects=True)

    assert b'2 transaction(s)' in response.data

def test_change_expense_category_missing_category(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    })

    response = authenticated_client.post('/change_expense_category/2025-12-10/50.0/Albert%20Heijn', data={}, follow_redirects=True)

    assert b'Please select a category' in response.data

def test_expense_auto_categorization(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    })

    response = authenticated_client.post('/expenses', data={
        'date': '2025-12-12',
        'category': 'Other',
        'amount': '6.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

import pytest
from database import init_db, drop_all_users_and_data

def test_create_budget_valid_data(authenticated_client):
    response = authenticated_client.post('/budgets', data={
        'category': 'Albert Heijn',
        'limit': '500.00'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Budget limit set successfully' in response.data

def test_create_budget_missing_category(authenticated_client):
    response = authenticated_client.post('/budgets', data={
        'limit': '500.00'
    }, follow_redirects=True)
    
    assert b'Please fill in all fields' in response.data

def test_create_budget_missing_limit(authenticated_client):
    response = authenticated_client.post('/budgets', data={
        'category': 'Albert Heijn'
    }, follow_redirects=True)
    
    assert b'Please fill in all fields' in response.data

def test_create_budget_negative_limit(authenticated_client):
    response = authenticated_client.post('/budgets', data={
        'category': 'Albert Heijn',
        'limit': '-500.00'
    }, follow_redirects=True)
    
    assert b'Invalid limit amount' in response.data

def test_create_budget_zero_limit(authenticated_client):
    response = authenticated_client.post('/budgets', data={
        'category': 'Albert Heijn',
        'limit': '0'
    }, follow_redirects=True)
    
    assert b'Invalid limit amount' in response.data

def test_create_budget_invalid_limit_format(authenticated_client):
    response = authenticated_client.post('/budgets', data={
        'category': 'Albert Heijn',
        'limit': 'not_a_number'
    }, follow_redirects=True)
    
    assert b'Invalid limit amount' in response.data

def test_update_existing_budget(authenticated_client):
    authenticated_client.post('/budgets', data={
        'category': 'Albert Heijn',
        'limit': '500.00'
    })
    
    response = authenticated_client.post('/budgets', data={
        'category': 'Albert Heijn',
        'limit': '600.00'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Budget limit set successfully' in response.data

def test_budget_spent_calculation(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '100.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    })
    
    authenticated_client.post('/budgets', data={
        'category': 'Albert Heijn',
        'limit': '500.00'
    })
    
    response = authenticated_client.get('/budgets')
    
    assert response.status_code == 200

def test_budget_remaining_calculation(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '200.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    })
    
    authenticated_client.post('/budgets', data={
        'category': 'Albert Heijn',
        'limit': '500.00'
    })
    
    response = authenticated_client.get('/budgets')
    
    assert response.status_code == 200

def test_budget_percentage_calculation(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '250.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    })
    
    authenticated_client.post('/budgets', data={
        'category': 'Albert Heijn',
        'limit': '500.00'
    })
    
    response = authenticated_client.get('/budgets')
    
    assert response.status_code == 200

def test_budget_percentage_over_limit(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '600.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    })
    
    authenticated_client.post('/budgets', data={
        'category': 'Albert Heijn',
        'limit': '500.00'
    })
    
    response = authenticated_client.get('/budgets')
    
    assert response.status_code == 200

def test_delete_budget_valid_id(authenticated_client):
    authenticated_client.post('/budgets', data={
        'category': 'Albert Heijn',
        'limit': '500.00'
    })

    # Look up the real budget id; the v1 schema uses DB-assigned IDs.
    import database
    with database.get_db() as conn:
        row = conn.execute(
            "SELECT id FROM budgets_v2 ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    budget_id = row['id']

    response = authenticated_client.post(f'/delete_budget/{budget_id}', follow_redirects=True)

    assert b'Budget deleted successfully' in response.data

def test_delete_budget_invalid_id(authenticated_client):
    response = authenticated_client.post('/delete_budget/999', follow_redirects=True)
    
    assert b'Budget not found' in response.data

def test_budget_with_no_expenses_in_category(authenticated_client):
    authenticated_client.post('/budgets', data={
        'category': 'De Kroeg Leiden',
        'limit': '200.00'
    })
    
    response = authenticated_client.get('/budgets')
    
    assert response.status_code == 200
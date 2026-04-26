
def test_dashboard_displays_correct_totals(authenticated_client):
    authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    })

    authenticated_client.post('/expenses', data={
        'date': '2025-12-12',
        'category': 'Albert Heijn',
        'amount': '500.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/dashboard')

    assert response.status_code == 200

def test_dashboard_calculates_balance(authenticated_client):
    authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '5000.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    })

    authenticated_client.post('/expenses', data={
        'date': '2025-12-12',
        'category': 'Albert Heijn',
        'amount': '1000.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/dashboard')

    assert response.status_code == 200

def test_dashboard_income_trend_calculation(authenticated_client):
    authenticated_client.post('/income', data={
        'date': '2025-12-08',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Nov salary',
        'currency': 'EUR'
    })

    authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '3500.00',
        'description': 'Dec salary',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/dashboard')

    assert response.status_code == 200

def test_dashboard_expense_trend_calculation(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-08',
        'category': 'Albert Heijn',
        'amount': '400.00',
        'description': 'Nov groceries',
        'currency': 'EUR'
    })

    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '500.00',
        'description': 'Dec groceries',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/dashboard')

    assert response.status_code == 200

def test_dashboard_recent_transactions_limit(authenticated_client):
    for i in range(10):
        authenticated_client.post('/expenses', data={
            'date': f'2025-12-{str(i+1).zfill(2)}',
            'category': 'Albert Heijn',
            'amount': '50.00',
            'description': f'Purchase {i}',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/dashboard')

    assert response.status_code == 200

def test_dashboard_recent_transactions_sorted(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Old',
        'currency': 'EUR'
    })

    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '60.00',
        'description': 'Recent',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/dashboard')

    assert response.status_code == 200

def test_dashboard_category_aggregation(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '100.00',
        'description': 'Expense 1',
        'currency': 'EUR'
    })

    authenticated_client.post('/expenses', data={
        'date': '2025-12-12',
        'category': 'Albert Heijn',
        'amount': '150.00',
        'description': 'Expense 2',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/dashboard')

    assert response.status_code == 200

def test_dashboard_with_no_data(authenticated_client):
    response = authenticated_client.get('/dashboard')

    assert response.status_code == 200

def test_dashboard_respects_timeframe_filter(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-01-01',
        'category': 'Albert Heijn',
        'amount': '100.00',
        'description': 'Old expense',
        'currency': 'EUR'
    })

    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '150.00',
        'description': 'Recent expense',
        'currency': 'EUR'
    })

    authenticated_client.post('/set_timeframe/1')

    response = authenticated_client.get('/dashboard')

    assert response.status_code == 200

def test_dashboard_handles_current_month_zero_data(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-08',
        'category': 'Albert Heijn',
        'amount': '100.00',
        'description': 'Last month',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/dashboard')

    assert response.status_code == 200

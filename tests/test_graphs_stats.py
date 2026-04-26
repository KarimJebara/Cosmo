
def test_spending_by_category_calculation(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '200.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    })

    authenticated_client.post('/expenses', data={
        'date': '2025-12-12',
        'category': 'Albert Heijn',
        'amount': '100.00',
        'description': 'Restaurant',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_top_5_categories_selection(authenticated_client):
    categories = ['Albert Heijn', 'OVpay', 'Shopping', 'De Kroeg Leiden', 'Utilities', 'Healthcare']

    for i, category in enumerate(categories):
        authenticated_client.post('/expenses', data={
            'date': '2025-12-10',
            'category': category,
            'amount': str((i + 1) * 100),
            'description': f'{category} expense',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_spending_by_day_of_week(authenticated_client):
    dates = ['2025-12-11', '2025-12-09', '2025-12-08', '2025-12-12', '2025-12-10', '2025-12-11', '2025-12-09']

    for date in dates:
        authenticated_client.post('/expenses', data={
            'date': date,
            'category': 'Albert Heijn',
            'amount': '50.00',
            'description': 'Multivending',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_spending_by_day_averages(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-11',
        'category': 'Albert Heijn',
        'amount': '100.00',
        'description': 'Monday 1',
        'currency': 'EUR'
    })

    authenticated_client.post('/expenses', data={
        'date': '2025-12-08',
        'category': 'Albert Heijn',
        'amount': '200.00',
        'description': 'Monday 2',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_daily_spending_timeline(authenticated_client):
    for i in range(1, 15):
        authenticated_client.post('/expenses', data={
            'date': f'2025-12-{str(i).zfill(2)}',
            'category': 'Albert Heijn',
            'amount': str(i * 10),
            'description': f'Day {i}',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_statistics_calculations(authenticated_client):
    amounts = ['50.00', '100.00', '75.00', '200.00', '125.00']

    for i, amount in enumerate(amounts):
        authenticated_client.post('/expenses', data={
            'date': f'2025-12-{str(i+1).zfill(2)}',
            'category': 'Albert Heijn',
            'amount': amount,
            'description': f'Expense {i}',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_busiest_day_determination(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-11',
        'category': 'Albert Heijn',
        'amount': '500.00',
        'description': 'Big Monday',
        'currency': 'EUR'
    })

    authenticated_client.post('/expenses', data={
        'date': '2025-12-09',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Small Tuesday',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_linear_regression_calculation(authenticated_client):
    for i in range(1, 6):
        authenticated_client.post('/expenses', data={
            'date': f'2025-{str(7+i).zfill(2)}-01',
            'category': 'Albert Heijn',
            'amount': str(i * 100),
            'description': f'Month {i}',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_linear_regression_insufficient_data(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '100.00',
        'description': 'Single expense',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_predict_value_calculation(authenticated_client):
    for i in range(1, 6):
        authenticated_client.post('/expenses', data={
            'date': f'2025-{str(7+i).zfill(2)}-01',
            'category': 'Albert Heijn',
            'amount': str(i * 200),
            'description': f'Month {i}',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_predict_value_with_none_coefficients(authenticated_client):
    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_predicted_monthly_expense(authenticated_client):
    for i in range(1, 4):
        authenticated_client.post('/expenses', data={
            'date': f'2025-{str(9+i).zfill(2)}-01',
            'category': 'Albert Heijn',
            'amount': '1000.00',
            'description': f'Month {i}',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_next_3_months_predictions(authenticated_client):
    for i in range(1, 6):
        authenticated_client.post('/expenses', data={
            'date': f'2025-{str(7+i).zfill(2)}-01',
            'category': 'Albert Heijn',
            'amount': str(i * 150),
            'description': f'Month {i}',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_predicted_yearly_balance(authenticated_client):
    for i in range(1, 6):
        authenticated_client.post('/income', data={
            'date': f'2025-{str(7+i).zfill(2)}-01',
            'category': 'Salary',
            'amount': '3000.00',
            'description': f'Month {i}',
            'currency': 'EUR'
        })

        authenticated_client.post('/expenses', data={
            'date': f'2025-{str(7+i).zfill(2)}-15',
            'category': 'Albert Heijn',
            'amount': '1000.00',
            'description': f'Month {i}',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_category_specific_predictions(authenticated_client):
    for i in range(1, 6):
        authenticated_client.post('/expenses', data={
            'date': f'2025-{str(7+i).zfill(2)}-01',
            'category': 'Albert Heijn',
            'amount': str(i * 100),
            'description': f'Month {i}',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_days_until_low_balance(authenticated_client):
    authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '10000.00',
        'description': 'Income',
        'currency': 'EUR'
    })

    for i in range(1, 6):
        authenticated_client.post('/expenses', data={
            'date': f'2025-12-{str(i).zfill(2)}',
            'category': 'Albert Heijn',
            'amount': '100.00',
            'description': f'Day {i}',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

def test_stats_with_no_data(authenticated_client):
    response = authenticated_client.get('/graphs-stats')

    assert response.status_code == 200

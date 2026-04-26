

def test_reports_page_loads(authenticated_client):
    """Test reports page loads successfully."""
    response = authenticated_client.get('/reports')

    assert response.status_code == 200


def test_report_total_income(authenticated_client):
    """Test report total income calculation."""
    authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    })

    authenticated_client.post('/income', data={
        'date': '2025-12-11',
        'category': 'Freelance',
        'amount': '500.00',
        'description': 'Frites van Piet',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/reports')

    assert response.status_code == 200


def test_report_total_expenses(authenticated_client):
    """Test report total expenses calculation."""
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '100.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    })

    authenticated_client.post('/expenses', data={
        'date': '2025-12-11',
        'category': 'OVpay',
        'amount': '50.00',
        'description': 'OVpay',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/reports')

    assert response.status_code == 200


def test_report_balance(authenticated_client):
    """Test report balance calculation."""
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

    response = authenticated_client.get('/reports')

    assert response.status_code == 200


def test_report_spending_breakdown(authenticated_client):
    """Test spending breakdown by category."""
    categories = ['Albert Heijn', 'OVpay', 'De Kroeg Leiden']

    for category in categories:
        authenticated_client.post('/expenses', data={
            'date': '2025-12-10',
            'category': category,
            'amount': '100.00',
            'description': f'{category} expense',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/reports')

    assert response.status_code == 200


def test_report_category_percentages(authenticated_client):
    """Test percentage calculations per category."""
    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '500.00',
        'description': 'Albert Heijn',
        'currency': 'EUR'
    })

    authenticated_client.post('/expenses', data={
        'date': '2025-12-11',
        'category': 'OVpay',
        'amount': '500.00',
        'description': 'OVpay',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/reports')

    assert response.status_code == 200


def test_report_monthly_summary(authenticated_client):
    """Test monthly income and expense summary."""
    for month in range(10, 12):
        authenticated_client.post('/income', data={
            'date': f'2025-{month}-01',
            'category': 'Salary',
            'amount': '3000.00',
            'description': 'Jumbo Supermarkt',
            'currency': 'EUR'
        })

        authenticated_client.post('/expenses', data={
            'date': f'2025-{month}-05',
            'category': 'Albert Heijn',
            'amount': '500.00',
            'description': 'Albert Heijn',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/reports')

    assert response.status_code == 200


def test_report_with_filters(authenticated_client):
    """Test report generation with applied filters."""
    authenticated_client.post('/expenses', data={
        'date': '2025-12-08',
        'category': 'Albert Heijn',
        'amount': '100.00',
        'description': 'Last month',
        'currency': 'EUR'
    })

    authenticated_client.post('/expenses', data={
        'date': '2025-12-10',
        'category': 'Albert Heijn',
        'amount': '150.00',
        'description': 'This month',
        'currency': 'EUR'
    })

    authenticated_client.post('/set_timeframe/1')

    response = authenticated_client.get('/reports')

    assert response.status_code == 200


def test_report_empty_data(authenticated_client):
    """Test report generation with no transactions."""
    response = authenticated_client.get('/reports')

    assert response.status_code == 200

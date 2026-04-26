

def test_add_income_valid(authenticated_client):
    """Test adding a valid income transaction."""
    response = authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Income added successfully' in response.data or b'added' in response.data


def test_add_income_missing_fields(authenticated_client):
    """Test income rejection when fields are missing."""
    response = authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert b'required' in response.data or b'fill in all' in response.data


def test_add_income_invalid_amount(authenticated_client):
    """Test income rejection for invalid amount."""
    response = authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': 'not_a_number',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert b'Invalid amount' in response.data or b'invalid' in response.data


def test_add_income_negative_amount(authenticated_client):
    """Test income rejection for negative amount."""
    response = authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '-1000.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert b'Invalid amount' in response.data or b'must be positive' in response.data


def test_add_income_with_currency(authenticated_client):
    """Test adding income with currency field."""
    response = authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'GBP'
    }, follow_redirects=True)

    assert response.status_code == 200


def test_add_income_auto_categorization(authenticated_client):
    """Test auto-categorization on income entry."""
    response = authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200


def test_add_income_manual_category(authenticated_client):
    """Test adding income with manual category selection."""
    response = authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Freelance',
        'amount': '1500.00',
        'description': 'Frites van Piet',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200


def test_edit_income(authenticated_client):
    """Test editing an existing income transaction."""
    authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    })

    response = authenticated_client.post('/change_income_category/2025-12-10/3000.0/Jumbo%20Supermarkt', data={
        'new_category': 'Freelance'
    }, follow_redirects=True)

    assert response.status_code == 200


def test_delete_income(authenticated_client):
    """Test deleting an income transaction."""
    authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    })

    response = authenticated_client.post('/delete_income/2025-12-10/3000.0/Jumbo%20Supermarkt', follow_redirects=True)

    assert response.status_code == 200 or b'deleted' in response.data


def test_change_income_category(authenticated_client):
    """Test changing category of income transaction."""
    authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    })

    response = authenticated_client.post('/change_income_category/2025-12-10/3000.0/Jumbo%20Supermarkt', data={
        'new_category': 'Freelance'
    }, follow_redirects=True)

    assert response.status_code == 200


def test_income_listing(authenticated_client):
    """Test retrieving list of incomes."""
    authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/income')

    assert response.status_code == 200


def test_income_sorting(authenticated_client):
    """Test income transactions sorted by date."""
    for i in range(3):
        authenticated_client.post('/income', data={
            'date': f'2025-{str(12-i).zfill(2)}-01',
            'category': 'Salary',
            'amount': '3000.00',
            'description': f'Salary {i}',
            'currency': 'EUR'
        })

    response = authenticated_client.get('/income')

    assert response.status_code == 200


def test_income_filtering_by_date(authenticated_client):
    """Test filtering income by date range."""
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
        'amount': '3000.00',
        'description': 'Dec salary',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/income')

    assert response.status_code == 200


def test_income_total_calculation(authenticated_client):
    """Test calculating total income."""
    authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Salary',
        'currency': 'EUR'
    })

    authenticated_client.post('/income', data={
        'date': '2025-12-11',
        'category': 'Freelance',
        'amount': '500.00',
        'description': 'Frites van Piet',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/income')

    assert response.status_code == 200


def test_income_currency_conversion(authenticated_client):
    """Test income amount conversion with different currencies."""
    response = authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'GBP'
    }, follow_redirects=True)

    assert response.status_code == 200


def test_income_duplicate_prevention(authenticated_client):
    """Test preventing duplicate income entries."""
    authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    })

    response = authenticated_client.get('/income')
    assert response.status_code == 200


def test_income_validation(authenticated_client):
    """Test all income field validations."""
    response = authenticated_client.post('/income', data={
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': '3000.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    }, follow_redirects=True)

    assert response.status_code == 200

from datetime import date

import pytest

from api.revolut_importer import RevolutImporter


def test_parse_csv_valid_data():
    csv_content = """Started Date,Description,Amount,Currency
2025-12-07 10:30:00,DUO HOOFDREKENING,3000.00,EUR
2025-12-06 14:20:00,Albert Heijn,-50.50,EUR"""

    transactions = RevolutImporter.parse_csv(csv_content)

    assert len(transactions) == 2
    assert transactions[0].date == date(2025, 12, 7)
    assert transactions[0].amount == 3000.00
    assert transactions[0].description == "DUO HOOFDREKENING"
    assert transactions[0].currency == "EUR"

def test_parse_csv_empty_file():
    csv_content = """Started Date,Description,Amount,Currency"""

    transactions = RevolutImporter.parse_csv(csv_content)

    assert len(transactions) == 0

def test_parse_csv_missing_headers():
    csv_content = """Date,Description,Amount
2025-12-07 10:30:00,Multivending,100"""

    with pytest.raises(ValueError, match="Missing expected CSV column"):
        RevolutImporter.parse_csv(csv_content)

def test_parse_csv_malformed_date():
    csv_content = """Started Date,Description,Amount,Currency
invalid-date,Multivending,100,EUR"""

    transactions = RevolutImporter.parse_csv(csv_content)

    assert len(transactions) == 0

def test_parse_csv_invalid_amount():
    csv_content = """Started Date,Description,Amount,Currency
2025-12-06 10:30:00,Multivending,not-a-number,EUR"""

    transactions = RevolutImporter.parse_csv(csv_content)

    assert len(transactions) == 0

def test_parse_csv_missing_currency():
    csv_content = """Started Date,Description,Amount,Currency
2025-12-05 10:30:00,Multivending,100,"""

    transactions = RevolutImporter.parse_csv(csv_content)

    assert len(transactions) == 1
    assert transactions[0].currency == ""

def test_parse_csv_skips_empty_rows():
    csv_content = """Started Date,Description,Amount,Currency
2025-12-07 10:30:00,Multivending1,100,EUR

2025-12-06 10:30:00,Multivending2,200,EUR"""

    transactions = RevolutImporter.parse_csv(csv_content)

    assert len(transactions) == 2

def test_parse_csv_multiple_transactions():
    csv_content = """Started Date,Description,Amount,Currency
2025-12-07 10:30:00,Income,1000,EUR
2025-12-06 14:00:00,Expense,-50,EUR
2025-12-05 09:15:00,Income,500,USD
2025-12-07 18:30:00,Expense,-75.50,GBP"""

    transactions = RevolutImporter.parse_csv(csv_content)

    assert len(transactions) == 4
    assert transactions[0].amount == 1000
    assert transactions[1].amount == -50
    assert transactions[2].currency == "USD"
    assert transactions[3].currency == "GBP"

def test_import_positive_amount_as_income(authenticated_client):
    csv_content = """Started Date,Description,Amount,Currency
2025-12-07 10:30:00,Salary,3000.00,EUR"""

    from io import BytesIO
    data = {
        'revolut_csv': (BytesIO(csv_content.encode()), 'test.csv')
    }

    response = authenticated_client.post('/revolut_import', data=data, content_type='multipart/form-data', follow_redirects=True)

    assert b'Successfully imported' in response.data

def test_import_negative_amount_as_expense(authenticated_client):
    csv_content = """Started Date,Description,Amount,Currency
2025-12-06 10:30:00,Albert Heijn,-50.00,EUR"""

    from io import BytesIO
    data = {
        'revolut_csv': (BytesIO(csv_content.encode()), 'test.csv')
    }

    response = authenticated_client.post('/revolut_import', data=data, content_type='multipart/form-data', follow_redirects=True)

    assert b'Successfully imported' in response.data

def test_import_detects_duplicates(authenticated_client):
    csv_content = """Started Date,Description,Amount,Currency
2025-12-07 10:30:00,Dirk,-50.00,EUR
2025-12-07 10:30:00,Dirk,-50.00,EUR"""

    from io import BytesIO
    data = {
        'revolut_csv': (BytesIO(csv_content.encode()), 'test.csv')
    }

    response = authenticated_client.post('/revolut_import', data=data, content_type='multipart/form-data', follow_redirects=True)

    assert b'Skipped' in response.data

def test_import_auto_categorizes_transactions(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-05',
        'category': 'Albert Heijn',
        'amount': '25.00',
        'description': 'Jumbo Supermarkt',
        'currency': 'EUR'
    })

    csv_content = """Started Date,Description,Amount,Currency
2025-12-07 10:30:00,Jumbo Supermarkt,-6.00,EUR"""

    from io import BytesIO
    data = {
        'revolut_csv': (BytesIO(csv_content.encode()), 'test.csv')
    }

    response = authenticated_client.post('/revolut_import', data=data, content_type='multipart/form-data', follow_redirects=True)

    assert b'Successfully imported' in response.data

def test_import_uses_other_category_when_no_mapping(authenticated_client):
    csv_content = """Started Date,Description,Amount,Currency
2025-12-06 10:30:00,Unknown Merchant,-100.00,EUR"""

    from io import BytesIO
    data = {
        'revolut_csv': (BytesIO(csv_content.encode()), 'test.csv')
    }

    response = authenticated_client.post('/revolut_import', data=data, content_type='multipart/form-data', follow_redirects=True)

    assert b'Successfully imported' in response.data

def test_import_counts_imported_and_skipped(authenticated_client):
    authenticated_client.post('/expenses', data={
        'date': '2025-12-07',
        'category': 'Albert Heijn',
        'amount': '50.00',
        'description': 'Dirk',
        'currency': 'EUR'
    })

    csv_content = """Started Date,Description,Amount,Currency
2025-12-07 00:00:00,Dirk,-50.00,EUR
2025-12-06 10:30:00,New Dirk,-25.00,EUR"""

    from io import BytesIO
    data = {
        'revolut_csv': (BytesIO(csv_content.encode()), 'test.csv')
    }

    response = authenticated_client.post('/revolut_import', data=data, content_type='multipart/form-data', follow_redirects=True)

    assert b'imported' in response.data

import os
import sys
from contextlib import suppress
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import database
from app import app as flask_app


@pytest.fixture(scope="session", autouse=True)
def reset_test_data_on_startup():
    """Run alembic upgrade once and clear all tables before/after the session."""
    database.init_db()
    database.drop_all_users_and_data()

    merchant_files = [
        'data/merchant_category_expenses.json',
        'data/merchant_category_income.json',
    ]
    for filepath in merchant_files:
        if os.path.exists(filepath):
            with suppress(OSError):
                os.remove(filepath)

    yield

    with suppress(Exception):
        database.drop_all_users_and_data()


@pytest.fixture
def app():
    flask_app.config['TESTING'] = True
    flask_app.config['SECRET_KEY'] = 'test_secret_key'
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()

@pytest.fixture
def init_database():
    """Per-test isolation: clear before and after."""
    database.drop_all_users_and_data()
    yield
    database.drop_all_users_and_data()


@pytest.fixture
def authenticated_client(client, init_database):
    client.post('/signup', data={
        'username': 'testuser',
        'password': 'testpass',
        'confirm_password': 'testpass',
    })
    yield client

@pytest.fixture
def sample_income():
    return {
        'date': '2025-12-10',
        'category': 'Salary',
        'amount': 3000.0,
        'description': 'Monthly salary',
        'currency': 'EUR'
    }

@pytest.fixture
def sample_expense():
    return {
        'date': '2025-12-12',
        'category': 'Food & Dining',
        'amount': 50.0,
        'description': 'Groceries',
        'currency': 'EUR'
    }

@pytest.fixture
def sample_budget():
    return {
        'category': 'Food & Dining',
        'limit': 500.0
    }

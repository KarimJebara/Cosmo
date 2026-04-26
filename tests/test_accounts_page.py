"""Smoke tests for /accounts page and the create/archive flows."""

from __future__ import annotations

import database


def test_accounts_page_loads_with_default_account(authenticated_client):
    """A fresh user has the Default EUR account auto-created on signup."""
    response = authenticated_client.get('/accounts')
    assert response.status_code == 200
    assert b'Default' in response.data
    assert b'EUR' in response.data


def test_create_new_account(authenticated_client):
    response = authenticated_client.post(
        '/accounts',
        data={'name': 'UK Travel', 'currency': 'GBP', 'type': 'checking'},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b'UK Travel' in response.data
    assert b'GBP' in response.data


def test_create_account_validates_currency_code(authenticated_client):
    response = authenticated_client.post(
        '/accounts',
        data={'name': 'Bad', 'currency': 'NOT_A_CODE', 'type': 'checking'},
        follow_redirects=True,
    )
    assert b'Currency must be a 3-letter ISO code' in response.data


def test_archive_account(authenticated_client):
    authenticated_client.post(
        '/accounts',
        data={'name': 'TempAcc', 'currency': 'CHF', 'type': 'checking'},
    )

    with database.get_db() as conn:
        row = conn.execute(
            "SELECT id FROM accounts WHERE name = 'TempAcc'"
        ).fetchone()
    assert row is not None

    response = authenticated_client.post(
        f'/archive_account/{row["id"]}', follow_redirects=True
    )
    assert response.status_code == 200
    assert b'archived' in response.data.lower()

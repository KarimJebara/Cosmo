"""Smoke tests for the /rules page."""

from __future__ import annotations


def test_rules_page_loads_empty(authenticated_client):
    response = authenticated_client.get('/rules')
    assert response.status_code == 200
    assert b'No merchant rules yet' in response.data


def test_rules_page_shows_learned_rule(authenticated_client):
    """Adding an expense → re-categorizing it → /rules shows the rule."""
    authenticated_client.post('/expenses', data={
        'date': '2026-04-10',
        'category': 'Food',
        'amount': '12.50',
        'description': 'Tesco Stores 1234',
        'currency': 'EUR',
    })
    # Trigger the natural-key category change (legacy URL form).
    authenticated_client.post(
        '/change_expense_category/2026-04-10/12.5/Tesco Stores 1234',
        data={'new_category': 'Groceries'},
    )

    response = authenticated_client.get('/rules')
    assert response.status_code == 200
    # The normalizer drops the trailing terminal id; the rule should be
    # keyed on 'TESCO STORES'.
    assert b'TESCO STORES' in response.data
    assert b'Groceries' in response.data


def test_delete_rule(authenticated_client):
    import database
    authenticated_client.post('/expenses', data={
        'date': '2026-04-10',
        'category': 'Groceries',
        'amount': '12.50',
        'description': 'Tesco Stores',
        'currency': 'EUR',
    })

    with database.get_db() as conn:
        row = conn.execute(
            "SELECT id FROM merchant_rules ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    rule_id = row['id']

    response = authenticated_client.post(
        f'/delete_rule/{rule_id}', follow_redirects=True
    )
    assert response.status_code == 200
    assert b'Rule deleted' in response.data

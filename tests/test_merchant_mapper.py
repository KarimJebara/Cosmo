import pytest
import os
import json
from merchant_mapper import (
    load_merchant_categories,
    save_merchant_categories,
    update_merchant_category,
    get_category_for_merchant,
    auto_categorize_transaction,
    MERCHANT_CATEGORY_FILE_EXPENSES,
    MERCHANT_CATEGORY_FILE_INCOME
)

@pytest.fixture
def cleanup_merchant_files():
    yield
    if os.path.exists(MERCHANT_CATEGORY_FILE_EXPENSES):
        os.remove(MERCHANT_CATEGORY_FILE_EXPENSES)
    if os.path.exists(MERCHANT_CATEGORY_FILE_INCOME):
        os.remove(MERCHANT_CATEGORY_FILE_INCOME)

def test_load_merchant_categories_expenses(cleanup_merchant_files):
    test_data = {"Jumbo Supermarkt": "Shopping", "Albert Heijn": "Food & Dining"}
    os.makedirs(os.path.dirname(MERCHANT_CATEGORY_FILE_EXPENSES), exist_ok=True)
    with open(MERCHANT_CATEGORY_FILE_EXPENSES, 'w') as f:
        json.dump(test_data, f)
    
    result = load_merchant_categories('expenses')
    
    assert result == test_data

def test_load_merchant_categories_income(cleanup_merchant_files):
    test_data = {"Acme Corp": "Salary", "Freelance Client": "Freelance"}
    os.makedirs(os.path.dirname(MERCHANT_CATEGORY_FILE_INCOME), exist_ok=True)
    with open(MERCHANT_CATEGORY_FILE_INCOME, 'w') as f:
        json.dump(test_data, f)
    
    result = load_merchant_categories('income')
    
    assert result == test_data

def test_load_merchant_categories_missing_file(cleanup_merchant_files):
    if os.path.exists(MERCHANT_CATEGORY_FILE_EXPENSES):
        os.remove(MERCHANT_CATEGORY_FILE_EXPENSES)
    
    result = load_merchant_categories('expenses')
    
    assert result == {}

def test_load_merchant_categories_invalid_json(cleanup_merchant_files):
    os.makedirs(os.path.dirname(MERCHANT_CATEGORY_FILE_EXPENSES), exist_ok=True)
    with open(MERCHANT_CATEGORY_FILE_EXPENSES, 'w') as f:
        f.write("invalid json content")
    
    result = load_merchant_categories('expenses')
    
    assert result == {}

def test_save_merchant_categories_expenses(cleanup_merchant_files):
    test_data = {"Dirk": "Shopping", "Kruidvat": "Food & Dining"}
    
    save_merchant_categories(test_data, 'expenses')
    
    assert os.path.exists(MERCHANT_CATEGORY_FILE_EXPENSES)
    with open(MERCHANT_CATEGORY_FILE_EXPENSES, 'r') as f:
        saved_data = json.load(f)
    assert saved_data == test_data

def test_save_merchant_categories_income(cleanup_merchant_files):
    test_data = {"Company A": "Salary", "Side Gig": "Side Hustle"}
    
    save_merchant_categories(test_data, 'income')
    
    assert os.path.exists(MERCHANT_CATEGORY_FILE_INCOME)
    with open(MERCHANT_CATEGORY_FILE_INCOME, 'r') as f:
        saved_data = json.load(f)
    assert saved_data == test_data

def test_save_merchant_categories_creates_directory(cleanup_merchant_files, tmp_path, monkeypatch):
    """Ensure save_merchant_categories creates its parent dir if missing.

    Uses tmp_path so we don't blow away the real ./data/ directory (which
    contains budget_tracker.db and breaks every subsequent test).
    """
    target = tmp_path / "merchants" / "expenses.json"
    monkeypatch.setattr(
        "merchant_mapper.MERCHANT_CATEGORY_FILE_EXPENSES", str(target)
    )

    save_merchant_categories({"Test": "Category"}, 'expenses')

    assert target.exists()

def test_update_merchant_category_new_merchant(cleanup_merchant_files):
    update_merchant_category("New Store", "Shopping", 'expenses')
    
    merchants = load_merchant_categories('expenses')
    
    assert "New Store" in merchants
    assert merchants["New Store"] == "Shopping"

def test_update_merchant_category_existing_merchant(cleanup_merchant_files):
    update_merchant_category("Store", "Food & Dining", 'expenses')
    update_merchant_category("Store", "Shopping", 'expenses')
    
    merchants = load_merchant_categories('expenses')
    
    assert merchants["Store"] == "Shopping"

def test_update_merchant_category_empty_name(cleanup_merchant_files):
    update_merchant_category("", "Shopping", 'expenses')
    
    merchants = load_merchant_categories('expenses')
    
    assert "" not in merchants

def test_update_merchant_category_empty_category(cleanup_merchant_files):
    update_merchant_category("Store", "", 'expenses')
    
    merchants = load_merchant_categories('expenses')
    
    assert "Store" not in merchants

def test_get_category_for_merchant_exists(cleanup_merchant_files):
    update_merchant_category("Coolblue", "Shopping", 'expenses')
    
    category = get_category_for_merchant("Coolblue", 'expenses')
    
    assert category == "Shopping"

def test_get_category_for_merchant_not_exists(cleanup_merchant_files):
    category = get_category_for_merchant("Unknown Store", 'expenses')
    
    assert category is None

def test_get_category_for_merchant_empty_name(cleanup_merchant_files):
    category = get_category_for_merchant("", 'expenses')
    
    assert category is None

def test_auto_categorize_transaction_found(cleanup_merchant_files):
    update_merchant_category("Best Buy", "Shopping", 'expenses')
    
    category = auto_categorize_transaction("Best Buy", 'expenses')
    
    assert category == "Shopping"

def test_auto_categorize_transaction_not_found(cleanup_merchant_files):
    category = auto_categorize_transaction("Random Merchant", 'expenses')
    
    assert category is None
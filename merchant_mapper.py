import json
import logging
import os

logger = logging.getLogger(__name__)

# NOTE: Phase-3 of the cosmo-v1 plan replaces this module with cosmo/categorize/
# (per-user merchant_rules table, fuzzy matching via rapidfuzz, normalization).
# The current dict[str -> str] is GLOBAL ACROSS USERS — a critical bug that will
# be fixed in the migration. Do not extend this module.

MERCHANT_CATEGORY_FILE_INCOME = 'data/merchant_category_income.json'
MERCHANT_CATEGORY_FILE_EXPENSES = 'data/merchant_category_expenses.json'

def _get_merchant_file(transaction_type):
    """Get the appropriate merchant file path based on transaction type"""
    if transaction_type == 'income':
        return MERCHANT_CATEGORY_FILE_INCOME
    else:
        return MERCHANT_CATEGORY_FILE_EXPENSES

def _ensure_merchant_file_exists(transaction_type='expenses'):
    """
    Ensure merchant category file exists. If not, create it with empty dict.
    This is called automatically when files are needed.
    """
    merchant_file = _get_merchant_file(transaction_type)

    # If file already exists, nothing to do
    if os.path.exists(merchant_file):
        return

    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(merchant_file), exist_ok=True)

    # Create empty merchant categories file
    try:
        with open(merchant_file, 'w') as f:
            json.dump({}, f, indent=4)
    except OSError:
        logger.exception("Error creating merchant categories file %s", merchant_file)

def load_merchant_categories(transaction_type='expenses'):
    """
    Load merchant category mappings from JSON file.
    If file doesn't exist, it will be created automatically.
    """
    merchant_file = _get_merchant_file(transaction_type)

    # Ensure file exists before trying to load
    _ensure_merchant_file_exists(transaction_type)

    if not os.path.exists(merchant_file):
        return {}

    try:
        with open(merchant_file) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        # If file is corrupted, return empty dict
        return {}

def save_merchant_categories(merchant_dict, transaction_type='expenses'):
    """Save merchant category mappings to JSON file"""
    merchant_file = _get_merchant_file(transaction_type)

    # Ensure directory exists
    os.makedirs(os.path.dirname(merchant_file), exist_ok=True)

    try:
        with open(merchant_file, 'w') as f:
            json.dump(merchant_dict, f, indent=4)
    except OSError:
        logger.exception("Error saving merchant categories to %s", merchant_file)

def ensure_merchant_files_exist():
    """
    Ensure both merchant category files exist.
    Called during app initialization.
    """
    _ensure_merchant_file_exists('expenses')
    _ensure_merchant_file_exists('income')

def update_merchant_category(merchant_name, category, transaction_type='expenses'):
    """Update or add a merchant category mapping"""
    if not merchant_name or not category:
        return

    merchants = load_merchant_categories(transaction_type)
    merchants[merchant_name] = category
    save_merchant_categories(merchants, transaction_type)

def get_category_for_merchant(merchant_name, transaction_type='expenses'):
    """Get the category for a merchant, returns None if not found"""
    if not merchant_name:
        return None

    merchants = load_merchant_categories(transaction_type)
    return merchants.get(merchant_name)

def auto_categorize_transaction(description, transaction_type='expenses'):
    """
    Auto-categorize a transaction based on merchant name.
    Returns the category if found, None otherwise.
    """
    return get_category_for_merchant(description, transaction_type)

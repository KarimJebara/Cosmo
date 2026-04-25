import logging
from functools import lru_cache

import requests

logger = logging.getLogger(__name__)

EXCHANGE_RATES_URL = "https://api.exchangerate-api.com/v4/latest/EUR"


# NOTE: Phase-2 of the cosmo-v1 plan replaces this entire module with cosmo/fx/
# (DB-backed rate cache, historical rates, multi-provider fallback). The lru_cache
# below is a known footgun (rates never refresh in-process) and is preserved only
# until the new fx service ships. Do not extend this module.
@lru_cache(maxsize=32)
def get_exchange_rates():
    try:
        response = requests.get(EXCHANGE_RATES_URL, timeout=5)
        response.raise_for_status()
        return response.json().get('rates', {})
    except requests.RequestException:
        logger.exception("Failed to fetch exchange rates from %s", EXCHANGE_RATES_URL)
        return {}

def convert_to_eur(amount, from_currency):
    if from_currency == 'EUR':
        return amount
    
    if not amount:
        return 0
    
    rates = get_exchange_rates()
    if from_currency not in rates:
        return amount
    
    rate = rates[from_currency]
    return amount / rate

def format_currency(amount, currency='EUR'):
    if currency == 'EUR':
        return f'€{amount:.2f}'
    elif currency == 'GBP':
        return f'£{amount:.2f}'
    elif currency == 'USD':
        return f'${amount:.2f}'
    else:
        return f'{amount:.2f} {currency}'

def format_amount_with_conversion(amount, original_currency):
    if original_currency == 'EUR':
        return format_currency(amount, 'EUR')
    
    eur_amount = convert_to_eur(amount, original_currency)
    original_formatted = format_currency(amount, original_currency)
    eur_formatted = format_currency(eur_amount, 'EUR')
    
    return f'({original_formatted}) {eur_formatted}'

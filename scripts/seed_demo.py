"""Seed a 3 year realistic financial history for the demo user.

Story: Karim, software engineer based in Lisbon. Hired Jan 2023 at a
mid sized EU company (EUR salary). In Feb 2024 starts a UK side project
(GBP rental income from Manchester flat). In June 2024 picks up US
freelance contracts (USD). Took a Tokyo trip Oct 2024 (JPY).
Salary raises every Jan (5 percent each year). Recurring spend grows
with lifestyle. Several big one offs along the way.
"""

from __future__ import annotations

import http.cookiejar
import random
import urllib.parse
import urllib.request
from datetime import date, timedelta

random.seed(7)

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
BASE = "http://localhost:5002"


def post(path, **fields):
    data = urllib.parse.urlencode(fields).encode()
    op.open(urllib.request.Request(f"{BASE}{path}", data=data, method="POST"))


def signup_or_login(username, password):
    try:
        op.open(urllib.request.Request(f"{BASE}/signup", method="POST",
            data=urllib.parse.urlencode({"username": username, "password": password,
                                          "confirm_password": password}).encode()))
    except Exception:
        pass
    op.open(urllib.request.Request(f"{BASE}/login", method="POST",
        data=urllib.parse.urlencode({"username": username, "password": password}).encode()))


# ---- 1. Auth + accounts -----------------------------------------------------

signup_or_login("demo", "hunter2hunter2")

# Default EUR account auto created at signup. Add more accounts for the
# story arc.
post("/accounts", name="UK Manchester Flat", currency="GBP", type="checking")
post("/accounts", name="US Freelance",       currency="USD", type="checking")
post("/accounts", name="Travel JPY",         currency="JPY", type="checking")
post("/accounts", name="Emergency Fund",     currency="EUR", type="savings")
post("/accounts", name="Index Fund",         currency="EUR", type="savings")


# ---- 2. Three years of monthly salary with raises --------------------------

START = date(2023, 1, 1)
TODAY = date(2026, 4, 26)

salary_2023 = 4200
salary_2024 = round(salary_2023 * 1.05)   # 4410
salary_2025 = round(salary_2024 * 1.06)   # 4675
salary_2026 = round(salary_2025 * 1.05)   # 4909

salary_by_year = {
    2023: salary_2023,
    2024: salary_2024,
    2025: salary_2025,
    2026: salary_2026,
}

current = START
while current <= TODAY:
    pay_day = current.replace(day=27)
    if pay_day <= TODAY:
        post("/income",
             date=pay_day.isoformat(),
             category="Salary",
             description="Monthly salary",
             amount=str(salary_by_year[pay_day.year]),
             currency="EUR")
    # advance one month
    if current.month == 12:
        current = current.replace(year=current.year + 1, month=1)
    else:
        current = current.replace(month=current.month + 1)

# Annual bonuses paid in March
for y in (2023, 2024, 2025, 2026):
    bonus_date = date(y, 3, 15)
    if bonus_date <= TODAY:
        post("/income",
             date=bonus_date.isoformat(),
             category="Bonus",
             description="Annual bonus",
             amount=str(round(salary_by_year[y] * 1.5)),
             currency="EUR")


# ---- 3. UK rental income (started Feb 2024) --------------------------------

uk_start = date(2024, 2, 1)
cur = uk_start
while cur <= TODAY:
    if cur.day == 1:
        post("/income",
             date=cur.isoformat(),
             category="Rental",
             description="Manchester flat rent",
             amount="1450",
             currency="GBP")
    if cur.month == 12:
        cur = cur.replace(year=cur.year + 1, month=1)
    else:
        cur = cur.replace(month=cur.month + 1)


# ---- 4. US freelance income (started June 2024) ----------------------------

freelance_clients = [
    ("Acme Corp consulting", 1800, 4500),
    ("Brightside design retainer", 1200, 1800),
    ("Helix audit", 800, 1600),
    ("Northwind retainer", 2200, 3500),
]
for offset_days in range(0, (TODAY - date(2024, 6, 15)).days, 14):
    d = date(2024, 6, 15) + timedelta(days=offset_days)
    if random.random() < 0.55 and d <= TODAY:  # not every fortnight
        client, lo, hi = random.choice(freelance_clients)
        post("/income",
             date=d.isoformat(),
             category="Freelance",
             description=client,
             amount=str(random.randint(lo, hi)),
             currency="USD")


# ---- 5. Investment dividends quarterly -------------------------------------

for y in (2023, 2024, 2025, 2026):
    for m in (3, 6, 9, 12):
        d = date(y, m, 15)
        if d <= TODAY:
            post("/income",
                 date=d.isoformat(),
                 category="Investment",
                 description="Index fund dividend",
                 amount=str(random.randint(180, 540)),
                 currency="EUR")


# ---- 6. Recurring monthly spend --------------------------------------------

def month_iter(start, end):
    cur = start.replace(day=1)
    while cur <= end:
        yield cur
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)


def safe(d):
    return d if d <= TODAY else None


for m in month_iter(START, TODAY):
    # Rent went up over the years
    if m.year == 2023:
        rent = 950
    elif m.year == 2024:
        rent = 980
    elif m.year == 2025:
        rent = 1050
    else:
        rent = 1100
    rd = safe(m.replace(day=2))
    if rd:
        post("/expenses", date=rd.isoformat(), category="Rent",
             description="Apartment Lisbon", amount=str(rent), currency="EUR")

    # Utilities each month
    for day, cat, desc, lo, hi in [
        (5,  "Utilities", "EDP electricity", 28, 78),
        (5,  "Utilities", "MEO internet", 35, 35),
        (8,  "Utilities", "Vodafone mobile", 18, 22),
        (10, "Utilities", "Galp natural gas", 18, 42),
    ]:
        d = safe(m.replace(day=day))
        if d:
            post("/expenses", date=d.isoformat(), category=cat,
                 description=desc, amount=str(round(random.uniform(lo, hi), 2)),
                 currency="EUR")

    # Subscriptions
    for day, cat, desc, amt, ccy in [
        (12, "Entertainment", "Netflix",  "13.99",  "EUR"),
        (12, "Entertainment", "Spotify",  "9.99",   "EUR"),
        (15, "Entertainment", "iCloud",   "2.99",   "EUR"),
        (18, "Education",     "O Reilly subscription", "29.99", "USD"),
        (20, "Health",        "Gym membership", "39",  "EUR"),
    ]:
        d = safe(m.replace(day=day))
        if d:
            post("/expenses", date=d.isoformat(), category=cat,
                 description=desc, amount=amt, currency=ccy)


# ---- 7. Variable discretionary spend ---------------------------------------

variable_pool = [
    ("Food", "Pingo Doce",     "EUR", 18, 90),
    ("Food", "Continente",     "EUR", 25, 130),
    ("Food", "Mercadona",      "EUR", 15, 75),
    ("Food", "Tesco Express",  "GBP", 4, 14),
    ("Food", "Pret a Manger",  "GBP", 3, 10),
    ("Food", "Coffee shop",    "EUR", 2, 6),
    ("Food", "Restaurant",     "EUR", 18, 80),
    ("Food", "Whole Foods",    "USD", 20, 90),
    ("Food", "Lawson",         "JPY", 320, 1500),
    ("Transport", "Uber",                     "EUR", 6, 22),
    ("Transport", "Bolt scooter",             "EUR", 3, 9),
    ("Transport", "TfL Oyster topup",         "GBP", 10, 40),
    ("Transport", "JR Pass topup",            "JPY", 1500, 6000),
    ("Transport", "Metropolitano monthly",    "EUR", 40, 40),
    ("Transport", "Fuel",                     "EUR", 35, 75),
    ("Shopping", "Amazon",                    "EUR", 12, 180),
    ("Shopping", "Decathlon",                 "EUR", 18, 110),
    ("Shopping", "Uniqlo",                    "GBP", 22, 85),
    ("Shopping", "IKEA",                      "EUR", 20, 250),
    ("Health", "Pharmacy",                    "EUR", 6, 35),
    ("Health", "Dental visit",                "EUR", 60, 250),
    ("Education", "Udemy course",             "USD", 9, 45),
    ("Travel", "Ryanair",                     "EUR", 45, 280),
    ("Travel", "Airbnb",                      "EUR", 70, 320),
    ("Travel", "Booking.com",                 "EUR", 80, 350),
    ("Other", "ATM withdrawal",               "EUR", 50, 200),
    ("Other", "Bank fee",                     "EUR", 2, 8),
]

# About 20 transactions per month on average across 3 years
months = list(month_iter(START, TODAY))
random.shuffle(months)
total_months = (TODAY.year - START.year) * 12 + (TODAY.month - START.month) + 1
target_count = total_months * 22

for _ in range(target_count):
    cat, desc, ccy, lo, hi = random.choice(variable_pool)
    m = random.choice(months)
    days_in_month = 28
    d = m.replace(day=random.randint(1, days_in_month))
    if d > TODAY:
        continue
    # Some currencies only valid post relevant dates
    if ccy == "GBP" and d < date(2024, 2, 1):
        continue
    if ccy == "USD" and d < date(2024, 6, 15):
        continue
    if ccy == "JPY" and not (date(2024, 10, 1) <= d <= date(2024, 11, 1)):
        # only spent in Tokyo during the trip window
        continue
    amt = round(random.uniform(lo, hi), 2)
    post("/expenses", date=d.isoformat(), category=cat, description=desc,
         amount=str(amt), currency=ccy)


# ---- 8. Big one-off purchases ---------------------------------------------

one_offs = [
    ("2023-04-12", "Shopping", "MacBook Pro M2",          "2399", "EUR"),
    ("2023-08-20", "Travel",   "Iceland trip",            "1850", "EUR"),
    ("2024-02-04", "Other",    "Manchester flat deposit", "4500", "GBP"),
    ("2024-05-09", "Shopping", "DSLR camera",              "1450", "EUR"),
    ("2024-10-08", "Travel",   "Tokyo flight",             "920",  "EUR"),
    ("2024-10-09", "Travel",   "Tokyo hotel 10 nights",    "1850", "EUR"),
    ("2025-01-15", "Health",   "Eye surgery",              "2200", "EUR"),
    ("2025-04-22", "Shopping", "Ergonomic chair",          "780",  "EUR"),
    ("2025-09-03", "Travel",   "Italy holiday",            "1640", "EUR"),
    ("2026-01-10", "Shopping", "iPhone 17 Pro",            "1499", "EUR"),
    ("2026-03-04", "Other",    "Lawyer fees",              "650",  "EUR"),
]
for d, cat, desc, amt, ccy in one_offs:
    if date.fromisoformat(d) <= TODAY:
        post("/expenses", date=d, category=cat, description=desc,
             amount=amt, currency=ccy)


# ---- 9. Transfers between accounts -----------------------------------------

# Read account ids
import sqlite3
c = sqlite3.connect("data/budget_tracker.db")
ids = {row[1]: row[0] for row in c.execute(
    "SELECT id, name FROM accounts WHERE user_id=1")}

def transfer(from_name, to_name, amount, when, desc):
    if date.fromisoformat(when) > TODAY:
        return
    post("/transfer",
         from_account_id=str(ids[from_name]),
         to_account_id=str(ids[to_name]),
         amount=str(amount),
         date=when,
         description=desc)

# Periodic moves to savings
for y in (2023, 2024, 2025, 2026):
    for m in (3, 6, 9, 12):
        d = date(y, m, 28)
        if d <= TODAY:
            transfer("Default", "Emergency Fund", random.randint(300, 800),
                     d.isoformat(), "Move to savings")
# Cross currency top ups
transfer("Default", "UK Manchester Flat", 600,  "2024-02-15", "Top up UK flat")
transfer("Default", "Travel JPY",          1200, "2024-09-25", "Tokyo trip funds")
transfer("Default", "Travel JPY",          800,  "2024-10-12", "Extra Tokyo cash")
transfer("US Freelance", "Default",        2500, "2025-02-20", "Convert USD freelance to EUR")
transfer("US Freelance", "Default",        3000, "2025-09-12", "Convert USD freelance to EUR")
transfer("Default", "Index Fund",          5000, "2024-08-01", "Open index fund")
transfer("Default", "Index Fund",          3000, "2025-04-15", "Top up index fund")
transfer("Default", "Index Fund",          4000, "2026-02-10", "Top up index fund")


# ---- 10. Budgets ----------------------------------------------------------

for cat, amt in [
    ("Food",          "650"),
    ("Transport",     "200"),
    ("Entertainment", "100"),
    ("Rent",          "1100"),
    ("Utilities",     "180"),
    ("Shopping",      "300"),
    ("Travel",        "500"),
    ("Health",        "150"),
    ("Education",     "80"),
]:
    post("/budgets", category=cat, limit=amt)

print("Demo seed complete.")

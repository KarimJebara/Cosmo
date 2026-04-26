import logging
import os
import secrets
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for

import database
from cosmo import legacy_adapter
from cosmo.importers import get_importer
from currency_converter import format_amount_with_conversion
from merchant_mapper import (
    ensure_merchant_files_exist,
    update_merchant_category,
)

# Configure logging once at app import. Level overridable via LOG_LEVEL env var.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = Flask(__name__)
# SECRET_KEY: use env var in production. Random fallback prevents the old hardcoded
# placeholder from being deployed unchanged, but warns the user loudly.
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    _secret = secrets.token_urlsafe(48)
    logging.getLogger(__name__).warning(
        "SECRET_KEY not set — generated a per-process random key. "
        "Sessions will invalidate on every restart. Set SECRET_KEY in .env for production."
    )
app.secret_key = _secret

# Initialize database
database.init_db()

# Ensure merchant category files exist
ensure_merchant_files_exist()

# Register Jinja2 filter for currency formatting
@app.template_filter('format_with_conversion')
def jinja_format_with_conversion(amount, currency):
    """Format amount with currency conversion"""
    return format_amount_with_conversion(amount, currency)

def linear_regression(x_values, y_values):
    """Simple linear regression using least squares method"""
    if len(x_values) < 2 or len(y_values) < 2:
        return None, None

    n = len(x_values)
    mean_x = sum(x_values) / n
    mean_y = sum(y_values) / n

    numerator = sum((x_values[i] - mean_x) * (y_values[i] - mean_y) for i in range(n))
    denominator = sum((x_values[i] - mean_x) ** 2 for i in range(n))

    if denominator == 0:
        return None, None

    slope = numerator / denominator
    intercept = mean_y - slope * mean_x

    return slope, intercept

def login_required(f):
    """Decorator to require login for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def _current_user_id() -> int:
    """Helper for route handlers — assumes login_required already ran."""
    return session['user_id']


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/healthz')
def healthz():
    """Liveness probe for Docker / orchestrators.

    Returns 200 if the DB is reachable, 503 otherwise.
    """
    try:
        with database.get_db() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok"}, 200
    except Exception as exc:  # pragma: no cover - defensive
        return {"status": "error", "detail": str(exc)}, 503


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Please fill in all fields!')
            return redirect(url_for('login'))

        user_id = database.authenticate_user(username, password)
        if user_id:
            session['user_id'] = user_id
            session['username'] = username
            session['currency'] = session.get('currency', 'EUR')
            legacy_adapter.ensure_default_account(user_id)
            flash(f'Welcome back, {username}!')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password!')
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not username or not password or not confirm_password:
            flash('Please fill in all fields!')
            return redirect(url_for('signup'))

        if len(username) < 3:
            flash('Username must be at least 3 characters long!')
            return redirect(url_for('signup'))

        if len(password) < 4:
            flash('Password must be at least 4 characters long!')
            return redirect(url_for('signup'))

        if password != confirm_password:
            flash('Passwords do not match!')
            return redirect(url_for('signup'))

        user_id = database.create_user(username, password)
        if user_id:
            session['user_id'] = user_id
            session['username'] = username
            flash(f'Account created successfully! Welcome, {username}!')
            return redirect(url_for('dashboard'))
        else:
            flash('Username already exists! Please choose a different one.')
            return redirect(url_for('signup'))

    return render_template('signup.html')


@app.route('/logout')
def logout():
    username = session.get('username', 'User')
    session.clear()
    flash(f'Goodbye, {username}! You have been logged out.')
    return redirect(url_for('login'))


@app.route('/set_currency/<currency>', methods=['POST'])
@login_required
def set_currency(currency):
    if currency in ['EUR', 'GBP', 'USD']:
        session['currency'] = currency
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/set_timeframe/<int:months>', methods=['POST'])
@login_required
def set_timeframe(months):
    """Set the timeframe filter in session"""
    if months in [1, 2, 3, 6, 9, 12]:
        session['timeframe_months'] = months
    return '', 204


def filter_by_timeframe(items):
    """Filter items by the selected timeframe"""
    timeframe_months = session.get('timeframe_months', 12)  # Default to 12 months
    cutoff_date = datetime.now() - timedelta(days=timeframe_months * 30)

    filtered_items = []
    for item in items:
        date_str = getattr(item, 'date', '')
        if date_str:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                if date_obj >= cutoff_date:
                    filtered_items.append(item)
            except Exception:
                pass
    return filtered_items

def predict_value(slope, intercept, x):
    """Predict a value using linear regression"""
    if slope is None or intercept is None:
        return None
    return slope * x + intercept


@app.route('/dashboard')
@login_required
def dashboard():
    try:
        # Get timeframe from session (default to 12 months)
        timeframe_months = session.get('timeframe_months', 12)

        # Get all data and filter by timeframe
        uid = _current_user_id()
        all_incomes = legacy_adapter.get_incomes(uid)
        all_expenses = legacy_adapter.get_expenses(uid)

        incomes = filter_by_timeframe(all_incomes)
        expenses = filter_by_timeframe(all_expenses)

        # Calculate totals
        total_income = sum([float(getattr(t, 'amount', 0.0)) for t in incomes])
        total_expenses = sum([float(getattr(t, 'amount', 0.0)) for t in expenses])
        balance = total_income - total_expenses

        # Get current date info
        now = datetime.now()
        current_month = now.strftime('%Y-%m')

        # Calculate last month (handle year rollover)
        if now.month == 1:
            last_month = f"{now.year - 1}-12"
        else:
            last_month = f"{now.year}-{str(now.month - 1).zfill(2)}"

        # Calculate current month totals
        current_month_income = 0
        current_month_expenses = 0
        last_month_income = 0
        last_month_expenses = 0

        for income in incomes:
            date_str = getattr(income, 'date', '')
            if date_str:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    month_key = date_obj.strftime('%Y-%m')
                    amount = float(getattr(income, 'amount', 0))

                    if month_key == current_month:
                        current_month_income += amount
                    elif month_key == last_month:
                        last_month_income += amount
                except Exception:
                    pass

        for expense in expenses:
            date_str = getattr(expense, 'date', '')
            if date_str:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    month_key = date_obj.strftime('%Y-%m')
                    amount = float(getattr(expense, 'amount', 0))

                    if month_key == current_month:
                        current_month_expenses += amount
                    elif month_key == last_month:
                        last_month_expenses += amount
                except Exception:
                    pass

        # Calculate trends
        income_trend = None
        income_trend_direction = 'neutral'
        if last_month_income > 0:
            income_change = ((current_month_income - last_month_income) / last_month_income) * 100
            income_trend = abs(income_change)
            income_trend_direction = 'up' if income_change > 0 else 'down'
        elif current_month_income > 0:
            income_trend = 100
            income_trend_direction = 'up'

        expense_trend = None
        expense_trend_direction = 'neutral'
        if last_month_expenses > 0:
            expense_change = ((current_month_expenses - last_month_expenses) / last_month_expenses) * 100
            expense_trend = abs(expense_change)
            expense_trend_direction = 'up' if expense_change > 0 else 'down'
        elif current_month_expenses > 0:
            expense_trend = 100
            expense_trend_direction = 'up'

        # Get recent transactions (combine income and expenses)
        recent_transactions = []

        for income in incomes:
            recent_transactions.append({
                'date': getattr(income, 'date', ''),
                'type': 'income',
                'description': getattr(income, 'description', ''),
                'category': getattr(income, 'category', ''),
                'amount': float(getattr(income, 'amount', 0)),
                'currency': getattr(income, 'currency', 'EUR')
            })

        for expense in expenses:
            recent_transactions.append({
                'date': getattr(expense, 'date', ''),
                'type': 'expense',
                'description': getattr(expense, 'description', ''),
                'category': getattr(expense, 'category', ''),
                'amount': float(getattr(expense, 'amount', 0)),
                'currency': getattr(expense, 'currency', 'EUR')
            })

        # Sort by date (most recent first) and get last 5
        recent_transactions.sort(key=lambda x: x['date'], reverse=True)
        recent_transactions = recent_transactions[:5]

        # Format dates for display
        for trans in recent_transactions:
            try:
                date_obj = datetime.strptime(trans['date'], '%Y-%m-%d')
                trans['formatted_date'] = date_obj.strftime('%B %d, %Y')
            except Exception:
                trans['formatted_date'] = trans['date']

        # Calculate expenses by category for chart
        expense_by_category = defaultdict(float)
        for expense in expenses:
            category = getattr(expense, 'category', 'Other')
            amount = float(getattr(expense, 'amount', 0))
            expense_by_category[category] += amount

        category_labels = list(expense_by_category.keys())
        category_values = list(expense_by_category.values())

    except Exception:
        total_income = total_expenses = balance = 0.0
        income_trend = expense_trend = None
        income_trend_direction = expense_trend_direction = 'neutral'
        recent_transactions = []
        category_labels = []
        category_values = []

    return render_template('dashboard.html',
                           total_income=total_income,
                           total_expenses=total_expenses,
                           balance=balance,
                           income_trend=income_trend,
                           income_trend_direction=income_trend_direction,
                           expense_trend=expense_trend,
                           expense_trend_direction=expense_trend_direction,
                           recent_transactions=recent_transactions,
                           category_labels=category_labels,
                           category_values=category_values,
                           timeframe_months=timeframe_months)

@app.route('/income', methods=['GET', 'POST'])
@login_required
def income():
    if request.method == 'POST':
        date = request.form.get('date')
        user_category = request.form.get('category')
        description = request.form.get('description') or user_category
        amount = request.form.get('amount')
        currency = request.form.get('currency', 'EUR')

        if not date or not user_category or not amount:
            flash('All fields are required!')
            return redirect(url_for('income'))

        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except ValueError:
            flash('Invalid amount!')
            return redirect(url_for('income'))

        auto_category = legacy_adapter.auto_categorize(
            _current_user_id(), description, type='income'
        )
        category = auto_category if auto_category else user_category

        try:
            legacy_adapter.add_transaction(
                _current_user_id(),
                type='income',
                date=date,
                description=description,
                category=category,
                amount=amount,
                currency=currency,
            )
        except ValueError:
            flash('Invalid date format — use YYYY-MM-DD.')
            return redirect(url_for('income'))

        flash('Income added successfully!')
        return redirect(url_for('income'))

    timeframe_months = session.get('timeframe_months', 12)
    all_incomes = legacy_adapter.get_incomes(_current_user_id())
    incomes = filter_by_timeframe(all_incomes)
    # Sort by date descending (most recent first)
    incomes = sorted(incomes, key=lambda x: x.date, reverse=True)
    total_income = sum([float(getattr(t, 'amount', 0.0)) for t in incomes])
    return render_template('income.html', incomes=incomes, total_income=total_income, timeframe_months=timeframe_months)


@app.route('/expenses', methods=['GET', 'POST'])
@login_required
def expenses():
    if request.method == 'POST':
        date = request.form.get('date')
        user_category = request.form.get('category')
        description = request.form.get('description') or user_category
        amount = request.form.get('amount')
        currency = request.form.get('currency', 'EUR')

        if not date or not user_category or not amount:
            flash('All fields are required!')
            return redirect(url_for('expenses'))

        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except ValueError:
            flash('Invalid amount!')
            return redirect(url_for('expenses'))

        auto_category = legacy_adapter.auto_categorize(
            _current_user_id(), description, type='expense'
        )
        category = auto_category if auto_category else user_category

        try:
            legacy_adapter.add_transaction(
                _current_user_id(),
                type='expense',
                date=date,
                description=description,
                category=category,
                amount=amount,
                currency=currency,
            )
        except ValueError:
            flash('Invalid date format — use YYYY-MM-DD.')
            return redirect(url_for('expenses'))

        flash('Expense added successfully!')
        return redirect(url_for('expenses'))

    timeframe_months = session.get('timeframe_months', 12)
    all_expenses = legacy_adapter.get_expenses(_current_user_id())
    expenses = filter_by_timeframe(all_expenses)
    # Sort by date descending (most recent first)
    expenses = sorted(expenses, key=lambda x: x.date, reverse=True)
    total_expenses = sum([float(getattr(t, 'amount', 0.0)) for t in expenses])
    return render_template('expenses.html', expenses=expenses, total_expenses=total_expenses, timeframe_months=timeframe_months)


@app.route('/revolut_import', methods=['GET', 'POST'])
@login_required
def revolut_import():
    if request.method == 'POST':
        if 'revolut_csv' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)

        file = request.files['revolut_csv']

        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)

        if file and file.filename.endswith('.csv'):
            try:
                csv_content = file.stream.read().decode('utf-8')
                importer = get_importer('revolut')
                records = list(importer.parse(csv_content))
                imported_count, skipped_count = legacy_adapter.import_transactions(
                    _current_user_id(),
                    source='revolut',
                    records=records,
                )
                flash(
                    f'Successfully imported {imported_count} Revolut transactions! '
                    f'Skipped {skipped_count} duplicate transactions.',
                    'success',
                )
                return redirect(url_for('dashboard'))
            except Exception as e:
                flash(f'Error importing transactions: {e}', 'error')
                return redirect(request.url)
        else:
            flash('Invalid file type. Please upload a CSV file.', 'error')
            return redirect(request.url)

    timeframe_months = session.get('timeframe_months', 12)
    return render_template('revolut_import.html', timeframe_months=timeframe_months)


@app.route('/delete_income/<date_str>/<float:amount>/<desc>', methods=['POST'])
@login_required
def delete_income(date_str, amount, desc):
    try:
        deleted = legacy_adapter.delete_transaction_by_natural_key(
            _current_user_id(),
            type='income', date=date_str, amount=amount, description=desc,
        )
        flash('Income deleted successfully!' if deleted else 'Income not found!')
    except Exception as e:
        flash(f'Error deleting income: {e!s}')
    return redirect(url_for('income'))


@app.route('/change_income_category/<date_str>/<float:amount>/<desc>', methods=['POST'])
@login_required
def change_income_category(date_str, amount, desc):
    try:
        new_category = request.form.get('new_category')
        if not new_category:
            flash('Please select a category!')
            return redirect(url_for('income'))

        updated_count, merchant = legacy_adapter.change_category_by_natural_key(
            _current_user_id(),
            type='income', date=date_str, amount=amount, description=desc,
            new_category=new_category,
        )
        if merchant is None:
            flash('Income not found!')
            return redirect(url_for('income'))

        # learn_from_correction in the adapter already persisted a
        # MerchantRule. Mirror to the legacy JSON file too so any code that
        # still reads it stays consistent until merchant_mapper is removed.
        update_merchant_category(merchant, new_category, transaction_type='income')
        flash(f'Category updated to "{new_category}" for {updated_count} transaction(s) from the same merchant!')
    except Exception as e:
        flash(f'Error updating category: {e!s}')
    return redirect(url_for('income'))


@app.route('/delete_expense/<date_str>/<float:amount>/<desc>', methods=['POST'])
@login_required
def delete_expense(date_str, amount, desc):
    try:
        deleted = legacy_adapter.delete_transaction_by_natural_key(
            _current_user_id(),
            type='expense', date=date_str, amount=amount, description=desc,
        )
        flash('Expense deleted successfully!' if deleted else 'Expense not found!')
    except Exception as e:
        flash(f'Error deleting expense: {e!s}')
    return redirect(url_for('expenses'))


@app.route('/change_expense_category/<date_str>/<float:amount>/<desc>', methods=['POST'])
@login_required
def change_expense_category(date_str, amount, desc):
    try:
        new_category = request.form.get('new_category')
        if not new_category:
            flash('Please select a category!')
            return redirect(url_for('expenses'))

        updated_count, merchant = legacy_adapter.change_category_by_natural_key(
            _current_user_id(),
            type='expense', date=date_str, amount=amount, description=desc,
            new_category=new_category,
        )
        if merchant is None:
            flash('Expense not found!')
            return redirect(url_for('expenses'))

        # See change_income_category for the dual-write rationale.
        update_merchant_category(merchant, new_category, transaction_type='expenses')
        flash(f'Category updated to "{new_category}" for {updated_count} transaction(s) from the same merchant!')
    except Exception as e:
        flash(f'Error updating category: {e!s}')
    return redirect(url_for('expenses'))


@app.route('/budgets', methods=['GET', 'POST'])
@login_required
def budgets():
    if request.method == 'POST':
        category = request.form.get('category')
        limit = request.form.get('limit')

        if not category or not limit:
            flash('Please fill in all fields!')
            return redirect(url_for('budgets'))

        try:
            limit = float(limit)
            if limit <= 0:
                raise ValueError("Limit must be positive")
        except ValueError:
            flash('Invalid limit amount!')
            return redirect(url_for('budgets'))

        legacy_adapter.set_budget(_current_user_id(), category=category, limit_amount=limit)
        flash('Budget limit set successfully!')
        return redirect(url_for('budgets'))

    # Calculate spending per category with timeframe filtering
    timeframe_months = session.get('timeframe_months', 12)
    uid = _current_user_id()
    all_expenses = legacy_adapter.get_expenses(uid)
    expenses = filter_by_timeframe(all_expenses)
    category_spending = {}

    for expense in expenses:
        cat = getattr(expense, 'category', 'Other')
        amount = float(getattr(expense, 'amount', 0))
        category_spending[cat] = category_spending.get(cat, 0) + amount

    # Prepare budget data with spending info
    budget_list = []
    for budget in legacy_adapter.get_budgets(uid):
        cat = budget.category
        limit = float(budget.limit)
        spent = category_spending.get(cat, 0)
        remaining = limit - spent
        percentage = (spent / limit * 100) if limit > 0 else 0

        budget_list.append({
            'id': budget.id,
            'category': cat,
            'limit': limit,
            'spent': spent,
            'remaining': remaining,
            'percentage': percentage,
        })

    return render_template('budgets.html', budgets=budget_list, timeframe_months=timeframe_months)


@app.route('/delete_budget/<int:budget_id>', methods=['POST'])
@login_required
def delete_budget(budget_id):
    deleted = legacy_adapter.delete_budget(_current_user_id(), budget_id)
    flash('Budget deleted successfully!' if deleted else 'Budget not found!')
    return redirect(url_for('budgets'))


@app.route('/accounts', methods=['GET', 'POST'])
@login_required
def accounts():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        currency = (request.form.get('currency') or 'EUR').strip().upper()
        acc_type = (request.form.get('type') or 'checking').strip()

        if not name or not currency:
            flash('Name and currency are required.')
            return redirect(url_for('accounts'))
        if len(currency) != 3 or not currency.isalpha():
            flash('Currency must be a 3-letter ISO code.')
            return redirect(url_for('accounts'))

        legacy_adapter.create_account(
            _current_user_id(), name=name, currency=currency, type=acc_type
        )
        flash(f'Account "{name}" created.')
        return redirect(url_for('accounts'))

    account_views = legacy_adapter.get_accounts(
        _current_user_id(), include_archived=True
    )
    return render_template('accounts.html', accounts=account_views)


@app.route('/archive_account/<int:account_id>', methods=['POST'])
@login_required
def archive_account(account_id):
    archived = legacy_adapter.archive_account(_current_user_id(), account_id)
    flash('Account archived.' if archived else 'Account not found.')
    return redirect(url_for('accounts'))


@app.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    uid = _current_user_id()

    if request.method == 'POST':
        try:
            from_id = int(request.form.get('from_account_id') or 0)
            to_id = int(request.form.get('to_account_id') or 0)
            amount = float(request.form.get('amount') or 0)
            date_str = request.form.get('date') or ''
            description = (request.form.get('description') or '').strip()

            legacy_adapter.create_transfer(
                uid,
                from_account_id=from_id,
                to_account_id=to_id,
                amount=amount,
                date=date_str,
                description=description,
            )
            flash('Transfer created.')
        except ValueError as exc:
            flash(f'Could not create transfer: {exc}')
        return redirect(url_for('transfer'))

    account_views = legacy_adapter.get_accounts(uid)
    return render_template(
        'transfer.html',
        accounts=account_views,
        today=datetime.now().strftime('%Y-%m-%d'),
    )


@app.route('/rules')
@login_required
def rules():
    rule_views = legacy_adapter.get_merchant_rules(_current_user_id())
    return render_template('rules.html', rules=rule_views)


@app.route('/delete_rule/<int:rule_id>', methods=['POST'])
@login_required
def delete_rule(rule_id):
    deleted = legacy_adapter.delete_merchant_rule(_current_user_id(), rule_id)
    flash('Rule deleted!' if deleted else 'Rule not found.')
    return redirect(url_for('rules'))


@app.route('/reports')
@login_required
def reports():
    timeframe_months = session.get('timeframe_months', 12)

    # Get all transactions and filter by timeframe
    uid = _current_user_id()
    all_incomes = legacy_adapter.get_incomes(uid)
    all_expenses = legacy_adapter.get_expenses(uid)
    incomes = filter_by_timeframe(all_incomes)
    expenses = filter_by_timeframe(all_expenses)

    # Calculate totals
    total_income = sum([float(getattr(t, 'amount', 0)) for t in incomes])
    total_expenses = sum([float(getattr(t, 'amount', 0)) for t in expenses])
    balance = total_income - total_expenses

    # Expenses by category
    category_totals = defaultdict(float)
    for expense in expenses:
        cat = getattr(expense, 'category', 'Other')
        amount = float(getattr(expense, 'amount', 0))
        category_totals[cat] += amount

    expense_by_category = []
    category_labels = []
    category_values = []

    for cat, amount in category_totals.items():
        percentage = (amount / total_expenses * 100) if total_expenses > 0 else 0
        expense_by_category.append({
            'category': cat,
            'amount': amount,
            'percentage': percentage
        })
        category_labels.append(cat)
        category_values.append(amount)

    # Monthly trends
    income_by_month = {}
    expense_by_month = {}

    for income in incomes:
        date_str = getattr(income, 'date', '')
        if date_str:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                # Use YYYY-MM as key for grouping, but store date object for sorting
                month_key = date_obj.strftime('%Y-%m')
                month_label = date_obj.strftime('%b %Y')
                amount = float(getattr(income, 'amount', 0))

                if month_key not in income_by_month:
                    income_by_month[month_key] = {'date': date_obj, 'label': month_label, 'amount': 0}
                income_by_month[month_key]['amount'] += amount
            except Exception:
                pass

    for expense in expenses:
        date_str = getattr(expense, 'date', '')
        if date_str:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                month_key = date_obj.strftime('%Y-%m')
                month_label = date_obj.strftime('%b %Y')
                amount = float(getattr(expense, 'amount', 0))

                if month_key not in expense_by_month:
                    expense_by_month[month_key] = {'date': date_obj, 'label': month_label, 'amount': 0}
                expense_by_month[month_key]['amount'] += amount
            except Exception:
                pass

    # Get all unique months and sort them
    all_month_keys = set(list(income_by_month.keys()) + list(expense_by_month.keys()))

    # Sort by the actual date, not alphabetically
    sorted_months = sorted(all_month_keys)

    # Build the data arrays
    month_labels = []
    income_trend = []
    expense_trend = []

    for month_key in sorted_months:
        # Get the label from either income or expense data
        if month_key in income_by_month:
            month_labels.append(income_by_month[month_key]['label'])
            income_trend.append(income_by_month[month_key]['amount'])
        elif month_key in expense_by_month:
            month_labels.append(expense_by_month[month_key]['label'])
            income_trend.append(0)

        if month_key in expense_by_month:
            expense_trend.append(expense_by_month[month_key]['amount'])
        else:
            expense_trend.append(0)

    monthly_data = len(sorted_months) > 0

    # Recent transactions (last 10)
    recent_transactions = []

    for income in incomes:
        recent_transactions.append({
            'date': getattr(income, 'date', ''),
            'type': 'Income',
            'description': getattr(income, 'description', ''),
            'category': getattr(income, 'category', ''),
            'amount': float(getattr(income, 'amount', 0))
        })

    for expense in expenses:
        recent_transactions.append({
            'date': getattr(expense, 'date', ''),
            'type': 'Expense',
            'description': getattr(expense, 'description', ''),
            'category': getattr(expense, 'category', ''),
            'amount': float(getattr(expense, 'amount', 0))
        })

    # Sort by date and get last 10
    recent_transactions.sort(key=lambda x: x['date'], reverse=True)
    recent_transactions = recent_transactions[:10]

    return render_template('reports.html',
                           total_income=total_income,
                           total_expenses=total_expenses,
                           balance=balance,
                           expense_by_category=expense_by_category,
                           category_labels=category_labels,
                           category_values=category_values,
                           monthly_data=monthly_data,
                           month_labels=month_labels,
                           income_trend=income_trend,
                           expense_trend=expense_trend,
                           recent_transactions=recent_transactions,
                           timeframe_months=timeframe_months)



@app.route('/graphs-stats')
@login_required
def graphs_stats():
    """Comprehensive analytics and visualization dashboard with predictions"""
    try:
        timeframe_months = session.get('timeframe_months', 12)
        uid = _current_user_id()
        all_incomes = legacy_adapter.get_incomes(uid)
        all_expenses = legacy_adapter.get_expenses(uid)
        incomes = filter_by_timeframe(all_incomes)
        expenses = filter_by_timeframe(all_expenses)

        # Calculate totals
        total_income = sum([float(getattr(t, 'amount', 0)) for t in incomes])
        total_expenses = sum([float(getattr(t, 'amount', 0)) for t in expenses])
        balance = total_income - total_expenses

        # ===== SPENDING BY CATEGORY =====
        category_totals = defaultdict(float)
        category_counts = defaultdict(int)
        for expense in expenses:
            cat = getattr(expense, 'category', 'Other')
            amount = float(getattr(expense, 'amount', 0))
            category_totals[cat] += amount
            category_counts[cat] += 1

        category_labels = list(category_totals.keys())
        category_values = list(category_totals.values())

        # Top 5 categories
        top_cats = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:5]
        top_cat_names = [cat for cat, _ in top_cats]
        top_cat_values = [val for _, val in top_cats]

        # ===== SPENDING BY DAY OF WEEK =====
        day_spending = defaultdict(float)
        day_transaction_counts = defaultdict(int)
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        for expense in expenses:
            date_str = getattr(expense, 'date', '')
            if date_str:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    day_name = day_order[date_obj.weekday()]
                    amount = float(getattr(expense, 'amount', 0))
                    day_spending[day_name] += amount
                    day_transaction_counts[day_name] += 1
                except Exception:
                    pass

        # Ensure all days are represented and calculate averages
        day_labels = day_order
        day_values = []
        for day in day_order:
            if day_transaction_counts[day] > 0:
                average = day_spending[day] / day_transaction_counts[day]
                day_values.append(average)
            else:
                day_values.append(0)
        day_transaction_counts_list = [day_transaction_counts.get(day, 0) for day in day_order]

        # ===== MONTHLY TRENDS =====
        income_by_month = {}
        expense_by_month = {}

        for income in incomes:
            date_str = getattr(income, 'date', '')
            if date_str:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    month_key = date_obj.strftime('%Y-%m')
                    month_label = date_obj.strftime('%b %Y')
                    amount = float(getattr(income, 'amount', 0))

                    if month_key not in income_by_month:
                        income_by_month[month_key] = {'date': date_obj, 'label': month_label, 'amount': 0}
                    income_by_month[month_key]['amount'] += amount
                except Exception:
                    pass

        for expense in expenses:
            date_str = getattr(expense, 'date', '')
            if date_str:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    month_key = date_obj.strftime('%Y-%m')
                    month_label = date_obj.strftime('%b %Y')
                    amount = float(getattr(expense, 'amount', 0))

                    if month_key not in expense_by_month:
                        expense_by_month[month_key] = {'date': date_obj, 'label': month_label, 'amount': 0}
                    expense_by_month[month_key]['amount'] += amount
                except Exception:
                    pass

        all_month_keys = set(list(income_by_month.keys()) + list(expense_by_month.keys()))
        sorted_months = sorted(all_month_keys)

        month_labels = []
        income_trend = []
        expense_trend = []

        for month_key in sorted_months:
            if month_key in income_by_month:
                month_labels.append(income_by_month[month_key]['label'])
                income_trend.append(income_by_month[month_key]['amount'])
            elif month_key in expense_by_month:
                month_labels.append(expense_by_month[month_key]['label'])
                income_trend.append(0)

            if month_key in expense_by_month:
                expense_trend.append(expense_by_month[month_key]['amount'])
            else:
                expense_trend.append(0)

        # ===== DAILY SPENDING THROUGHOUT MONTH =====
        date_spending = defaultdict(float)
        for expense in expenses:
            date_str = getattr(expense, 'date', '')
            if date_str:
                amount = float(getattr(expense, 'amount', 0))
                date_spending[date_str] += amount

        sorted_dates = sorted(date_spending.keys())
        date_labels = sorted_dates
        date_values = [date_spending[date] for date in sorted_dates]

        # ===== STATISTICS =====
        all_amounts = [float(getattr(e, 'amount', 0)) for e in expenses]
        avg_expense = sum(all_amounts) / len(all_amounts) if all_amounts else 0
        max_expense = max(all_amounts) if all_amounts else 0
        min_expense = min(all_amounts) if all_amounts else 0

        all_income_amounts = [float(getattr(i, 'amount', 0)) for i in incomes]
        avg_income = sum(all_income_amounts) / len(all_income_amounts) if all_income_amounts else 0

        # Calculate average daily spending
        total_days = len(set([getattr(e, 'date', '') for e in expenses]))
        avg_daily_spend = total_expenses / max(total_days, 1) if total_expenses > 0 else 0

        # Busiest day
        busiest_day = max(day_spending, key=day_spending.get) if day_spending else 'N/A'

        # Category percentages
        expense_percentages = {}
        if total_expenses > 0:
            for cat, amount in category_totals.items():
                expense_percentages[cat] = (amount / total_expenses) * 100
        else:
            expense_percentages = {cat: 0 for cat in category_labels}

        # ===== PREDICTIONS & FORECASTING =====

        # 1. Monthly expense prediction
        if len(expense_trend) >= 2:
            x_months = list(range(len(expense_trend)))
            slope, intercept = linear_regression(x_months, expense_trend)
            predicted_monthly_expense = predict_value(slope, intercept, len(expense_trend))
            if predicted_monthly_expense is None:
                predicted_monthly_expense = avg_expense * 30  # Fallback
        else:
            predicted_monthly_expense = avg_expense * 30

        # 2. Next 3 months predictions
        next_3_months_predictions = []
        if len(expense_trend) >= 2:
            x_months = list(range(len(expense_trend)))
            slope, intercept = linear_regression(x_months, expense_trend)
            for i in range(1, 4):
                pred = predict_value(slope, intercept, len(expense_trend) + i)
                next_3_months_predictions.append(max(0, pred) if pred else avg_expense * 30)
        else:
            next_3_months_predictions = [avg_expense * 30] * 3

        # 3. Yearly balance prediction
        if len(income_trend) >= 2 and len(expense_trend) >= 2:
            x_months = list(range(max(len(income_trend), len(expense_trend))))

            # Pad data if needed
            income_trend_padded = income_trend + [0] * (len(x_months) - len(income_trend))
            expense_trend_padded = expense_trend + [0] * (len(x_months) - len(expense_trend))

            income_slope, income_intercept = linear_regression(x_months, income_trend_padded)
            expense_slope, expense_intercept = linear_regression(x_months, expense_trend_padded)

            # Predict for next 12 months
            future_months = 12
            predicted_yearly_income = 0
            predicted_yearly_expenses = 0

            for i in range(len(expense_trend), len(expense_trend) + future_months):
                pred_income = predict_value(income_slope, income_intercept, i)
                pred_expense = predict_value(expense_slope, expense_intercept, i)
                predicted_yearly_income += max(0, pred_income) if pred_income else 0
                predicted_yearly_expenses += max(0, pred_expense) if pred_expense else 0

            predicted_yearly_balance = balance + (predicted_yearly_income - predicted_yearly_expenses)
        else:
            predicted_yearly_balance = balance + ((avg_income - avg_expense) * 12)

        # 4. Category-specific predictions (next year spending)
        category_predictions = {}
        for category in category_totals:
            cat_expenses = [float(getattr(e, 'amount', 0)) for e in expenses
                           if getattr(e, 'category', 'Other') == category]
            if cat_expenses:
                avg_cat_spending = sum(cat_expenses) / len(cat_expenses)
                yearly_prediction = avg_cat_spending * 12
                category_predictions[category] = yearly_prediction

        # Sort by predicted spending (descending)
        sorted_predictions = sorted(category_predictions.items(), key=lambda x: x[1], reverse=True)
        top_pred_categories = dict(sorted_predictions[:5])
        max_pred_category_value = max(top_pred_categories.values()) if top_pred_categories else 1

        # 5. Days until balance reaches warning level (if spending continues)
        if avg_daily_spend > 0:
            days_until_low = balance / avg_daily_spend if balance > 0 else 0
        else:
            days_until_low = float('inf')

    except Exception as e:
        print(f"Error in graphs_stats: {e}")
        total_income = total_expenses = balance = 0
        category_labels = category_values = []
        top_cat_names = top_cat_values = []
        day_labels = day_values = day_transaction_counts_list = []
        month_labels = income_trend = expense_trend = []
        date_labels = date_values = []
        avg_expense = avg_income = max_expense = min_expense = 0
        avg_daily_spend = 0
        busiest_day = 'N/A'
        expense_percentages = {}
        predicted_monthly_expense = 0
        next_3_months_predictions = [0, 0, 0]
        predicted_yearly_balance = 0
        top_pred_categories = {}
        max_pred_category_value = 1
        days_until_low = float('inf')

    return render_template('graphs_stats.html',
                           total_income=total_income,
                           total_expenses=total_expenses,
                           balance=balance,
                           category_labels=category_labels,
                           category_values=category_values,
                           top_cat_names=top_cat_names,
                           top_cat_values=top_cat_values,
                           day_labels=day_labels,
                           day_values=day_values,
                           day_transaction_counts=day_transaction_counts_list,
                           month_labels=month_labels,
                           income_trend=income_trend,
                           expense_trend=expense_trend,
                           date_labels=date_labels,
                           date_values=date_values,
                           avg_expense=avg_expense,
                           avg_income=avg_income,
                           max_expense=max_expense,
                           min_expense=min_expense,
                           avg_daily_spend=avg_daily_spend,
                           busiest_day=busiest_day,
                           expense_percentages=expense_percentages,
                           predicted_monthly_expense=predicted_monthly_expense,
                           next_3_months_predictions=next_3_months_predictions,
                           predicted_yearly_balance=predicted_yearly_balance,
                           top_pred_categories=top_pred_categories,
                           max_pred_category_value=max_pred_category_value,
                           days_until_low=days_until_low,
                           timeframe_months=timeframe_months)



if __name__ == '__main__':
    app.run(debug=True, port=5002)

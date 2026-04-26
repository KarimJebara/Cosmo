import pytest
from datetime import datetime, timedelta
from app import linear_regression, predict_value, filter_by_timeframe


def _today() -> datetime:
    return datetime.now()


def _days_ago(n: int) -> str:
    return (_today() - timedelta(days=n)).strftime('%Y-%m-%d')


def test_filter_by_timeframe_1_month(app):
    with app.test_request_context():
        from flask import session
        session['timeframe_months'] = 1

        items = [
            type('Item', (), {'date': _days_ago(2)}),
            type('Item', (), {'date': _days_ago(10)}),
            type('Item', (), {'date': _days_ago(60)}),
        ]

        result = filter_by_timeframe(items)

        assert len(result) >= 1

def test_filter_by_timeframe_3_months(app):
    with app.test_request_context():
        from flask import session
        session['timeframe_months'] = 3

        items = [
            type('Item', (), {'date': _days_ago(2)}),
            type('Item', (), {'date': _days_ago(10)}),
            type('Item', (), {'date': _days_ago(40)}),
            type('Item', (), {'date': _days_ago(50)}),
            type('Item', (), {'date': _days_ago(180)}),
        ]

        result = filter_by_timeframe(items)

        assert len(result) >= 3

def test_filter_by_timeframe_6_months(app):
    with app.test_request_context():
        from flask import session
        session['timeframe_months'] = 6

        items = [
            type('Item', (), {'date': _days_ago(5)}),
            type('Item', (), {'date': _days_ago(120)}),
            type('Item', (), {'date': _days_ago(400)}),
        ]

        result = filter_by_timeframe(items)

        assert len(result) >= 1

def test_filter_by_timeframe_12_months(app):
    with app.test_request_context():
        from flask import session
        session['timeframe_months'] = 12

        items = [
            type('Item', (), {'date': _days_ago(5)}),
            type('Item', (), {'date': _days_ago(200)}),
            type('Item', (), {'date': _days_ago(900)}),
        ]

        result = filter_by_timeframe(items)

        assert len(result) >= 2

def test_filter_by_timeframe_invalid_dates(app):
    with app.test_request_context():
        from flask import session
        session['timeframe_months'] = 12

        items = [
            type('Item', (), {'date': 'invalid-date'}),
            type('Item', (), {'date': _days_ago(5)}),
        ]

        result = filter_by_timeframe(items)

        assert len(result) >= 1

def test_filter_by_timeframe_empty_list(app):
    with app.test_request_context():
        from flask import session
        session['timeframe_months'] = 12
        
        result = filter_by_timeframe([])
        
        assert result == []

def test_linear_regression_valid_data():
    x_values = [0, 1, 2, 3, 4]
    y_values = [100, 150, 200, 250, 300]
    
    slope, intercept = linear_regression(x_values, y_values)
    
    assert slope == 50.0
    assert intercept == 100.0

def test_linear_regression_single_point():
    x_values = [1]
    y_values = [100]
    
    slope, intercept = linear_regression(x_values, y_values)
    
    assert slope is None
    assert intercept is None

def test_linear_regression_zero_denominator():
    x_values = [1, 1, 1, 1]
    y_values = [100, 150, 200, 250]
    
    slope, intercept = linear_regression(x_values, y_values)
    
    assert slope is None
    assert intercept is None

def test_predict_value_valid_coefficients():
    result = predict_value(50, 100, 5)
    
    assert result == 350

def test_predict_value_none_slope():
    result = predict_value(None, 100, 5)
    
    assert result is None

def test_predict_value_none_intercept():
    result = predict_value(50, None, 5)
    
    assert result is None
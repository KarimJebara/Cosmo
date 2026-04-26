"""WSGI entry point for production servers (gunicorn).

Usage:
    gunicorn -w 4 -b 0.0.0.0:5002 wsgi:app
"""

from __future__ import annotations

from app import app  # noqa: F401  (re-export for gunicorn)

#!/usr/bin/env python3

import os
import shutil
import sqlite3

import database

DATABASE_PATH = 'data/budget_tracker.db'
MERCHANT_CATEGORY_EXPENSES_FILE = 'data/merchant_category_expenses.json'
MERCHANT_CATEGORY_INCOME_FILE = 'data/merchant_category_income.json'
DATA_DIR = 'data'


def remove_file_if_exists(filepath):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"[OK] Removed: {filepath}")
        else:
            print(f"[OK] Already removed: {filepath}")
    except Exception as e:
        print(f"[ERROR] Error removing {filepath}: {e}")


def ensure_data_directory():
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
            print(f"[OK] Created directory: {DATA_DIR}")
        else:
            print(f"[OK] Data directory exists: {DATA_DIR}")
    except Exception as e:
        print(f"[ERROR] Error creating data directory: {e}")


def is_database_corrupted():
    """Check if database file is corrupted"""
    if not os.path.exists(DATABASE_PATH):
        return False

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        conn.close()

        is_corrupted = result[0] != 'ok'
        if is_corrupted:
            print(f"[WARNING] Database integrity check failed: {result[0]}")
        return is_corrupted
    except Exception as e:
        print(f"[WARNING] Could not verify database integrity: {e}")
        return True


def reset_database():
    """Reset the database by clearing all data or rebuilding if corrupted"""
    try:
        # Check if database exists and is valid
        if os.path.exists(DATABASE_PATH):
            if is_database_corrupted():
                print("[WARNING] Database appears corrupted, rebuilding...")
                remove_file_if_exists(DATABASE_PATH)
            else:
                # Database is valid, just clear the data
                try:
                    database.drop_all_users_and_data()
                    print("[OK] All database data cleared")
                    return
                except Exception as e:
                    print(f"[WARNING] Could not clear data cleanly: {e}")
                    print("[WARNING] Rebuilding database instead...")
                    remove_file_if_exists(DATABASE_PATH)

        # Initialize fresh database
        database.init_db()
        print("[OK] Database initialized")
    except Exception as e:
        print(f"[ERROR] Error resetting database: {e}")


def reset_merchant_categories():
    try:
        remove_file_if_exists(MERCHANT_CATEGORY_EXPENSES_FILE)
        remove_file_if_exists(MERCHANT_CATEGORY_INCOME_FILE)
        print("[OK] Merchant categories reset")
    except Exception as e:
        print(f"[ERROR] Error resetting merchant categories: {e}")


def reset_cache():
    try:
        cache_dirs = []
        for root, dirs, _files in os.walk('.'):
            if '__pycache__' in dirs:
                cache_path = os.path.join(root, '__pycache__')
                cache_dirs.append(cache_path)

        for cache_dir in cache_dirs:
            try:
                shutil.rmtree(cache_dir)
                print(f"[OK] Cleared cache: {cache_dir}")
            except Exception as e:
                print(f"[ERROR] Error clearing {cache_dir}: {e}")
    except Exception as e:
        print(f"[ERROR] Error clearing cache: {e}")


def main():
    print("=" * 60)
    print("TESTING DATA RESET UTILITY")
    print("=" * 60)
    print()
    print("Starting reset process...")
    print()
    ensure_data_directory()
    print()
    print("Resetting database...")
    reset_database()
    print()
    print("Resetting merchant categories...")
    reset_merchant_categories()
    print()
    print("Clearing Python cache...")
    reset_cache()
    print()
    print("=" * 60)
    print("RESET COMPLETE")
    print("=" * 60)


if __name__ == '__main__':
    main()

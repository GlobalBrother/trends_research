"""
Apply the SQLite schema (sqlite_schema.sql) to the local trends.db.

Usage:
    PYTHONPATH="." python src/db/setup_sqlite.py
"""

import os
import sys
import sqlite3

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

DB_PATH = os.getenv("DB_PATH", os.path.join(project_root, "src", "collector", "trends.db"))
SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "sqlite_schema.sql")


def run():
    print(f"Database : {DB_PATH}")
    print(f"Schema   : {SCHEMA_FILE}")

    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema_sql)
    conn.close()

    print("SQLite schema setup completed successfully.")


if __name__ == "__main__":
    run()

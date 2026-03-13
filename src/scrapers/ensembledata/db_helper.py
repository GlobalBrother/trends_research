"""
Shared database helper for ensembledata scrapers.
Inserts trend rows and scrape errors into the SQLite trends.db used by the rest of the project.
"""

import json
import os
import sqlite3
from datetime import datetime


DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "collector", "trends.db"))


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def save_trend(platform, topic, growth, keyword, geo, url, extra_data=None):
    """Insert a single trend row into the trends table."""
    conn = _get_connection()
    extracted_at = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO trends (platform, topic, growth, keyword, geo, url, extracted_at, extra_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (platform, topic, growth, keyword, geo, url, extracted_at, json.dumps(extra_data or {})),
    )
    conn.execute(
        "INSERT OR REPLACE INTO scrape_log (platform, identifier, status, extracted_at) VALUES (?, ?, ?, ?)",
        (platform, f"{keyword}_{geo}" if geo else keyword, 200, extracted_at),
    )
    conn.commit()
    conn.close()


def save_error(platform, keyword, url, status, reason):
    """Insert a scrape error row."""
    conn = _get_connection()
    conn.execute(
        "INSERT INTO scrape_errors (platform, keyword, url, status, reason, extracted_at) VALUES (?, ?, ?, ?, ?, ?)",
        (platform, keyword, url, status, reason, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

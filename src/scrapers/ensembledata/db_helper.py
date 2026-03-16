"""
Shared database helper for ensembledata scrapers.
Inserts trend rows and scrape errors into the SQLite trends.db used by the rest of the project.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "collector", "trends.db")))


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def save_trend(platform, topic, growth, keyword, geo, url, extra_data=None):
    """Insert a single trend row into the trends table."""
    conn = _get_connection()
    extracted_at = datetime.now().isoformat()
    try:
        conn.execute(
            "INSERT INTO trends (platform, topic, growth, keyword, geo, url, extracted_at, extra_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (platform, topic, growth, keyword, geo, url, extracted_at, json.dumps(extra_data or {})),
        )
        conn.execute(
            "INSERT OR REPLACE INTO scrape_log (platform, identifier, status, extracted_at) VALUES (?, ?, ?, ?)",
            (platform, f"{keyword}_{geo}" if geo else keyword, 200, extracted_at),
        )
        conn.commit()
        logger.debug("Saved trend: platform=%s, topic=%.60s, keyword=%s", platform, topic, keyword)
    except Exception:
        logger.error("Failed to save trend: platform=%s, keyword=%s", platform, keyword, exc_info=True)
        raise
    finally:
        conn.close()


def save_token_usage(platform, keyword, units_charged, geo=""):
    """Record EnsembleData API token/units consumption."""
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT INTO token_usage (platform, keyword, units_charged, geo, created_at) VALUES (?, ?, ?, ?, ?)",
            (platform, keyword, units_charged, geo, datetime.now().isoformat()),
        )
        conn.commit()
        logger.debug("Saved token usage: platform=%s, keyword=%s, units=%s", platform, keyword, units_charged)
    except Exception:
        logger.error("Failed to save token usage: platform=%s, keyword=%s", platform, keyword, exc_info=True)
    finally:
        conn.close()


def save_error(platform, keyword, url, status, reason):
    """Insert a scrape error row."""
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT INTO scrape_errors (platform, keyword, url, status, reason, extracted_at) VALUES (?, ?, ?, ?, ?, ?)",
            (platform, keyword, url, status, reason, datetime.now().isoformat()),
        )
        conn.commit()
        logger.debug("Saved error: platform=%s, keyword=%s, reason=%.80s", platform, keyword, reason)
    except Exception:
        logger.error("Failed to save error row: platform=%s, keyword=%s", platform, keyword, exc_info=True)
        raise
    finally:
        conn.close()

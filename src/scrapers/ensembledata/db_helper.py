"""
Shared database helper for ensembledata scrapers.
Inserts trend rows and scrape errors into the Azure SQL database used by the rest of the project.
"""

import json
import logging
import os
import sys
from datetime import datetime

from sqlalchemy import text

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.db.connection import get_engine
from src.db.sql_compat import duplicate_check_sql, upsert_scrape_log, tbl

logger = logging.getLogger(__name__)

_engine = get_engine()


def save_trend(platform, topic, growth, keyword, geo, url=None, extra_data=None):
    """Insert a trend row, skipping duplicates by (platform, topic, keyword, geo)."""
    extracted_at = datetime.now().isoformat()
    try:
        # Merge url into extra_data if provided (url column was removed from trends table)
        ed = extra_data.copy() if extra_data else {}
        if url:
            ed["url"] = url

        with _engine.connect() as conn:
            # Skip duplicate: same platform+topic+keyword+geo already exists today
            existing = conn.execute(
                text(duplicate_check_sql()),
                {"platform": platform, "topic": topic, "keyword": keyword, "geo": geo},
            ).fetchone()
            if existing:
                logger.debug("Skipped duplicate trend: platform=%s, topic=%.60s, keyword=%s", platform, topic, keyword)
                return

            conn.execute(
                text(
                    f"INSERT INTO {tbl('trends')} (platform, topic, growth, keyword, geo, extracted_at, extra_data) "
                    "VALUES (:platform, :topic, :growth, :keyword, :geo, :extracted_at, :extra_data)"
                ),
                {
                    "platform": platform, "topic": topic, "growth": growth,
                    "keyword": keyword, "geo": geo, "extracted_at": extracted_at,
                    "extra_data": json.dumps(ed) if ed else None,
                },
            )
            upsert_scrape_log(
                conn, platform,
                f"{keyword}_{geo}" if geo else keyword,
                200, extracted_at,
            )
            conn.commit()
            logger.debug("Saved trend: platform=%s, topic=%.60s, keyword=%s", platform, topic, keyword)
    except Exception:
        logger.error("Failed to save trend: platform=%s, keyword=%s", platform, keyword, exc_info=True)
        raise


def save_token_usage(platform, keyword, units_charged, geo=""):
    """Record EnsembleData API token/units consumption."""
    try:
        with _engine.connect() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {tbl('token_usage')} (platform, keyword, units_charged, geo, created_at) "
                    "VALUES (:platform, :keyword, :units_charged, :geo, :created_at)"
                ),
                {
                    "platform": platform, "keyword": keyword,
                    "units_charged": units_charged, "geo": geo,
                    "created_at": datetime.now().isoformat(),
                },
            )
            conn.commit()
            logger.debug("Saved token usage: platform=%s, keyword=%s, units=%s", platform, keyword, units_charged)
    except Exception:
        logger.error("Failed to save token usage: platform=%s, keyword=%s", platform, keyword, exc_info=True)


def save_error(platform, keyword, url, status, reason):
    """Insert a scrape error row."""
    try:
        with _engine.connect() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {tbl('scrape_errors')} (platform, keyword, url, status, reason, extracted_at) "
                    "VALUES (:platform, :keyword, :url, :status, :reason, :extracted_at)"
                ),
                {
                    "platform": platform, "keyword": keyword, "url": url,
                    "status": status, "reason": reason,
                    "extracted_at": datetime.now().isoformat(),
                },
            )
            conn.commit()
            logger.debug("Saved error: platform=%s, keyword=%s, reason=%.80s", platform, keyword, reason)
    except Exception:
        logger.error("Failed to save error row: platform=%s, keyword=%s", platform, keyword, exc_info=True)
        raise

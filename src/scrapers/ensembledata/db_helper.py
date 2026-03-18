"""
Shared database helper for ensembledata scrapers.
Inserts trend rows and scrape errors into the database used by the rest of the project.
Now uses SQLAlchemy ORM instead of raw SQL.
"""

import json
import logging
import os
import sys
from datetime import datetime

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.db.connection import get_session
from src.db.models import Trend, ScrapeError, TokenUsage
from src.db.sql_compat import (
    is_duplicate_trend, upsert_scrape_log, get_platform_id,
    upsert_author, upsert_content, upsert_content_metrics, upsert_hashtags,
)

logger = logging.getLogger(__name__)


def save_trend(platform, topic, growth, keyword, geo, url=None, extra_data=None):
    """Insert a trend row, skipping duplicates by (platform_id, topic, keyword, geo)."""
    extracted_at = datetime.now()
    try:
        ed = extra_data.copy() if extra_data else {}
        if url:
            ed["url"] = url

        session = get_session()
        try:
            platform_id = get_platform_id(session, platform)

            if is_duplicate_trend(session, platform_id, topic, keyword, geo):
                logger.debug("Skipped duplicate trend: platform=%s, topic=%.60s, keyword=%s", platform, topic, keyword)
                return

            session.add(Trend(
                platform_id=platform_id, topic=topic, growth=growth,
                keyword=keyword, geo=geo, extracted_at=extracted_at,
                extra_data=json.dumps(ed) if ed else None,
            ))
            upsert_scrape_log(
                session, platform,
                f"{keyword}_{geo}" if geo else keyword,
                200, extracted_at.isoformat(),
            )
            session.commit()
            logger.debug("Saved trend: platform=%s, topic=%.60s, keyword=%s", platform, topic, keyword)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception:
        logger.error("Failed to save trend: platform=%s, keyword=%s", platform, keyword, exc_info=True)
        raise


def save_content_normalized(platform, external_id, keyword, geo,
                            text_content="", media_type="", url="", content_created_at=None,
                            author_external_id=None, author_username="", author_full_name="",
                            author_follower_count=0, author_is_verified=0, author_profile_pic="",
                            likes=0, comments=0, shares=0, views=0, saves=0,
                            hashtags=None):
    """Save content into the normalized content/authors/metrics/hashtags tables."""
    try:
        session = get_session()
        try:
            platform_id = get_platform_id(session, platform)

            author_id = None
            if author_external_id:
                author_id = upsert_author(
                    session, platform_id, author_external_id,
                    username=author_username, full_name=author_full_name,
                    follower_count=author_follower_count,
                    is_verified=author_is_verified,
                    profile_pic_url=author_profile_pic,
                )

            content_id = upsert_content(
                session, platform_id, external_id,
                keyword=keyword, geo=geo, text_content=text_content,
                media_type=media_type, url=url,
                created_at=content_created_at, author_id=author_id,
            )

            upsert_content_metrics(
                session, content_id,
                likes=likes, comments=comments, shares=shares,
                views=views, saves=saves,
            )

            if hashtags:
                upsert_hashtags(session, content_id, hashtags)

            session.commit()
            logger.debug("Saved content: platform=%s, external_id=%s", platform, external_id)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception:
        logger.error("Failed to save content: platform=%s, external_id=%s", platform, external_id, exc_info=True)
        raise


def save_token_usage(platform, keyword, units_charged, geo=""):
    """Record EnsembleData API token/units consumption."""
    try:
        session = get_session()
        try:
            session.add(TokenUsage(
                platform=platform, keyword=keyword,
                units_charged=units_charged, geo=geo,
                created_at=datetime.now(),
            ))
            session.commit()
            logger.debug("Saved token usage: platform=%s, keyword=%s, units=%s", platform, keyword, units_charged)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception:
        logger.error("Failed to save token usage: platform=%s, keyword=%s", platform, keyword, exc_info=True)


def save_error(platform, keyword, url, status, reason):
    """Insert a scrape error row."""
    try:
        session = get_session()
        try:
            session.add(ScrapeError(
                platform=platform, keyword=keyword, url=url,
                status=status, reason=reason,
                extracted_at=datetime.now(),
            ))
            session.commit()
            logger.debug("Saved error: platform=%s, keyword=%s, reason=%.80s", platform, keyword, reason)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception:
        logger.error("Failed to save error row: platform=%s, keyword=%s", platform, keyword, exc_info=True)
        raise

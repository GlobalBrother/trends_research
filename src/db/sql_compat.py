"""
SQL compatibility layer for SQLite and Azure SQL Server.
Uses SQLAlchemy ORM models exclusively — no raw SQL.
Provides helper functions so the rest of the codebase
can work with both backends without inline if/else blocks.
"""

import os
import sys
from datetime import datetime, timedelta

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from src.db.connection import is_sqlite
from src.db.models import (
    Platform, User, Author, Content, ContentMetric,
    Hashtag, ContentHashtag, Trend, ScrapeError, ScrapeLog,
    OtpCode, AuthToken, TokenUsage, Niche, AdsInsight,
)


# ---------------------------------------------------------------------------
# Platform ID resolution
# ---------------------------------------------------------------------------

_platform_cache = {}


def get_platform_id(session: Session, platform_name: str) -> int:
    """Return the integer id for a platform name, creating it if needed.

    Results are cached in-process to avoid repeated lookups.
    """
    if platform_name in _platform_cache:
        return _platform_cache[platform_name]

    row = session.query(Platform).filter(Platform.name == platform_name).first()
    if not row:
        row = Platform(name=platform_name)
        session.add(row)
        session.flush()
    _platform_cache[platform_name] = row.id
    return row.id


def get_platform_name(session: Session, platform_id: int) -> str:
    """Return the platform name for a given id."""
    row = session.query(Platform).filter(Platform.id == platform_id).first()
    return row.name if row else ""


# ---------------------------------------------------------------------------
# UPSERT / MERGE for scrape_log
# ---------------------------------------------------------------------------

def upsert_scrape_log(session: Session, platform, identifier, status, extracted_at):
    """Upsert a scrape_log entry."""
    row = session.query(ScrapeLog).filter(
        ScrapeLog.platform == platform,
        ScrapeLog.identifier == identifier,
    ).first()
    if row:
        row.status = status
        row.extracted_at = extracted_at
    else:
        session.add(ScrapeLog(
            platform=platform, identifier=identifier,
            status=status, extracted_at=extracted_at,
        ))


# ---------------------------------------------------------------------------
# Duplicate check for trends
# ---------------------------------------------------------------------------

def is_duplicate_trend(session: Session, platform_id, topic, keyword, geo):
    """Check if a trend already exists today. Returns True if duplicate."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    exists = session.query(Trend).filter(
        Trend.platform_id == platform_id,
        Trend.topic == topic,
        Trend.keyword == keyword,
        Trend.geo == geo,
        Trend.extracted_at > today,
    ).first()
    return exists is not None


# ---------------------------------------------------------------------------
# Conditional INSERT (niches seeding)
# ---------------------------------------------------------------------------

def insert_niche_if_not_exists(session: Session, niche_name, keyword):
    """Insert a niche keyword if it doesn't exist."""
    exists = session.query(Niche).filter(
        Niche.niche_name == niche_name,
        Niche.keyword == keyword,
    ).first()
    if not exists:
        session.add(Niche(niche_name=niche_name, keyword=keyword))


# ---------------------------------------------------------------------------
# OTP verification
# ---------------------------------------------------------------------------

def verify_otp(session: Session, user_id, code):
    """Find a valid (unused, unexpired) OTP. Returns OtpCode or None."""
    cutoff = datetime.now() - timedelta(minutes=10)
    return session.query(OtpCode).filter(
        OtpCode.user_id == user_id,
        OtpCode.code == code,
        OtpCode.used == 0,
        OtpCode.created_at > cutoff,
    ).order_by(OtpCode.created_at.desc()).first()


# ---------------------------------------------------------------------------
# Content helpers for normalized schema (ORM)
# ---------------------------------------------------------------------------

def upsert_author(session: Session, platform_id, external_author_id, username="",
                  full_name="", follower_count=0, is_verified=0, profile_pic_url=""):
    """Insert or update an author row and return the author id."""
    row = session.query(Author).filter(
        Author.platform_id == platform_id,
        Author.external_author_id == external_author_id,
    ).first()
    if row:
        row.username = username
        row.full_name = full_name
        row.follower_count = follower_count
        row.is_verified = is_verified
        row.profile_pic_url = profile_pic_url
        session.flush()
        return row.id
    new_author = Author(
        platform_id=platform_id, external_author_id=external_author_id,
        username=username, full_name=full_name,
        follower_count=follower_count, is_verified=is_verified,
        profile_pic_url=profile_pic_url,
    )
    session.add(new_author)
    session.flush()
    return new_author.id


def _ensure_datetime(val):
    """Convert ISO-format strings to datetime objects; pass through None/datetime."""
    if val is None or isinstance(val, datetime):
        return val
    if isinstance(val, str):
        return datetime.fromisoformat(val)
    return val


def upsert_content(session: Session, platform_id, external_id, keyword="", geo="",
                   text_content="", media_type="", url="", created_at=None, author_id=None):
    """Insert or update a content row and return the content id."""
    created_at = _ensure_datetime(created_at)
    row = session.query(Content).filter(
        Content.platform_id == platform_id,
        Content.external_id == external_id,
    ).first()
    if row:
        row.keyword = keyword
        row.geo = geo
        row.text_content = text_content
        row.media_type = media_type
        row.url = url
        row.created_at = created_at
        row.author_id = author_id
        session.flush()
        return row.id
    new_content = Content(
        platform_id=platform_id, external_id=external_id,
        keyword=keyword, geo=geo, text_content=text_content,
        media_type=media_type, url=url, created_at=created_at,
        author_id=author_id,
    )
    session.add(new_content)
    session.flush()
    return new_content.id


def upsert_content_metrics(session: Session, content_id, likes=0, comments=0, shares=0, views=0, saves=0):
    """Insert or update metrics for a content row."""
    row = session.query(ContentMetric).filter(
        ContentMetric.content_id == content_id,
    ).first()
    if row:
        row.likes = likes
        row.comments = comments
        row.shares = shares
        row.views = views
        row.saves = saves
    else:
        session.add(ContentMetric(
            content_id=content_id, likes=likes, comments=comments,
            shares=shares, views=views, saves=saves,
        ))


def upsert_hashtags(session: Session, content_id, tags):
    """Insert hashtags and link them to content via content_hashtags."""
    for tag in tags:
        tag = tag.strip()
        if not tag:
            continue
        ht = session.query(Hashtag).filter(Hashtag.tag == tag).first()
        if not ht:
            ht = Hashtag(tag=tag)
            session.add(ht)
            session.flush()
        existing = session.query(ContentHashtag).filter(
            ContentHashtag.content_id == content_id,
            ContentHashtag.hashtag_id == ht.id,
        ).first()
        if not existing:
            session.add(ContentHashtag(content_id=content_id, hashtag_id=ht.id))

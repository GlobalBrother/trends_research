"""
SQL compatibility layer for Azure SQL Server.

Uses SQLAlchemy ORM models exclusively — no raw SQL.
Optimized for reduced round-trips: first-row existence checks, bulk lookups, and
session-reuse patterns.
"""

import os
import sys
from datetime import datetime, timedelta

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.db.models import (
    Platform, User, Author, Content, ContentMetric,
    Hashtag, ContentHashtag, Trend, ScrapeError, ScrapeLog,
    OtpCode, AuthToken, TokenUsage, Niche, AdsInsight,
)


# ---------------------------------------------------------------------------
# Platform ID resolution (cached)
# ---------------------------------------------------------------------------

_platform_cache: dict[str, int] = {}


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
    # Check reverse cache first
    for name, pid in _platform_cache.items():
        if pid == platform_id:
            return name
    row = session.query(Platform).filter(Platform.id == platform_id).first()
    if row:
        _platform_cache[row.name] = row.id
        return row.name
    return ""


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
# Duplicate check for trends (dialect-safe first-row existence query)
# ---------------------------------------------------------------------------

def is_duplicate_trend(session: Session, platform_id, topic, keyword, geo) -> bool:
    """Check if a trend already exists today.

    Uses a first-row lookup instead of ``SELECT EXISTS (...)`` because
    SQL Server rejects that syntax while SQLite accepts it. This still
    short-circuits at the database level via ``TOP 1`` / ``LIMIT 1``.
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    row = session.query(Trend.id).filter(
        Trend.platform_id == platform_id,
        Trend.topic == topic,
        Trend.keyword == keyword,
        Trend.geo == geo,
        Trend.extracted_at > today,
    ).first()
    return row is not None


# ---------------------------------------------------------------------------
# Conditional INSERT (niches seeding)
# ---------------------------------------------------------------------------

def insert_niche_if_not_exists(session: Session, niche_name, keyword):
    """Insert a niche keyword if it doesn't exist."""
    already = session.query(Niche.id).filter(
        Niche.niche_name == niche_name,
        Niche.keyword == keyword,
    ).first()
    if not already:
        session.add(Niche(niche_name=niche_name, keyword=keyword))


# ---------------------------------------------------------------------------
# OTP verification
# ---------------------------------------------------------------------------

def verify_otp(session: Session, email, code):
    """Find a valid (unused, unexpired) OTP for the given email.
    If found, marks the OTP as used and returns the user_id. Otherwise returns None.

    Uses a UTC cutoff timestamp computed in Python, keeping the query in
    ORM style and avoiding backend-specific SQL functions.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    otp = session.query(OtpCode).join(User).filter(
        User.email == email,
        OtpCode.code == code,
        OtpCode.used == 0,
        OtpCode.created_at > cutoff,
    ).order_by(OtpCode.created_at.desc()).first()
    
    if otp:
        otp.used = 1
        session.flush()
        return otp.user_id
    return None


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
    """Insert hashtags and link them to content via content_hashtags.

    Optimized: pre-fetches all existing hashtags for the given tags in a
    single IN query, and pre-fetches existing links, to avoid N+1 lookups.
    """
    clean_tags = [t.strip() for t in tags if t and t.strip()]
    if not clean_tags:
        return

    # Bulk-fetch existing hashtags matching any of the tags
    existing_hashtags = {
        ht.tag: ht
        for ht in session.query(Hashtag).filter(Hashtag.tag.in_(clean_tags)).all()
    }

    # Ensure all hashtags exist, collecting their IDs
    tag_to_id: dict[str, int] = {}
    for tag in clean_tags:
        if tag in existing_hashtags:
            tag_to_id[tag] = existing_hashtags[tag].id
        else:
            ht = Hashtag(tag=tag)
            session.add(ht)
            session.flush()
            tag_to_id[tag] = ht.id

    # Bulk-fetch existing links for this content
    existing_links = set()
    if tag_to_id:
        rows = session.query(ContentHashtag.hashtag_id).filter(
            ContentHashtag.content_id == content_id,
            ContentHashtag.hashtag_id.in_(tag_to_id.values()),
        ).all()
        existing_links = {r.hashtag_id for r in rows}

    # Insert only missing links
    for tag, ht_id in tag_to_id.items():
        if ht_id not in existing_links:
            session.add(ContentHashtag(content_id=content_id, hashtag_id=ht_id))

"""
SQL compatibility layer for Azure SQL Server.

Uses SQLAlchemy ORM models exclusively — no raw SQL.
Optimized for reduced round-trips: EXISTS checks, bulk lookups, and
session-reuse patterns.
"""

import os
import sys
from datetime import datetime, timedelta

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import func, and_, exists, text
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
# Duplicate check for trends (optimized with EXISTS)
# ---------------------------------------------------------------------------

def is_duplicate_trend(session: Session, platform_id, topic, keyword, geo) -> bool:
    """Check if a trend already exists today.

    Uses an EXISTS subquery instead of loading the full row, which is
    significantly faster on large tables — the DB can stop scanning as
    soon as it finds one matching row.
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return session.query(
        exists().where(
            and_(
                Trend.platform_id == platform_id,
                Trend.topic == topic,
                Trend.keyword == keyword,
                Trend.geo == geo,
                Trend.extracted_at > today,
            )
        )
    ).scalar()


# ---------------------------------------------------------------------------
# Conditional INSERT (niches seeding)
# ---------------------------------------------------------------------------

def insert_niche_if_not_exists(session: Session, niche_name, keyword, is_seed: bool = False):
    """Insert a niche keyword if it doesn't exist (uses EXISTS check).

    Existing rows are never modified — this preserves any user edits to
    ``is_seed`` and other columns. Pass ``is_seed=True`` only when seeding
    from ``NICHE_SEED_KEYWORDS``.
    """
    already = session.query(
        exists().where(
            and_(Niche.niche_name == niche_name, Niche.keyword == keyword)
        )
    ).scalar()
    if not already:
        session.add(Niche(niche_name=niche_name, keyword=keyword, is_seed=bool(is_seed)))


def seed_niches(session: Session) -> int:
    """Idempotently seed the niches table from ``NICHE_SEED_KEYWORDS``.

    Inserts each (niche_name, keyword) pair with ``is_seed=True`` if it
    does not already exist. Never updates existing rows, so user edits and
    user-created niches are preserved across restarts.

    Returns the number of newly inserted rows.
    """
    # Local import to avoid a circular import at module load time.
    from src.niche.niche_discovery import NICHE_SEED_KEYWORDS

    inserted = 0
    for niche_name, keywords in NICHE_SEED_KEYWORDS.items():
        for kw in keywords:
            already = session.query(
                exists().where(
                    and_(Niche.niche_name == niche_name, Niche.keyword == kw)
                )
            ).scalar()
            if not already:
                session.add(Niche(niche_name=niche_name, keyword=kw, is_seed=True))
                inserted += 1
    return inserted


def reset_niches_to_defaults(session: Session) -> dict:
    """Delete all seed-owned niche rows and re-seed from defaults.

    User-created rows (``is_seed = False``) are left untouched.
    Returns a dict with ``deleted`` and ``inserted`` counts.
    """
    deleted = session.query(Niche).filter(Niche.is_seed == True).delete(  # noqa: E712
        synchronize_session=False
    )
    session.flush()
    inserted = seed_niches(session)
    return {"deleted": int(deleted or 0), "inserted": inserted}


# ---------------------------------------------------------------------------
# OTP verification
# ---------------------------------------------------------------------------

def verify_otp(session: Session, user_id, code):
    """Find a valid (unused, unexpired) OTP. Returns OtpCode or None.

    Uses ``func.getutcdate()`` so the 10-minute window is evaluated
    server-side in UTC, matching the ``server_default=func.now()`` on
    ``OtpCode.created_at`` (which is UTC on Azure SQL).
    """
    return session.query(OtpCode).filter(
        OtpCode.user_id == user_id,
        OtpCode.code == code,
        OtpCode.used == 0,
        OtpCode.created_at > func.dateadd(text("minute"), -10, func.getutcdate()),
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

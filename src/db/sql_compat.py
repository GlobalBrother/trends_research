"""
SQL compatibility layer for SQLite and Azure SQL Server.
Now uses SQLAlchemy ORM models instead of raw SQL.
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
# Schema-qualified table names (kept for raw-SQL fallback in dynamic queries)
# ---------------------------------------------------------------------------

def tbl(table_name: str) -> str:
    """Return schema-qualified table name.

    SQLite  → ``table_name``  (no schema prefix)
    MSSQL   → ``dbo.table_name``
    """
    if is_sqlite():
        return table_name
    return f"dbo.{table_name}"


# ---------------------------------------------------------------------------
# Platform ID resolution
# ---------------------------------------------------------------------------

_platform_cache = {}


def get_platform_id(session, platform_name: str) -> int:
    """Return the integer id for a platform name, creating it if needed.

    Accepts either a SQLAlchemy Session or a raw Connection (for backward compat).
    Results are cached in-process to avoid repeated lookups.
    """
    if platform_name in _platform_cache:
        return _platform_cache[platform_name]

    # Support both Session and Connection objects
    if isinstance(session, Session):
        row = session.query(Platform).filter(Platform.name == platform_name).first()
        if not row:
            row = Platform(name=platform_name)
            session.add(row)
            session.flush()
        _platform_cache[platform_name] = row.id
        return row.id
    else:
        # Legacy Connection path
        from sqlalchemy import text as _text
        _t = tbl('platforms')
        row = session.execute(
            _text(f"SELECT id FROM {_t} WHERE name = :name"),
            {"name": platform_name},
        ).fetchone()
        if row:
            _platform_cache[platform_name] = row[0]
            return row[0]
        if is_sqlite():
            session.execute(
                _text(f"INSERT OR IGNORE INTO {_t} (name) VALUES (:name)"),
                {"name": platform_name},
            )
        else:
            session.execute(
                _text(
                    f"IF NOT EXISTS (SELECT 1 FROM {_t} WHERE name = :name) "
                    f"INSERT INTO {_t} (name) VALUES (:name)"
                ),
                {"name": platform_name},
            )
        row = session.execute(
            _text(f"SELECT id FROM {_t} WHERE name = :name"),
            {"name": platform_name},
        ).fetchone()
        _platform_cache[platform_name] = row[0]
        return row[0]


def get_platform_name(session, platform_id: int) -> str:
    """Return the platform name for a given id."""
    if isinstance(session, Session):
        row = session.query(Platform).filter(Platform.id == platform_id).first()
        return row.name if row else ""
    else:
        from sqlalchemy import text as _text
        _t = tbl('platforms')
        row = session.execute(
            _text(f"SELECT name FROM {_t} WHERE id = :id"),
            {"id": platform_id},
        ).fetchone()
        return row[0] if row else ""


# ---------------------------------------------------------------------------
# UPSERT / MERGE for scrape_log
# ---------------------------------------------------------------------------

def upsert_scrape_log(session, platform, identifier, status, extracted_at):
    """Upsert a scrape_log entry."""
    if isinstance(session, Session):
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
        return

    # Legacy Connection path
    from sqlalchemy import text as _text
    params = {"platform": platform, "identifier": identifier, "status": status, "extracted_at": extracted_at}
    if is_sqlite():
        _t = tbl('scrape_log')
        session.execute(_text(
            f"DELETE FROM {_t} WHERE platform = :platform AND identifier = :identifier"
        ), params)
        session.execute(_text(
            f"INSERT INTO {_t} (platform, identifier, status, extracted_at) "
            "VALUES (:platform, :identifier, :status, :extracted_at)"
        ), params)
    else:
        _t = tbl('scrape_log')
        session.execute(_text(
            f"MERGE {_t} AS target "
            "USING (SELECT :platform AS platform, :identifier AS identifier) AS source "
            "ON target.platform = source.platform AND target.identifier = source.identifier "
            "WHEN MATCHED THEN UPDATE SET status = :status, extracted_at = :extracted_at "
            "WHEN NOT MATCHED THEN INSERT (platform, identifier, status, extracted_at) "
            "VALUES (:platform, :identifier, :status, :extracted_at);"
        ), params)


# ---------------------------------------------------------------------------
# Duplicate check for trends
# ---------------------------------------------------------------------------

def is_duplicate_trend(session, platform_id, topic, keyword, geo):
    """Check if a trend already exists today. Returns True if duplicate."""
    if isinstance(session, Session):
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        exists = session.query(Trend).filter(
            Trend.platform_id == platform_id,
            Trend.topic == topic,
            Trend.keyword == keyword,
            Trend.geo == geo,
            Trend.extracted_at > today,
        ).first()
        return exists is not None

    # Legacy: return SQL string for Connection usage
    raise TypeError("is_duplicate_trend requires a Session object")


def duplicate_check_sql():
    """Return SQL to check if a trend already exists today (legacy Connection support)."""
    _t = tbl('trends')
    if is_sqlite():
        return (
            f"SELECT 1 FROM {_t} WHERE platform_id = :platform_id AND topic = :topic "
            "AND keyword = :keyword AND geo = :geo "
            "AND extracted_at > date('now')"
        )
    return (
        f"SELECT 1 FROM {_t} WHERE platform_id = :platform_id AND topic = :topic "
        "AND keyword = :keyword AND geo = :geo "
        "AND extracted_at > CAST(GETDATE() AS DATE)"
    )


# ---------------------------------------------------------------------------
# Conditional INSERT (niches seeding)
# ---------------------------------------------------------------------------

def insert_niche_if_not_exists(session, niche_name, keyword):
    """Insert a niche keyword if it doesn't exist."""
    if isinstance(session, Session):
        exists = session.query(Niche).filter(
            Niche.niche_name == niche_name,
            Niche.keyword == keyword,
        ).first()
        if not exists:
            session.add(Niche(niche_name=niche_name, keyword=keyword))
        return

    # Legacy Connection path
    from sqlalchemy import text as _text
    _t = tbl('niches')
    if is_sqlite():
        session.execute(
            _text(f"INSERT OR IGNORE INTO {_t} (niche_name, keyword) VALUES (:niche_name, :kw)"),
            {"niche_name": niche_name, "kw": keyword},
        )
    else:
        session.execute(
            _text(
                f"IF NOT EXISTS ("
                f"    SELECT 1 FROM {_t} WHERE niche_name = :niche_name AND keyword = :kw"
                ") "
                f"INSERT INTO {_t} (niche_name, keyword) VALUES (:niche_name, :kw)"
            ),
            {"niche_name": niche_name, "kw": keyword},
        )


def insert_if_not_exists_niches():
    """Return SQL to insert a niche keyword if it doesn't exist (legacy)."""
    _t = tbl('niches')
    if is_sqlite():
        return (
            f"INSERT OR IGNORE INTO {_t} (niche_name, keyword) "
            "VALUES (:niche_name, :kw)"
        )
    return (
        f"IF NOT EXISTS ("
        f"    SELECT 1 FROM {_t} WHERE niche_name = :niche_name AND keyword = :kw"
        ") "
        f"INSERT INTO {_t} (niche_name, keyword) VALUES (:niche_name, :kw)"
    )


# ---------------------------------------------------------------------------
# OTP verification
# ---------------------------------------------------------------------------

def verify_otp(session, user_id, code):
    """Find a valid (unused, unexpired) OTP. Returns OtpCode or None."""
    if isinstance(session, Session):
        cutoff = datetime.now() - timedelta(minutes=10)
        return session.query(OtpCode).filter(
            OtpCode.user_id == user_id,
            OtpCode.code == code,
            OtpCode.used == 0,
            OtpCode.created_at > cutoff,
        ).order_by(OtpCode.created_at.desc()).first()

    raise TypeError("verify_otp requires a Session object")


def otp_verify_sql():
    """Return SQL to find a valid (unused, unexpired) OTP (legacy)."""
    _t = tbl('otp_codes')
    if is_sqlite():
        return (
            f"SELECT id, code FROM {_t} WHERE user_id = :user_id AND code = :code AND used = 0 "
            "AND datetime(created_at, '+10 minutes') > datetime('now') "
            "ORDER BY created_at DESC LIMIT 1"
        )
    return (
        f"SELECT id, code FROM {_t} WHERE user_id = :user_id AND code = :code AND used = 0 "
        "AND DATEADD(MINUTE, 10, created_at) > GETDATE() "
        "ORDER BY created_at DESC OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY"
    )


# ---------------------------------------------------------------------------
# Date / time helpers (kept for raw-SQL fallback)
# ---------------------------------------------------------------------------

def today_start():
    """SQL expression for the start of today (midnight)."""
    if is_sqlite():
        return "date('now')"
    return "CAST(GETDATE() AS DATE)"


def now():
    """SQL expression for current timestamp."""
    if is_sqlite():
        return "datetime('now')"
    return "GETDATE()"


def minutes_ago(col, minutes):
    """SQL expression: <col> + <minutes> minutes > now."""
    if is_sqlite():
        return f"datetime({col}, '+{minutes} minutes') > datetime('now')"
    return f"DATEADD(MINUTE, {minutes}, {col}) > GETDATE()"


def expires_check(col):
    """SQL expression: <col> > now (for token expiry)."""
    if is_sqlite():
        return f"{col} > datetime('now')"
    return f"{col} > GETDATE()"


# ---------------------------------------------------------------------------
# LIMIT / TOP (kept for raw-SQL fallback)
# ---------------------------------------------------------------------------

def limit_clause(order_by, limit):
    """Return ORDER BY ... LIMIT/OFFSET FETCH clause."""
    if is_sqlite():
        return f" ORDER BY {order_by} LIMIT {limit}"
    return f" ORDER BY {order_by} OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"


def top_clause(n):
    """Return TOP N or empty string (SQLite uses LIMIT instead)."""
    if is_sqlite():
        return ""
    return f"TOP {n} "


def top_limit_suffix(n):
    """Return LIMIT N for SQLite (appended at end) or empty for mssql (uses TOP)."""
    if is_sqlite():
        return f" LIMIT {n}"
    return ""


# ---------------------------------------------------------------------------
# Content helpers for normalized schema (ORM)
# ---------------------------------------------------------------------------

def upsert_author(session, platform_id, external_author_id, username="",
                  full_name="", follower_count=0, is_verified=0, profile_pic_url=""):
    """Insert or update an author row and return the author id."""
    if isinstance(session, Session):
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

    # Legacy Connection path
    from sqlalchemy import text as _text
    _t = tbl('authors')
    row = session.execute(
        _text(f"SELECT id FROM {_t} WHERE platform_id = :platform_id AND external_author_id = :ext_id"),
        {"platform_id": platform_id, "ext_id": external_author_id},
    ).fetchone()
    if row:
        session.execute(
            _text(
                f"UPDATE {_t} SET username = :username, full_name = :full_name, "
                "follower_count = :follower_count, is_verified = :is_verified, "
                "profile_pic_url = :profile_pic_url "
                "WHERE id = :id"
            ),
            {
                "username": username, "full_name": full_name,
                "follower_count": follower_count, "is_verified": is_verified,
                "profile_pic_url": profile_pic_url, "id": row[0],
            },
        )
        return row[0]
    session.execute(
        _text(
            f"INSERT INTO {_t} (platform_id, external_author_id, username, full_name, "
            "follower_count, is_verified, profile_pic_url) "
            "VALUES (:platform_id, :ext_id, :username, :full_name, "
            ":follower_count, :is_verified, :profile_pic_url)"
        ),
        {
            "platform_id": platform_id, "ext_id": external_author_id,
            "username": username, "full_name": full_name,
            "follower_count": follower_count, "is_verified": is_verified,
            "profile_pic_url": profile_pic_url,
        },
    )
    row = session.execute(
        _text(f"SELECT id FROM {_t} WHERE platform_id = :platform_id AND external_author_id = :ext_id"),
        {"platform_id": platform_id, "ext_id": external_author_id},
    ).fetchone()
    return row[0]


def upsert_content(session, platform_id, external_id, keyword="", geo="",
                   text_content="", media_type="", url="", created_at=None, author_id=None):
    """Insert or update a content row and return the content id."""
    if isinstance(session, Session):
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

    # Legacy Connection path
    from sqlalchemy import text as _text
    _t = tbl('content')
    row = session.execute(
        _text(f"SELECT id FROM {_t} WHERE platform_id = :platform_id AND external_id = :ext_id"),
        {"platform_id": platform_id, "ext_id": external_id},
    ).fetchone()
    if row:
        session.execute(
            _text(
                f"UPDATE {_t} SET keyword = :keyword, geo = :geo, text_content = :text_content, "
                "media_type = :media_type, url = :url, created_at = :created_at, author_id = :author_id "
                "WHERE id = :id"
            ),
            {
                "keyword": keyword, "geo": geo, "text_content": text_content,
                "media_type": media_type, "url": url, "created_at": created_at,
                "author_id": author_id, "id": row[0],
            },
        )
        return row[0]
    session.execute(
        _text(
            f"INSERT INTO {_t} (platform_id, external_id, keyword, geo, text_content, "
            "media_type, url, created_at, author_id) "
            "VALUES (:platform_id, :ext_id, :keyword, :geo, :text_content, "
            ":media_type, :url, :created_at, :author_id)"
        ),
        {
            "platform_id": platform_id, "ext_id": external_id,
            "keyword": keyword, "geo": geo, "text_content": text_content,
            "media_type": media_type, "url": url, "created_at": created_at,
            "author_id": author_id,
        },
    )
    row = session.execute(
        _text(f"SELECT id FROM {_t} WHERE platform_id = :platform_id AND external_id = :ext_id"),
        {"platform_id": platform_id, "ext_id": external_id},
    ).fetchone()
    return row[0]


def upsert_content_metrics(session, content_id, likes=0, comments=0, shares=0, views=0, saves=0):
    """Insert or update metrics for a content row."""
    if isinstance(session, Session):
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
        return

    # Legacy Connection path
    from sqlalchemy import text as _text
    _t = tbl('content_metrics')
    row = session.execute(
        _text(f"SELECT id FROM {_t} WHERE content_id = :content_id"),
        {"content_id": content_id},
    ).fetchone()
    if row:
        session.execute(
            _text(
                f"UPDATE {_t} SET likes = :likes, comments = :comments, shares = :shares, "
                "views = :views, saves = :saves WHERE id = :id"
            ),
            {"likes": likes, "comments": comments, "shares": shares,
             "views": views, "saves": saves, "id": row[0]},
        )
    else:
        session.execute(
            _text(
                f"INSERT INTO {_t} (content_id, likes, comments, shares, views, saves) "
                "VALUES (:content_id, :likes, :comments, :shares, :views, :saves)"
            ),
            {"content_id": content_id, "likes": likes, "comments": comments,
             "shares": shares, "views": views, "saves": saves},
        )


def upsert_hashtags(session, content_id, tags):
    """Insert hashtags and link them to content via content_hashtags."""
    if isinstance(session, Session):
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
        return

    # Legacy Connection path
    from sqlalchemy import text as _text
    _ht = tbl('hashtags')
    _cht = tbl('content_hashtags')
    for tag in tags:
        tag = tag.strip()
        if not tag:
            continue
        row = session.execute(
            _text(f"SELECT id FROM {_ht} WHERE tag = :tag"),
            {"tag": tag},
        ).fetchone()
        if not row:
            if is_sqlite():
                session.execute(_text(f"INSERT OR IGNORE INTO {_ht} (tag) VALUES (:tag)"), {"tag": tag})
            else:
                session.execute(
                    _text(f"IF NOT EXISTS (SELECT 1 FROM {_ht} WHERE tag = :tag) INSERT INTO {_ht} (tag) VALUES (:tag)"),
                    {"tag": tag},
                )
            row = session.execute(
                _text(f"SELECT id FROM {_ht} WHERE tag = :tag"),
                {"tag": tag},
            ).fetchone()
        hashtag_id = row[0]
        existing = session.execute(
            _text(f"SELECT 1 FROM {_cht} WHERE content_id = :cid AND hashtag_id = :hid"),
            {"cid": content_id, "hid": hashtag_id},
        ).fetchone()
        if not existing:
            session.execute(
                _text(f"INSERT INTO {_cht} (content_id, hashtag_id) VALUES (:cid, :hid)"),
                {"cid": content_id, "hid": hashtag_id},
            )

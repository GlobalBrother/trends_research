"""
SQLAlchemy ORM models for the trends_research database.

Mirrors the schema defined in azure_schema.sql.
Works with Azure SQL Server backend.

Index Strategy
--------------
Every foreign key, every column used in WHERE / ORDER BY / JOIN ON in the
API or scraper write paths has an explicit index.  Composite indexes are
ordered to match the most selective column first.
"""

import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import (
    Column, Integer, Text, Float, DateTime, ForeignKey, UniqueConstraint, Index,
    String, Boolean, func, text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ---------------------------------------------------------------------------
# 1. LOOKUP / REFERENCE TABLES
# ---------------------------------------------------------------------------

class Platform(Base):
    __tablename__ = "platforms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)

    # relationships
    authors = relationship("Author", back_populates="platform", lazy="select")
    content_items = relationship("Content", back_populates="platform", lazy="select")
    trends = relationship("Trend", back_populates="platform", lazy="select")


# ---------------------------------------------------------------------------
# 2. CORE TABLES
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(320), nullable=False, unique=True)
    role = Column(String(20), nullable=False, default="trends")
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    otp_codes = relationship("OtpCode", back_populates="user", lazy="select")
    auth_tokens = relationship("AuthToken", back_populates="user", lazy="select")


class Author(Base):
    __tablename__ = "authors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(Integer, ForeignKey("platforms.id"), nullable=False)
    external_author_id = Column(Text)
    username = Column(Text)
    full_name = Column(Text)
    follower_count = Column(Integer)
    is_verified = Column(Integer)
    profile_pic_url = Column(Text)

    platform = relationship("Platform", back_populates="authors")
    content_items = relationship("Content", back_populates="author", lazy="select")

    __table_args__ = (
        Index("idx_authors_platform", "platform_id"),
        Index("idx_authors_external", "platform_id", "external_author_id"),
    )


class Content(Base):
    __tablename__ = "content"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(Integer, ForeignKey("platforms.id"), nullable=False)
    external_id = Column(Text, nullable=False)
    keyword = Column(Text)
    geo = Column(Text)
    text_content = Column(Text)
    media_type = Column(Text)
    url = Column(Text)
    created_at = Column(DateTime)
    author_id = Column(Integer, ForeignKey("authors.id"))

    platform = relationship("Platform", back_populates="content_items")
    author = relationship("Author", back_populates="content_items")
    metrics = relationship("ContentMetric", back_populates="content", uselist=False, lazy="joined")
    hashtag_links = relationship("ContentHashtag", back_populates="content", lazy="select")

    __table_args__ = (
        Index("idx_content_platform", "platform_id"),
        Index("idx_content_keyword", "keyword"),
        Index("idx_content_external", "platform_id", "external_id"),
        Index("idx_content_created", "created_at"),
        Index("idx_content_author", "author_id"),
    )


class ContentMetric(Base):
    __tablename__ = "content_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_id = Column(Integer, ForeignKey("content.id"), nullable=False, unique=True)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    views = Column(Integer, default=0)
    saves = Column(Integer, default=0)

    content = relationship("Content", back_populates="metrics")

    __table_args__ = (
        Index("idx_metrics_content", "content_id"),
    )


class Hashtag(Base):
    __tablename__ = "hashtags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tag = Column(Text, unique=True)

    content_links = relationship("ContentHashtag", back_populates="hashtag", lazy="select")


class ContentHashtag(Base):
    __tablename__ = "content_hashtags"

    content_id = Column(Integer, ForeignKey("content.id"), primary_key=True)
    hashtag_id = Column(Integer, ForeignKey("hashtags.id"), primary_key=True)

    content = relationship("Content", back_populates="hashtag_links")
    hashtag = relationship("Hashtag", back_populates="content_links")


class Trend(Base):
    __tablename__ = "trends"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(Integer, ForeignKey("platforms.id"))
    topic = Column(Text)
    growth = Column(Float)
    keyword = Column(Text)
    geo = Column(Text)
    extracted_at = Column(DateTime)
    extra_data = Column(Text)

    platform = relationship("Platform", back_populates="trends")

    __table_args__ = (
        Index("idx_trends_platform_id", "platform_id"),
        Index("idx_trends_keyword", "keyword"),
        Index("idx_trends_geo", "geo"),
        Index("idx_trends_extracted_at", "extracted_at"),
        # Composite index for the duplicate-check query:
        # WHERE platform_id=? AND topic=? AND keyword=? AND geo=? AND extracted_at>?
        Index("idx_trends_dedup", "platform_id", "keyword", "geo", "extracted_at"),
    )


class ScrapeError(Base):
    __tablename__ = "scrape_errors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(Text)
    keyword = Column(Text)
    url = Column(Text)
    status = Column(Integer)
    reason = Column(Text)
    extracted_at = Column(DateTime)

    __table_args__ = (
        Index("idx_error_platform", "platform"),
        Index("idx_error_extracted_at", "extracted_at"),
    )


class ScrapeLog(Base):
    __tablename__ = "scrape_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(Text)
    identifier = Column(Text)
    status = Column(Integer)
    extracted_at = Column(DateTime)

    __table_args__ = (
        Index("idx_log_platform_id", "platform", "identifier"),
        Index("idx_log_extracted", "platform", "identifier", "status", "extracted_at"),
    )


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    code = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    used = Column(Integer, nullable=False, default=0)

    user = relationship("User", back_populates="otp_codes")

    __table_args__ = (
        Index("idx_otp_user", "user_id"),
        Index("idx_otp_lookup", "user_id", "code", "used", "created_at"),
    )


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(128), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User", back_populates="auth_tokens")

    __table_args__ = (
        Index("idx_authtoken_token", "token"),
        Index("idx_authtoken_user_expires", "user_id", "expires_at"),
    )


class TokenUsage(Base):
    __tablename__ = "token_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(Text, nullable=False)
    keyword = Column(Text)
    units_charged = Column(Float, nullable=False, default=0)
    geo = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_tokenusage_platform", "platform"),
        Index("idx_tokenusage_created", "created_at"),
        Index("idx_tokenusage_platform_created", "platform", "created_at"),
    )


class RawDataArchive(Base):
    __tablename__ = "raw_data_archive"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_table = Column(Text, nullable=False)
    source_id = Column(Integer, nullable=False)
    raw_data = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_raw_source", "source_table", "source_id"),
    )


class Niche(Base):
    __tablename__ = "niches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    niche_name = Column(Text, nullable=False)
    keyword = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    is_seed = Column(Boolean, nullable=False, default=False, server_default=text("0"))

    __table_args__ = (
        UniqueConstraint("niche_name", "keyword", name="uq_niches_name_keyword"),
        Index("idx_niches_name", "niche_name"),
    )


class AdsInsight(Base):
    __tablename__ = "ads_insight"

    id = Column(Integer, primary_key=True, autoincrement=True)
    hookd_id = Column(Integer)
    external_id = Column(Text)
    search_keyword = Column(Text)
    platform = Column(Text)
    display_format = Column(Text)
    title = Column(Text)
    body = Column(Text)
    landing_page = Column(Text)
    link_description = Column(Text)
    cta_type = Column(Text)
    cta_text = Column(Text)
    start_date = Column(Text)
    end_date = Column(Text)
    days_active = Column(Integer)
    active_in_library = Column(Integer)
    performance_score = Column(Integer)
    performance_score_title = Column(Text)
    used_count = Column(Integer)
    is_aaa_eligible = Column(Integer)
    age_audience_min = Column(Integer)
    age_audience_max = Column(Integer)
    gender_audience = Column(Text)
    eu_total_reach = Column(Integer)
    ad_spend_range_score = Column(Integer)
    ad_spend_range_score_title = Column(Text)
    brand_external_id = Column(Text)
    brand_name = Column(Text)
    brand_logo_url = Column(Text)
    brand_active_ads = Column(Integer)
    media = Column(Text)
    ad_cards = Column(Text)
    share_url = Column(Text)
    extracted_at = Column(DateTime)
    updated_at = Column(DateTime)

    __table_args__ = (
        Index("idx_ads_keyword", "search_keyword"),
        Index("idx_ads_extracted", "extracted_at"),
        Index("idx_ads_hookd_id", "hookd_id"),
    )

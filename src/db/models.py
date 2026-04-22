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
        # Covering index for the main API query:
        # WHERE platform_id IN (...) AND geo=? ORDER BY extracted_at DESC
        Index("idx_trends_api_query", "platform_id", "geo", "extracted_at"),
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


class MyBrand(Base):
    """Brands the user is tracking via GetHooked Brand Spy."""
    __tablename__ = "my_brands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_name = Column(Text, nullable=False)
    brand_external_id = Column(Text)
    brand_logo_url = Column(Text)
    brand_active_ads = Column(Integer, default=0)
    added_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_mybrand_name", "brand_name"),
        Index("idx_mybrand_external", "brand_external_id"),
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


class TrendCluster(Base):
    __tablename__ = "trend_clusters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_key = Column(String(255), nullable=False, unique=True)
    title = Column(Text, nullable=False)
    cluster_keywords = Column(Text)
    platforms = Column(Text)
    primary_platform = Column(String(100))
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    lifecycle_stage = Column(String(32), nullable=False, default="watchlist")
    confidence_score = Column(Float, nullable=False, default=0.0)
    freshness_score = Column(Float, nullable=False, default=0.0)
    source_confidence = Column(Float, nullable=False, default=0.0)
    trend_strength = Column(Float, nullable=False, default=0.0)
    quality_score = Column(Float, nullable=False, default=0.0)
    source_count = Column(Integer, nullable=False, default=0)
    signal_count = Column(Integer, nullable=False, default=0)
    geo_coverage = Column(Integer, nullable=False, default=0)
    explanation_json = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_cluster_stage", "lifecycle_stage"),
        Index("idx_cluster_last_seen", "last_seen"),
        Index("idx_cluster_primary_platform", "primary_platform"),
        {"implicit_returning": False},
    )


class TrendSignal(Base):
    __tablename__ = "trend_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, ForeignKey("trend_clusters.id"), nullable=False)
    source_trend_id = Column(Integer, ForeignKey("trends.id"))
    platform = Column(String(100), nullable=False)
    topic = Column(Text)
    keyword = Column(Text)
    geo = Column(Text)
    signal_timestamp = Column(DateTime, nullable=False)
    volume = Column(Float, nullable=False, default=0.0)
    growth = Column(Float, nullable=False, default=0.0)
    engagement = Column(Float, nullable=False, default=0.0)
    sentiment = Column(Float, nullable=False, default=0.0)
    freshness = Column(Float, nullable=False, default=0.0)
    source_confidence = Column(Float, nullable=False, default=0.0)
    quality_flags = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_signal_cluster", "cluster_id"),
        Index("idx_signal_platform", "platform"),
        Index("idx_signal_timestamp", "signal_timestamp"),
        {"implicit_returning": False},
    )


class TrendInsight(Base):
    __tablename__ = "trend_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, ForeignKey("trend_clusters.id"), nullable=False, unique=True)
    ad_opportunity_score = Column(Float, nullable=False, default=0.0)
    trend_strength = Column(Float, nullable=False, default=0.0)
    confidence_score = Column(Float, nullable=False, default=0.0)
    audience_intent = Column(Text)
    creative_angle_candidates = Column(Text)
    platform_fit = Column(Text)
    ad_timing_window = Column(Text)
    saturation_risk = Column(Float, nullable=False, default=0.0)
    brand_safety_risk = Column(Float, nullable=False, default=0.0)
    monetization_potential = Column(Float, nullable=False, default=0.0)
    commercial_relevance = Column(Float, nullable=False, default=0.0)
    audience_signal = Column(Float, nullable=False, default=0.0)
    creative_reusability = Column(Float, nullable=False, default=0.0)
    explanation_json = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_insight_score", "ad_opportunity_score"),
        Index("idx_insight_confidence", "confidence_score"),
        {"implicit_returning": False},
    )


class TrendAdMatch(Base):
    __tablename__ = "trend_ad_matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, ForeignKey("trend_clusters.id"), nullable=False)
    ads_insight_id = Column(Integer, ForeignKey("ads_insight.id"), nullable=False)
    match_score = Column(Float, nullable=False, default=0.0)
    match_reason = Column(Text)
    matched_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_match_cluster", "cluster_id"),
        Index("idx_match_ad", "ads_insight_id"),
        Index("idx_match_score", "match_score"),
        {"implicit_returning": False},
    )


class InsightFeedback(Base):
    __tablename__ = "insight_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, ForeignKey("trend_clusters.id"), nullable=False)
    insight_id = Column(Integer, ForeignKey("trend_insights.id"))
    useful = Column(Integer, nullable=False, default=0)
    rating = Column(Integer)
    used_in_campaign = Column(Integer, nullable=False, default=0)
    outcome = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_feedback_cluster", "cluster_id"),
        Index("idx_feedback_insight", "insight_id"),
        {"implicit_returning": False},
    )


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_label = Column(String(255), nullable=False)
    window_start = Column(DateTime)
    window_end = Column(DateTime)
    total_clusters = Column(Integer, nullable=False, default=0)
    matched_clusters = Column(Integer, nullable=False, default=0)
    avg_opportunity_score = Column(Float, nullable=False, default=0.0)
    precision_proxy = Column(Float, nullable=False, default=0.0)
    recall_proxy = Column(Float, nullable=False, default=0.0)
    summary_json = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_backtest_created", "created_at"),
        {"implicit_returning": False},
    )


class ReportBrief(Base):
    __tablename__ = "report_briefs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_type = Column(String(64), nullable=False)
    title = Column(Text, nullable=False)
    cluster_id = Column(Integer, ForeignKey("trend_clusters.id"))
    content_json = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_report_type", "report_type"),
        Index("idx_report_created", "created_at"),
        {"implicit_returning": False},
    )


class CanonicalTrendSignal(Base):
    __tablename__ = "canonical_trend_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(100), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(255), nullable=False)
    label = Column(Text, nullable=False)
    normalized_label = Column(Text, nullable=False)
    country = Column(String(32))
    language = Column(String(32))
    time_bucket_start = Column(DateTime, nullable=False)
    granularity = Column(String(32), nullable=False, default="hour")
    volume = Column(Float)
    growth_rate = Column(Float)
    rank = Column(Integer)
    engagement = Column(Float)
    velocity = Column(Float)
    sampled_content_refs = Column(Text)
    retrieved_at = Column(DateTime, nullable=False)
    fetch_metadata = Column(Text)
    idempotency_key = Column(String(128), nullable=False, unique=True)
    source_confidence = Column(Float, nullable=False, default=0.0)
    freshness_score = Column(Float, nullable=False, default=0.0)
    evidence_count = Column(Integer, nullable=False, default=0)
    legacy_trend_id = Column(Integer, ForeignKey("trends.id"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_canonical_source_bucket", "source", "time_bucket_start"),
        Index("idx_canonical_entity", "source", "entity_id"),
        Index("idx_canonical_country", "country"),
        Index("idx_canonical_idempotency", "idempotency_key"),
    )


class TrendEvidence(Base):
    __tablename__ = "trend_evidence"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(Integer, ForeignKey("canonical_trend_signals.id"), nullable=False)
    content_id = Column(Integer, ForeignKey("content.id"))
    evidence_type = Column(String(64), nullable=False, default="content_ref")
    external_ref = Column(Text)
    url = Column(Text)
    title = Column(Text)
    snippet = Column(Text)
    metadata_json = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_evidence_signal", "signal_id"),
        Index("idx_evidence_content", "content_id"),
    )


class SourceCursor(Base):
    __tablename__ = "source_cursors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(100), nullable=False)
    country = Column(String(32))
    language = Column(String(32))
    category = Column(String(100))
    cursor_value = Column(Text)
    response_hash = Column(String(128))
    last_seen_entity_id = Column(String(255))
    last_success_at = Column(DateTime)
    updated_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("source", "country", "language", "category", name="uq_source_cursor_scope"),
        Index("idx_cursor_source", "source"),
    )


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(100), nullable=False)
    acquisition_mode = Column(String(32), nullable=False)
    country = Column(String(32))
    language = Column(String(32))
    category = Column(String(100))
    status = Column(String(32), nullable=False, default="running")
    fetched_count = Column(Integer, nullable=False, default=0)
    parsed_count = Column(Integer, nullable=False, default=0)
    inserted_count = Column(Integer, nullable=False, default=0)
    deduped_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    duplicate_ratio = Column(Float, nullable=False, default=0.0)
    quota_usage = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Float, nullable=False, default=0.0)
    top_error_types = Column(Text)
    stale_window_hours = Column(Float, nullable=False, default=0.0)
    alert_state = Column(String(32), nullable=False, default="ok")
    summary_json = Column(Text)
    started_at = Column(DateTime, nullable=False, server_default=func.now())
    finished_at = Column(DateTime)

    __table_args__ = (
        Index("idx_scrape_run_source_started", "source", "started_at"),
        Index("idx_scrape_run_status", "status"),
    )


class ScrapeDeadLetter(Base):
    __tablename__ = "scrape_dead_letters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(100), nullable=False)
    scrape_run_id = Column(Integer, ForeignKey("scrape_runs.id"))
    cursor_key = Column(Text)
    payload_ref = Column(Text)
    error_type = Column(String(128), nullable=False)
    error_message = Column(Text)
    retry_count = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    resolved_at = Column(DateTime)

    __table_args__ = (
        Index("idx_dead_letter_source", "source"),
        Index("idx_dead_letter_status", "status"),
        Index("idx_dead_letter_run", "scrape_run_id"),
    )

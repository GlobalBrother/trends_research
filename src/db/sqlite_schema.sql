-- ============================================================
-- SQLite Schema Setup for trends.db
-- Mirrors the Azure SQL schema (azure_schema.sql)
-- Generated: 2026-03-17
-- ============================================================

-- ============================================================
-- 1. LOOKUP / REFERENCE TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS platforms (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- ============================================================
-- 2. CORE TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT NOT NULL UNIQUE,
    role       TEXT    NOT NULL DEFAULT 'trends',
    created_at DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS authors (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id         INTEGER NOT NULL REFERENCES platforms(id),
    external_author_id  TEXT,
    username            TEXT,
    full_name           TEXT,
    follower_count      INTEGER,
    is_verified         INTEGER,
    profile_pic_url     TEXT
);

CREATE TABLE IF NOT EXISTS content (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id  INTEGER NOT NULL REFERENCES platforms(id),
    external_id  TEXT    NOT NULL,
    keyword      TEXT,
    geo          TEXT,
    text_content TEXT,
    media_type   TEXT,
    url          TEXT,
    created_at   DATETIME,
    author_id    INTEGER REFERENCES authors(id)
);

CREATE TABLE IF NOT EXISTS content_metrics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER NOT NULL REFERENCES content(id),
    likes      INTEGER DEFAULT 0,
    comments   INTEGER DEFAULT 0,
    shares     INTEGER DEFAULT 0,
    views      INTEGER DEFAULT 0,
    saves      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS hashtags (
    id  INTEGER PRIMARY KEY AUTOINCREMENT,
    tag TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS content_hashtags (
    content_id INTEGER NOT NULL REFERENCES content(id),
    hashtag_id INTEGER NOT NULL REFERENCES hashtags(id),
    PRIMARY KEY (content_id, hashtag_id)
);

CREATE TABLE IF NOT EXISTS trends (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id  INTEGER REFERENCES platforms(id),
    topic        TEXT,
    growth       REAL,
    keyword      TEXT,
    geo          TEXT,
    extracted_at DATETIME,
    extra_data   TEXT
);

CREATE TABLE IF NOT EXISTS scrape_errors (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    platform     TEXT,
    keyword      TEXT,
    url          TEXT,
    status       INTEGER,
    reason       TEXT,
    extracted_at DATETIME
);

CREATE TABLE IF NOT EXISTS scrape_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    platform     TEXT,
    identifier   TEXT,
    status       INTEGER,
    extracted_at DATETIME
);

CREATE TABLE IF NOT EXISTS otp_codes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id),
    code       TEXT    NOT NULL,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    used       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    token      TEXT    NOT NULL,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    expires_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS token_usage (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    platform       TEXT    NOT NULL,
    keyword        TEXT,
    units_charged  REAL    NOT NULL DEFAULT 0,
    geo            TEXT,
    created_at     DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS raw_data_archive (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table TEXT NOT NULL,
    source_id    INTEGER NOT NULL,
    raw_data     TEXT,
    created_at   DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS niches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    niche_name TEXT NOT NULL,
    keyword    TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE (niche_name, keyword)
);

-- Keep ads_insight as a standalone table (not part of normalized content model)
CREATE TABLE IF NOT EXISTS ads_insight (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    hookd_id                   INTEGER,
    external_id                TEXT,
    search_keyword             TEXT,
    platform                   TEXT,
    display_format             TEXT,
    title                      TEXT,
    body                       TEXT,
    landing_page               TEXT,
    link_description           TEXT,
    cta_type                   TEXT,
    cta_text                   TEXT,
    start_date                 TEXT,
    end_date                   TEXT,
    days_active                INTEGER,
    active_in_library          INTEGER,
    performance_score          INTEGER,
    performance_score_title    TEXT,
    used_count                 INTEGER,
    is_aaa_eligible            INTEGER,
    age_audience_min           INTEGER,
    age_audience_max           INTEGER,
    gender_audience            TEXT,
    eu_total_reach             INTEGER,
    ad_spend_range_score       INTEGER,
    ad_spend_range_score_title TEXT,
    brand_external_id          TEXT,
    brand_name                 TEXT,
    brand_logo_url             TEXT,
    brand_active_ads           INTEGER,
    media                      TEXT,
    ad_cards                   TEXT,
    share_url                  TEXT,
    extracted_at               DATETIME,
    updated_at                 DATETIME
);

-- ============================================================
-- 3. INDEXES
-- ============================================================

-- content indexes
CREATE INDEX IF NOT EXISTS idx_content_platform ON content(platform_id);
CREATE INDEX IF NOT EXISTS idx_content_keyword ON content(keyword);
CREATE INDEX IF NOT EXISTS idx_content_external ON content(platform_id, external_id);
CREATE INDEX IF NOT EXISTS idx_content_created ON content(created_at);

-- authors indexes
CREATE INDEX IF NOT EXISTS idx_authors_platform ON authors(platform_id);
CREATE INDEX IF NOT EXISTS idx_authors_external ON authors(platform_id, external_author_id);

-- content_metrics indexes
CREATE INDEX IF NOT EXISTS idx_metrics_content ON content_metrics(content_id);

-- trends indexes
CREATE INDEX IF NOT EXISTS idx_trends_platform_id ON trends(platform_id);
CREATE INDEX IF NOT EXISTS idx_trends_keyword ON trends(keyword);
CREATE INDEX IF NOT EXISTS idx_trends_geo ON trends(geo);
CREATE INDEX IF NOT EXISTS idx_trends_extracted_at ON trends(extracted_at);

-- scrape_errors indexes
CREATE INDEX IF NOT EXISTS idx_error_platform ON scrape_errors(platform);
CREATE INDEX IF NOT EXISTS idx_error_extracted_at ON scrape_errors(extracted_at);

-- scrape_log indexes
CREATE INDEX IF NOT EXISTS idx_log_platform_id ON scrape_log(platform, identifier);
CREATE INDEX IF NOT EXISTS idx_log_extracted ON scrape_log(platform, identifier, status, extracted_at);

-- raw_data_archive indexes
CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_data_archive(source_table, source_id);

-- ads_insight indexes
CREATE INDEX IF NOT EXISTS idx_ads_keyword ON ads_insight(search_keyword);
CREATE INDEX IF NOT EXISTS idx_ads_extracted ON ads_insight(extracted_at);

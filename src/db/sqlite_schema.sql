-- ============================================================
-- SQLite Schema Setup for trends.db
-- Mirrors the Azure SQL schema (azure_schema.sql)
-- Generated: 2026-03-17
-- ============================================================

-- ============================================================
-- 1. CORE TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS trends (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    platform     TEXT,
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

CREATE TABLE IF NOT EXISTS users (
    email      TEXT PRIMARY KEY,
    role       TEXT    NOT NULL DEFAULT 'trends',
    created_at DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS otp_codes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT    NOT NULL,
    code       TEXT    NOT NULL,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    used       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token      TEXT PRIMARY KEY,
    email      TEXT    NOT NULL,
    role       TEXT    NOT NULL,
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

CREATE TABLE IF NOT EXISTS niches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    niche_name TEXT NOT NULL,
    keyword    TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE (niche_name, keyword)
);

CREATE TABLE IF NOT EXISTS raw_data_archive (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table TEXT NOT NULL,
    source_id    INTEGER NOT NULL,
    raw_data     TEXT,
    created_at   DATETIME DEFAULT (datetime('now'))
);

-- ============================================================
-- 2. PLATFORM TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS tiktok_videos (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    aweme_id               TEXT,
    search_keyword         TEXT,
    geo                    TEXT,
    description            TEXT,
    desc_language          TEXT,
    share_url              TEXT,
    region                 TEXT,
    create_time            INTEGER,
    aweme_type             INTEGER,
    duration               INTEGER,
    is_ads                 INTEGER,
    is_top                 INTEGER,
    content_type           TEXT,
    digg_count             INTEGER,
    comment_count          INTEGER,
    share_count            INTEGER,
    play_count             INTEGER,
    download_count         INTEGER,
    forward_count          INTEGER,
    collect_count          INTEGER,
    lose_count             INTEGER,
    lose_comment_count     INTEGER,
    author_uid             TEXT,
    author_unique_id       TEXT,
    author_nickname        TEXT,
    author_signature       TEXT,
    author_region          TEXT,
    author_follower_count  INTEGER,
    author_following_count INTEGER,
    author_total_favorited INTEGER,
    author_avatar_uri      TEXT,
    author_sec_uid         TEXT,
    author_verified        INTEGER,
    author_ins_id          TEXT,
    music_id               TEXT,
    music_title            TEXT,
    music_author           TEXT,
    music_album            TEXT,
    music_duration         INTEGER,
    music_is_original      INTEGER,
    music_is_commerce      INTEGER,
    music_user_count       INTEGER,
    video_height           INTEGER,
    video_width            INTEGER,
    video_ratio            TEXT,
    video_has_watermark    INTEGER,
    video_cover_url        TEXT,
    hashtags               TEXT,
    cha_list               TEXT,
    text_extra             TEXT,
    engagement_total       INTEGER,
    extracted_at           DATETIME,
    updated_at             DATETIME
);

CREATE TABLE IF NOT EXISTS instagram_posts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    post_pk          TEXT,
    shortcode        TEXT,
    search_keyword   TEXT,
    geo              TEXT,
    caption          TEXT,
    media_type       INTEGER,
    url              TEXT,
    thumbnail_url    TEXT,
    taken_at         INTEGER,
    location_name    TEXT,
    location_lat     REAL,
    location_lng     REAL,
    username         TEXT,
    user_pk          TEXT,
    full_name        TEXT,
    follower_count   INTEGER,
    is_verified      INTEGER,
    profile_pic_url  TEXT,
    like_count       INTEGER,
    comment_count    INTEGER,
    share_count      INTEGER,
    save_count       INTEGER,
    video_view_count INTEGER,
    video_play_count INTEGER,
    engagement_total INTEGER,
    hashtags         TEXT,
    extracted_at     DATETIME,
    updated_at       DATETIME
);

CREATE TABLE IF NOT EXISTS youtube_videos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id         TEXT,
    search_keyword   TEXT,
    geo              TEXT,
    title            TEXT,
    description      TEXT,
    channel_title    TEXT,
    channel_id       TEXT,
    published        TEXT,
    duration         TEXT,
    url              TEXT,
    thumbnail_url    TEXT,
    category_id      TEXT,
    tags             TEXT,
    language         TEXT,
    view_count       INTEGER,
    like_count       INTEGER,
    dislike_count    INTEGER,
    comment_count    INTEGER,
    favorite_count   INTEGER,
    engagement_total INTEGER,
    extracted_at     DATETIME,
    updated_at       DATETIME
);

CREATE TABLE IF NOT EXISTS reddit_posts (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id                TEXT,
    search_keyword         TEXT,
    geo                    TEXT,
    title                  TEXT,
    selftext               TEXT,
    url                    TEXT,
    permalink              TEXT,
    domain                 TEXT,
    post_hint              TEXT,
    is_self                INTEGER,
    is_video               INTEGER,
    over_18                INTEGER,
    spoiler                INTEGER,
    created_utc            INTEGER,
    thumbnail              TEXT,
    subreddit              TEXT,
    subreddit_id           TEXT,
    subreddit_subscribers  INTEGER,
    author                 TEXT,
    author_fullname        TEXT,
    score                  INTEGER,
    upvote_ratio           REAL,
    num_comments           INTEGER,
    num_crossposts         INTEGER,
    total_awards           INTEGER,
    engagement_total       INTEGER,
    link_flair_text        TEXT,
    extracted_at           DATETIME,
    updated_at             DATETIME
);

CREATE TABLE IF NOT EXISTS threads_posts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    post_code        TEXT,
    post_pk          TEXT,
    search_keyword   TEXT,
    geo              TEXT,
    caption          TEXT,
    url              TEXT,
    taken_at         INTEGER,
    media_type       TEXT,
    username         TEXT,
    user_pk          TEXT,
    full_name        TEXT,
    follower_count   INTEGER,
    is_verified      INTEGER,
    profile_pic_url  TEXT,
    like_count       INTEGER,
    reply_count      INTEGER,
    repost_count     INTEGER,
    quote_count      INTEGER,
    share_count      INTEGER,
    engagement_total INTEGER,
    extracted_at     DATETIME,
    updated_at       DATETIME
);

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

-- trends indexes
CREATE INDEX IF NOT EXISTS idx_trends_platform ON trends(platform);
CREATE INDEX IF NOT EXISTS idx_trends_keyword ON trends(keyword);
CREATE INDEX IF NOT EXISTS idx_trends_geo ON trends(geo);
CREATE INDEX IF NOT EXISTS idx_trends_extracted_at ON trends(extracted_at);
CREATE INDEX IF NOT EXISTS idx_trends_platform_geo ON trends(platform, geo);
CREATE INDEX IF NOT EXISTS idx_trends_geo_platform_extracted ON trends(geo, platform, extracted_at DESC);

-- scrape_errors indexes
CREATE INDEX IF NOT EXISTS idx_error_platform ON scrape_errors(platform);
CREATE INDEX IF NOT EXISTS idx_error_extracted_at ON scrape_errors(extracted_at);

-- scrape_log indexes
CREATE INDEX IF NOT EXISTS idx_log_platform_id ON scrape_log(platform, identifier);
CREATE INDEX IF NOT EXISTS idx_log_extracted ON scrape_log(platform, identifier, status, extracted_at);

-- raw_data_archive indexes
CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_data_archive(source_table, source_id);

-- Platform table indexes
CREATE INDEX IF NOT EXISTS idx_tiktok_keyword ON tiktok_videos(search_keyword);
CREATE INDEX IF NOT EXISTS idx_tiktok_extracted ON tiktok_videos(extracted_at);
CREATE INDEX IF NOT EXISTS idx_instagram_keyword ON instagram_posts(search_keyword);
CREATE INDEX IF NOT EXISTS idx_instagram_extracted ON instagram_posts(extracted_at);
CREATE INDEX IF NOT EXISTS idx_youtube_keyword ON youtube_videos(search_keyword);
CREATE INDEX IF NOT EXISTS idx_youtube_extracted ON youtube_videos(extracted_at);
CREATE INDEX IF NOT EXISTS idx_reddit_keyword ON reddit_posts(search_keyword);
CREATE INDEX IF NOT EXISTS idx_reddit_extracted ON reddit_posts(extracted_at);
CREATE INDEX IF NOT EXISTS idx_threads_keyword ON threads_posts(search_keyword);
CREATE INDEX IF NOT EXISTS idx_threads_extracted ON threads_posts(extracted_at);
CREATE INDEX IF NOT EXISTS idx_ads_keyword ON ads_insight(search_keyword);
CREATE INDEX IF NOT EXISTS idx_ads_extracted ON ads_insight(extracted_at);

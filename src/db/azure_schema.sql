-- ============================================================
-- Azure SQL Server Schema Setup for trends.db migration
-- Target: gb-ads-sql-server.database.windows.net / GB_Reporting_DB
-- Generated: 2026-03-17
-- ============================================================

-- ============================================================
-- 1. CORE TABLES
-- ============================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'trends')
CREATE TABLE trends (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    platform    NVARCHAR(100),
    topic       NVARCHAR(500),
    growth      FLOAT,
    keyword     NVARCHAR(255),
    geo         NVARCHAR(100),
    extracted_at DATETIME2,
    extra_data  NVARCHAR(MAX)
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'scrape_errors')
CREATE TABLE scrape_errors (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    platform     NVARCHAR(100),
    keyword      NVARCHAR(255),
    url          NVARCHAR(2000),
    status       INT,
    reason       NVARCHAR(MAX),
    extracted_at DATETIME2
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'scrape_log')
CREATE TABLE scrape_log (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    platform     NVARCHAR(100),
    identifier   NVARCHAR(500),
    status       INT,
    extracted_at DATETIME2
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'users')
CREATE TABLE users (
    email      NVARCHAR(320) PRIMARY KEY,
    role       NVARCHAR(50)  NOT NULL DEFAULT 'trends',
    created_at DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'otp_codes')
CREATE TABLE otp_codes (
    id         INT IDENTITY(1,1) PRIMARY KEY,
    email      NVARCHAR(320) NOT NULL,
    code       NVARCHAR(20)  NOT NULL,
    created_at DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    used       BIT           NOT NULL DEFAULT 0
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'auth_tokens')
CREATE TABLE auth_tokens (
    token      NVARCHAR(500) PRIMARY KEY,
    email      NVARCHAR(320) NOT NULL,
    role       NVARCHAR(50)  NOT NULL,
    created_at DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    expires_at DATETIME2     NOT NULL
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'token_usage')
CREATE TABLE token_usage (
    id             INT IDENTITY(1,1) PRIMARY KEY,
    platform       NVARCHAR(100) NOT NULL,
    keyword        NVARCHAR(255),
    units_charged  FLOAT         NOT NULL DEFAULT 0,
    geo            NVARCHAR(100),
    created_at     DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'niches')
CREATE TABLE niches (
    id         INT IDENTITY(1,1) PRIMARY KEY,
    niche_name NVARCHAR(255) NOT NULL,
    keyword    NVARCHAR(255) NOT NULL,
    created_at DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_niches_name_keyword UNIQUE (niche_name, keyword)
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'raw_data_archive')
CREATE TABLE raw_data_archive (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    source_table NVARCHAR(100) NOT NULL,
    source_id    INT           NOT NULL,
    raw_data     NVARCHAR(MAX),
    created_at   DATETIME2     DEFAULT SYSUTCDATETIME()
);

-- ============================================================
-- 2. PLATFORM TABLES
-- ============================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'tiktok_videos')
CREATE TABLE tiktok_videos (
    id                     INT IDENTITY(1,1) PRIMARY KEY,
    aweme_id               NVARCHAR(100),
    search_keyword         NVARCHAR(255),
    geo                    NVARCHAR(100),
    description            NVARCHAR(MAX),
    desc_language          NVARCHAR(20),
    share_url              NVARCHAR(2000),
    region                 NVARCHAR(50),
    create_time            INT,
    aweme_type             INT,
    duration               INT,
    is_ads                 BIT,
    is_top                 BIT,
    content_type           NVARCHAR(100),
    digg_count             INT,
    comment_count          INT,
    share_count            INT,
    play_count             INT,
    download_count         INT,
    forward_count          INT,
    collect_count          INT,
    lose_count             INT,
    lose_comment_count     INT,
    author_uid             NVARCHAR(100),
    author_unique_id       NVARCHAR(200),
    author_nickname        NVARCHAR(200),
    author_signature       NVARCHAR(MAX),
    author_region          NVARCHAR(50),
    author_follower_count  INT,
    author_following_count INT,
    author_total_favorited INT,
    author_avatar_uri      NVARCHAR(2000),
    author_sec_uid         NVARCHAR(200),
    author_verified        BIT,
    author_ins_id          NVARCHAR(200),
    music_id               NVARCHAR(100),
    music_title            NVARCHAR(500),
    music_author           NVARCHAR(200),
    music_album            NVARCHAR(500),
    music_duration         INT,
    music_is_original      BIT,
    music_is_commerce      BIT,
    music_user_count       INT,
    video_height           INT,
    video_width            INT,
    video_ratio            NVARCHAR(20),
    video_has_watermark    BIT,
    video_cover_url        NVARCHAR(2000),
    hashtags               NVARCHAR(MAX),
    cha_list               NVARCHAR(MAX),
    text_extra             NVARCHAR(MAX),
    engagement_total       INT,
    extracted_at           DATETIME2,
    updated_at             DATETIME2
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'instagram_posts')
CREATE TABLE instagram_posts (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    post_pk          NVARCHAR(100),
    shortcode        NVARCHAR(100),
    search_keyword   NVARCHAR(255),
    geo              NVARCHAR(100),
    caption          NVARCHAR(MAX),
    media_type       INT,
    url              NVARCHAR(2000),
    thumbnail_url    NVARCHAR(2000),
    taken_at         INT,
    location_name    NVARCHAR(500),
    location_lat     FLOAT,
    location_lng     FLOAT,
    username         NVARCHAR(200),
    user_pk          NVARCHAR(100),
    full_name        NVARCHAR(200),
    follower_count   INT,
    is_verified      BIT,
    profile_pic_url  NVARCHAR(2000),
    like_count       INT,
    comment_count    INT,
    share_count      INT,
    save_count       INT,
    video_view_count INT,
    video_play_count INT,
    engagement_total INT,
    hashtags         NVARCHAR(MAX),
    extracted_at     DATETIME2,
    updated_at       DATETIME2
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'youtube_videos')
CREATE TABLE youtube_videos (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    video_id         NVARCHAR(100),
    search_keyword   NVARCHAR(255),
    geo              NVARCHAR(100),
    title            NVARCHAR(500),
    description      NVARCHAR(MAX),
    channel_title    NVARCHAR(200),
    channel_id       NVARCHAR(100),
    published        NVARCHAR(50),
    duration         NVARCHAR(50),
    url              NVARCHAR(2000),
    thumbnail_url    NVARCHAR(2000),
    category_id      NVARCHAR(20),
    tags             NVARCHAR(MAX),
    language         NVARCHAR(20),
    view_count       INT,
    like_count       INT,
    dislike_count    INT,
    comment_count    INT,
    favorite_count   INT,
    engagement_total INT,
    extracted_at     DATETIME2,
    updated_at       DATETIME2
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'reddit_posts')
CREATE TABLE reddit_posts (
    id                     INT IDENTITY(1,1) PRIMARY KEY,
    post_id                NVARCHAR(100),
    search_keyword         NVARCHAR(255),
    geo                    NVARCHAR(100),
    title                  NVARCHAR(500),
    selftext               NVARCHAR(MAX),
    url                    NVARCHAR(2000),
    permalink              NVARCHAR(2000),
    domain                 NVARCHAR(500),
    post_hint              NVARCHAR(100),
    is_self                BIT,
    is_video               BIT,
    over_18                BIT,
    spoiler                BIT,
    created_utc            INT,
    thumbnail              NVARCHAR(2000),
    subreddit              NVARCHAR(200),
    subreddit_id           NVARCHAR(100),
    subreddit_subscribers  INT,
    author                 NVARCHAR(200),
    author_fullname        NVARCHAR(200),
    score                  INT,
    upvote_ratio           FLOAT,
    num_comments           INT,
    num_crossposts         INT,
    total_awards           INT,
    engagement_total       INT,
    link_flair_text        NVARCHAR(200),
    extracted_at           DATETIME2,
    updated_at             DATETIME2
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'threads_posts')
CREATE TABLE threads_posts (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    post_code        NVARCHAR(100),
    post_pk          NVARCHAR(100),
    search_keyword   NVARCHAR(255),
    geo              NVARCHAR(100),
    caption          NVARCHAR(MAX),
    url              NVARCHAR(2000),
    taken_at         INT,
    media_type       NVARCHAR(100),
    username         NVARCHAR(200),
    user_pk          NVARCHAR(100),
    full_name        NVARCHAR(200),
    follower_count   INT,
    is_verified      BIT,
    profile_pic_url  NVARCHAR(2000),
    like_count       INT,
    reply_count      INT,
    repost_count     INT,
    quote_count      INT,
    share_count      INT,
    engagement_total INT,
    extracted_at     DATETIME2,
    updated_at       DATETIME2
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ads_insight')
CREATE TABLE ads_insight (
    id                         INT IDENTITY(1,1) PRIMARY KEY,
    hookd_id                   INT,
    external_id                NVARCHAR(200),
    search_keyword             NVARCHAR(255),
    platform                   NVARCHAR(100),
    display_format             NVARCHAR(100),
    title                      NVARCHAR(500),
    body                       NVARCHAR(MAX),
    landing_page               NVARCHAR(2000),
    link_description           NVARCHAR(MAX),
    cta_type                   NVARCHAR(100),
    cta_text                   NVARCHAR(200),
    start_date                 NVARCHAR(50),
    end_date                   NVARCHAR(50),
    days_active                INT,
    active_in_library          BIT,
    performance_score          INT,
    performance_score_title    NVARCHAR(100),
    used_count                 INT,
    is_aaa_eligible            BIT,
    age_audience_min           INT,
    age_audience_max           INT,
    gender_audience            NVARCHAR(50),
    eu_total_reach             INT,
    ad_spend_range_score       INT,
    ad_spend_range_score_title NVARCHAR(100),
    brand_external_id          NVARCHAR(200),
    brand_name                 NVARCHAR(200),
    brand_logo_url             NVARCHAR(2000),
    brand_active_ads           INT,
    media                      NVARCHAR(MAX),
    ad_cards                   NVARCHAR(MAX),
    share_url                  NVARCHAR(2000),
    extracted_at               DATETIME2,
    updated_at                 DATETIME2
);

-- ============================================================
-- 3. INDEXES
-- ============================================================

-- trends indexes
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_trends_platform')
    CREATE INDEX idx_trends_platform ON trends(platform);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_trends_keyword')
    CREATE INDEX idx_trends_keyword ON trends(keyword);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_trends_geo')
    CREATE INDEX idx_trends_geo ON trends(geo);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_trends_extracted_at')
    CREATE INDEX idx_trends_extracted_at ON trends(extracted_at);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_trends_platform_geo')
    CREATE INDEX idx_trends_platform_geo ON trends(platform, geo);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_trends_geo_platform_extracted')
    CREATE INDEX idx_trends_geo_platform_extracted ON trends(geo, platform, extracted_at DESC);

-- scrape_errors indexes
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_error_platform')
    CREATE INDEX idx_error_platform ON scrape_errors(platform);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_error_extracted_at')
    CREATE INDEX idx_error_extracted_at ON scrape_errors(extracted_at);

-- scrape_log indexes
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_log_platform_id')
    CREATE INDEX idx_log_platform_id ON scrape_log(platform, identifier);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_log_extracted')
    CREATE INDEX idx_log_extracted ON scrape_log(platform, identifier, status, extracted_at);

-- raw_data_archive indexes
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_raw_source')
    CREATE INDEX idx_raw_source ON raw_data_archive(source_table, source_id);

-- Platform table indexes for common queries
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_tiktok_keyword')
    CREATE INDEX idx_tiktok_keyword ON tiktok_videos(search_keyword);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_tiktok_extracted')
    CREATE INDEX idx_tiktok_extracted ON tiktok_videos(extracted_at);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_instagram_keyword')
    CREATE INDEX idx_instagram_keyword ON instagram_posts(search_keyword);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_instagram_extracted')
    CREATE INDEX idx_instagram_extracted ON instagram_posts(extracted_at);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_youtube_keyword')
    CREATE INDEX idx_youtube_keyword ON youtube_videos(search_keyword);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_youtube_extracted')
    CREATE INDEX idx_youtube_extracted ON youtube_videos(extracted_at);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_reddit_keyword')
    CREATE INDEX idx_reddit_keyword ON reddit_posts(search_keyword);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_reddit_extracted')
    CREATE INDEX idx_reddit_extracted ON reddit_posts(extracted_at);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_threads_keyword')
    CREATE INDEX idx_threads_keyword ON threads_posts(search_keyword);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_threads_extracted')
    CREATE INDEX idx_threads_extracted ON threads_posts(extracted_at);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_ads_keyword')
    CREATE INDEX idx_ads_keyword ON ads_insight(search_keyword);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_ads_extracted')
    CREATE INDEX idx_ads_extracted ON ads_insight(extracted_at);

PRINT 'Azure SQL schema setup completed successfully.';

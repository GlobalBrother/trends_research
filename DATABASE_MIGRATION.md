# Database Optimization & Azure SQL Migration Guide

## Key Findings from Analysis

| Issue | Detail |
|-------|--------|
| **Massive duplicates in `trends`** | 169,559 rows but only **7,371 unique** rows by `(platform, topic, keyword, geo, growth, extracted_at)` — **~95.7% are duplicates** |
| **`trends.url` is 97.7% NULL** | Only 3,842 of 169,559 rows have a URL |
| **`tiktok_videos` has duplicate columns** | `duration` and `video_duration` are always identical |
| **No NOT NULL constraints** on `trends` | `platform`, `topic`, `keyword`, `geo` should never be NULL |
| **`raw_data` blobs are huge** | TikTok avg 72KB, YouTube avg 18KB, ads_insight max 255KB per row |
| **No normalization** | Author data repeated in every platform post table; platform names stored as strings everywhere |
| **Denormalized `Google Regions`** | 161,823 rows (95% of trends) are all `Google Regions` — likely time-series data that could be stored more efficiently |
| **No foreign keys** between tables |
| **Inconsistent timestamp formats** | `trends` uses `DATETIME`, platform tables use `TEXT`, TikTok uses `INTEGER` (epoch) |

---

## Current Table Row Counts

| Table | Rows |
|-------|------|
| trends | 169,559 |
| scrape_log | 9,863 |
| ads_insight | 1,080 |
| instagram_posts | 561 |
| tiktok_videos | 290 |
| youtube_videos | 283 |
| token_usage | 169 |
| scrape_errors | 97 |
| niches | 83 |
| threads_posts | 34 |
| reddit_posts | 25 |
| auth_tokens | 13 |
| users | 13 |
| otp_codes | 17 |

---

## Platform Distribution (trends table)

| Platform | Count |
|----------|-------|
| Google Regions | 161,823 |
| Google Interest | 3,604 |
| YouTube | 1,325 |
| HackerNews | 717 |
| TikTok | 614 |
| Instagram | 566 |
| GetHookdAI | 260 |
| Google Related Queries | 210 |
| Reddit | 195 |
| Google Trends | 80 |
| Threads | 74 |
| News | 50 |
| X (Twitter) | 38 |
| Facebook | 3 |

---

## Optimization 1 — Deduplicate `trends` (Critical)

This alone will shrink the biggest table from **169,559 → ~7,371 rows**.

```sql
-- Run this BEFORE migration in SQLite:
CREATE TABLE trends_clean AS
SELECT MIN(id) AS id, platform, topic, growth, keyword, geo, url, extracted_at, extra_data
FROM trends
GROUP BY platform, topic, keyword, geo, growth, extracted_at;

-- Verify
SELECT COUNT(*) FROM trends_clean;  -- Should be ~7,371

-- Swap
DROP TABLE trends;
ALTER TABLE trends_clean RENAME TO trends;

-- Recreate indexes
CREATE INDEX idx_platform ON trends(platform);
CREATE INDEX idx_keyword ON trends(keyword);
CREATE INDEX idx_geo ON trends(geo);
CREATE INDEX idx_extracted_at ON trends(extracted_at);
CREATE INDEX idx_platform_geo ON trends(platform, geo);
CREATE INDEX idx_geo_platform_extracted ON trends(geo, platform, extracted_at DESC);
```

---

## Optimization 2 — Drop `trends.url` Column (97.7% NULL)

Since only 3,842 rows have a URL and those URLs likely come from platforms like YouTube/HackerNews that already have their own tables with URLs, simply don't include the `url` column in the Azure SQL schema.

If you want to preserve the 3,842 URLs before dropping:

```python
import sqlite3, json
conn = sqlite3.connect('src/collector/trends.db')
rows = conn.execute("SELECT id, url, extra_data FROM trends WHERE url IS NOT NULL").fetchall()
for row_id, url, extra in rows:
    data = json.loads(extra) if extra else {}
    data['url'] = url
    conn.execute("UPDATE trends SET extra_data = ? WHERE id = ?", (json.dumps(data), row_id))
conn.commit()
```

---

## Optimization 3 — Remove Duplicate `tiktok_videos` Columns

`duration` and `video_duration` are always identical. In the Azure SQL schema, only keep `duration_ms` (don't create `video_duration`).

---

## Optimization 4 — Compress/Archive `raw_data` Blobs

`raw_data` is the biggest storage consumer.

### Option A — Drop `raw_data` entirely (recommended)
If you've already extracted all needed fields into columns, don't include `raw_data` in the Azure SQL schema. Optionally archive to Azure Blob Storage.

### Option B — Move to a separate table
Keeps main tables fast for queries:

```sql
CREATE TABLE raw_data_archive (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    source_table    NVARCHAR(50) NOT NULL,
    source_id       INT NOT NULL,
    raw_data        NVARCHAR(MAX),
    created_at      DATETIME2 DEFAULT GETDATE()
);
CREATE INDEX idx_raw_source ON raw_data_archive(source_table, source_id);
```

### Storage savings estimate

| Table | Rows | Avg raw_data | Total |
|-------|------|-------------|-------|
| tiktok_videos | 290 | 72 KB | ~20 MB |
| youtube_videos | 283 | 18 KB | ~5 MB |
| ads_insight | 1,080 | 4.6 KB | ~5 MB |
| threads_posts | 34 | 10 KB | ~0.3 MB |
| reddit_posts | 25 | 4.7 KB | ~0.1 MB |
| instagram_posts | 561 | 1.6 KB | ~0.9 MB |

---

## Optimization 5 — Normalize Platform Names with a Lookup Table

Instead of storing `'Google Interest'`, `'TikTok'`, etc. as strings in every row:

```sql
CREATE TABLE platforms (
    id      TINYINT IDENTITY(1,1) PRIMARY KEY,
    name    NVARCHAR(50) NOT NULL UNIQUE
);

INSERT INTO platforms (name) VALUES
('Google Regions'), ('Google Interest'), ('YouTube'), ('HackerNews'),
('TikTok'), ('Instagram'), ('GetHookdAI'), ('Google Related Queries'),
('Reddit'), ('Google Trends'), ('Threads'), ('News'), ('X (Twitter)'), ('Facebook');
```

Then reference `platform_id TINYINT` (1 byte) instead of `NVARCHAR` (up to 30 bytes) in `trends`, `scrape_log`, `scrape_errors`, `token_usage`.

---

## Optimization 6 — Add Proper Constraints

```sql
-- Use NOT NULL on: platform_id, topic, keyword, geo, extracted_at

-- Add unique constraint to prevent future duplicates
CREATE UNIQUE INDEX uq_trends_natural ON trends(platform_id, topic, keyword, geo, extracted_at);
```

---

## Optimization 7 — Standardize Timestamps

Use `DATETIME2` everywhere in Azure SQL. Convert TikTok's epoch integers during migration:

```python
from datetime import datetime
# Python: datetime.utcfromtimestamp(create_time).isoformat()
```

---

## Optimization 8 — Proper Data Types for Azure SQL

| SQLite Column | Current | Optimized Azure SQL Type | Why |
|--------------|---------|-------------------------|-----|
| `platform` | TEXT | `TINYINT` (FK to platforms) | 14 distinct values, saves space |
| `geo` | TEXT | `CHAR(2)` or `NVARCHAR(10)` | ISO country codes, max 6 chars |
| `growth` | REAL | `DECIMAL(10,2)` | Precise numeric, not floating point |
| `keyword` | TEXT | `NVARCHAR(200)` | Bounded length |
| `topic` | TEXT | `NVARCHAR(500)` | Bounded length |
| `url` | TEXT | `NVARCHAR(2048)` | Standard URL max |
| `extra_data` | TEXT | `NVARCHAR(MAX)` | JSON blob |
| `is_ads`, `is_verified`, etc. | INTEGER | `BIT` | Boolean values |
| `like_count`, `share_count`, etc. | INTEGER | `INT` | Correct |
| `engagement_total` | INTEGER | `INT` (computed column) | Can be computed on-the-fly |
| `extracted_at` | TEXT/DATETIME | `DATETIME2` | Consistent |

---

## Summary of Optimizations

| Optimization | Impact |
|-------------|--------|
| **Deduplicate `trends`** | 169,559 → ~7,371 rows (**95.7% reduction**) |
| **Drop `trends.url`** | 97.7% NULL column removed |
| **Platform lookup table** | String → TINYINT (1 byte vs 30 bytes per row) |
| **`engagement_total` as computed column** | No storage, always accurate |
| **`raw_data` → separate archive table** | ~31 MB out of main query tables |
| **Drop duplicate `video_duration`** | Redundant column removed |
| **Drop deprecated columns** | `dislike_count`, `favorite_count`, `lose_count`, etc. |
| **Proper data types** | `BIT` for booleans, `DECIMAL` for precise numbers, `DATE` for dates |
| **NOT NULL constraints** | Data integrity enforced |
| **UNIQUE constraints on `trends`** | Prevents future duplicates |
| **Standardized `DATETIME2`** | Consistent timestamps across all tables |
| **Bounded `NVARCHAR(n)`** | Better query optimizer hints vs `NVARCHAR(MAX)` |

---

## Final Optimized Azure SQL Schema

```sql
-- ============================================
-- LOOKUP TABLES
-- ============================================

CREATE TABLE platforms (
    id      TINYINT IDENTITY(1,1) PRIMARY KEY,
    name    NVARCHAR(50) NOT NULL UNIQUE
);

INSERT INTO platforms (name) VALUES
('Google Regions'),('Google Interest'),('YouTube'),('HackerNews'),
('TikTok'),('Instagram'),('GetHookdAI'),('Google Related Queries'),
('Reddit'),('Google Trends'),('Threads'),('News'),('X (Twitter)'),('Facebook');

-- ============================================
-- CORE TABLES
-- ============================================

CREATE TABLE trends (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    platform_id     TINYINT NOT NULL REFERENCES platforms(id),
    topic           NVARCHAR(500) NOT NULL,
    growth          DECIMAL(10,2),
    keyword         NVARCHAR(200) NOT NULL,
    geo             NVARCHAR(10) NOT NULL DEFAULT 'US',
    extracted_at    DATETIME2 NOT NULL,
    extra_data      NVARCHAR(MAX),
    CONSTRAINT uq_trends UNIQUE (platform_id, topic, keyword, geo, extracted_at)
);
CREATE INDEX idx_trends_platform ON trends(platform_id);
CREATE INDEX idx_trends_keyword ON trends(keyword);
CREATE INDEX idx_trends_geo ON trends(geo);
CREATE INDEX idx_trends_extracted ON trends(extracted_at);
CREATE INDEX idx_trends_geo_plat_ext ON trends(geo, platform_id, extracted_at DESC);

CREATE TABLE scrape_log (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    platform_id     TINYINT NOT NULL REFERENCES platforms(id),
    identifier      NVARCHAR(500) NOT NULL,
    status          SMALLINT NOT NULL,
    extracted_at    DATETIME2 NOT NULL
);
CREATE INDEX idx_log_plat_id ON scrape_log(platform_id, identifier);
CREATE INDEX idx_log_full ON scrape_log(platform_id, identifier, status, extracted_at);

CREATE TABLE scrape_errors (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    platform_id     TINYINT NOT NULL REFERENCES platforms(id),
    keyword         NVARCHAR(200),
    url             NVARCHAR(2048),
    status          SMALLINT,
    reason          NVARCHAR(MAX),
    extracted_at    DATETIME2 NOT NULL
);
CREATE INDEX idx_err_platform ON scrape_errors(platform_id);
CREATE INDEX idx_err_extracted ON scrape_errors(extracted_at);

-- ============================================
-- PLATFORM POST TABLES
-- ============================================

CREATE TABLE tiktok_videos (
    id                      INT IDENTITY(1,1) PRIMARY KEY,
    aweme_id                NVARCHAR(50) NOT NULL UNIQUE,
    search_keyword          NVARCHAR(200),
    geo                     NVARCHAR(10),
    description             NVARCHAR(MAX),
    desc_language           NVARCHAR(10),
    share_url               NVARCHAR(2048),
    region                  NVARCHAR(10),
    create_time             DATETIME2,
    aweme_type              TINYINT,
    duration_ms             INT,
    is_ads                  BIT DEFAULT 0,
    is_top                  BIT DEFAULT 0,
    content_type            NVARCHAR(50),
    -- statistics
    digg_count              INT DEFAULT 0,
    comment_count           INT DEFAULT 0,
    share_count             INT DEFAULT 0,
    play_count              INT DEFAULT 0,
    download_count          INT DEFAULT 0,
    forward_count           INT DEFAULT 0,
    collect_count           INT DEFAULT 0,
    -- author
    author_uid              NVARCHAR(50),
    author_unique_id        NVARCHAR(100),
    author_nickname         NVARCHAR(200),
    author_signature        NVARCHAR(MAX),
    author_region           NVARCHAR(10),
    author_follower_count   INT DEFAULT 0,
    author_following_count  INT DEFAULT 0,
    author_total_favorited  INT DEFAULT 0,
    author_sec_uid          NVARCHAR(100),
    author_verified         BIT DEFAULT 0,
    -- music
    music_id                NVARCHAR(50),
    music_title             NVARCHAR(500),
    music_author            NVARCHAR(200),
    music_duration          INT,
    music_is_original       BIT DEFAULT 0,
    music_user_count        INT DEFAULT 0,
    -- video technical
    video_height            SMALLINT,
    video_width             SMALLINT,
    video_ratio             NVARCHAR(20),
    video_cover_url         NVARCHAR(2048),
    -- tags
    hashtags                NVARCHAR(MAX),
    -- engagement (computed)
    engagement_total AS (digg_count + comment_count + share_count + collect_count) PERSISTED,
    -- metadata
    extracted_at            DATETIME2 NOT NULL,
    updated_at              DATETIME2
);
-- Dropped: lose_count, lose_comment_count (always 0), video_duration (=duration),
--          author_avatar_uri, author_ins_id, music_album, music_is_commerce,
--          video_has_watermark, cha_list, text_extra
CREATE INDEX idx_tk_keyword ON tiktok_videos(search_keyword);
CREATE INDEX idx_tk_plays ON tiktok_videos(play_count DESC);
CREATE INDEX idx_tk_author ON tiktok_videos(author_unique_id);
CREATE INDEX idx_tk_create ON tiktok_videos(create_time);

CREATE TABLE instagram_posts (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    post_pk             NVARCHAR(50) NOT NULL UNIQUE,
    shortcode           NVARCHAR(50),
    search_keyword      NVARCHAR(200),
    geo                 NVARCHAR(10),
    caption             NVARCHAR(MAX),
    media_type          TINYINT,
    url                 NVARCHAR(2048),
    thumbnail_url       NVARCHAR(2048),
    taken_at            DATETIME2,
    location_name       NVARCHAR(200),
    location_lat        DECIMAL(9,6),
    location_lng        DECIMAL(9,6),
    -- author
    username            NVARCHAR(100),
    user_pk             NVARCHAR(50),
    full_name           NVARCHAR(200),
    follower_count      INT DEFAULT 0,
    is_verified         BIT DEFAULT 0,
    -- statistics
    like_count          INT DEFAULT 0,
    comment_count       INT DEFAULT 0,
    share_count         INT DEFAULT 0,
    save_count          INT DEFAULT 0,
    video_view_count    INT DEFAULT 0,
    video_play_count    INT DEFAULT 0,
    -- engagement (computed)
    engagement_total AS (like_count + comment_count + share_count + save_count) PERSISTED,
    -- tags
    hashtags            NVARCHAR(MAX),
    -- metadata
    extracted_at        DATETIME2 NOT NULL,
    updated_at          DATETIME2
);
-- Dropped: profile_pic_url
CREATE INDEX idx_ig_keyword ON instagram_posts(search_keyword);
CREATE INDEX idx_ig_likes ON instagram_posts(like_count DESC);
CREATE INDEX idx_ig_taken ON instagram_posts(taken_at);
CREATE INDEX idx_ig_username ON instagram_posts(username);

CREATE TABLE youtube_videos (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    video_id            NVARCHAR(20) NOT NULL UNIQUE,
    search_keyword      NVARCHAR(200),
    geo                 NVARCHAR(10),
    title               NVARCHAR(500),
    description         NVARCHAR(MAX),
    channel_title       NVARCHAR(200),
    channel_id          NVARCHAR(50),
    published           DATETIME2,
    duration            NVARCHAR(20),
    url                 NVARCHAR(2048),
    thumbnail_url       NVARCHAR(2048),
    category_id         NVARCHAR(10),
    tags                NVARCHAR(MAX),
    language            NVARCHAR(10),
    -- statistics
    view_count          INT DEFAULT 0,
    like_count          INT DEFAULT 0,
    comment_count       INT DEFAULT 0,
    -- engagement (computed)
    engagement_total AS (view_count + like_count + comment_count) PERSISTED,
    -- metadata
    extracted_at        DATETIME2 NOT NULL,
    updated_at          DATETIME2
);
-- Dropped: dislike_count (YouTube API no longer returns it), favorite_count (deprecated)
CREATE INDEX idx_yt_keyword ON youtube_videos(search_keyword);
CREATE INDEX idx_yt_views ON youtube_videos(view_count DESC);
CREATE INDEX idx_yt_channel ON youtube_videos(channel_title);
CREATE INDEX idx_yt_published ON youtube_videos(published);

CREATE TABLE reddit_posts (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    post_id             NVARCHAR(20) NOT NULL UNIQUE,
    search_keyword      NVARCHAR(200),
    geo                 NVARCHAR(10),
    title               NVARCHAR(500),
    selftext            NVARCHAR(MAX),
    url                 NVARCHAR(2048),
    permalink           NVARCHAR(500),
    domain              NVARCHAR(200),
    is_self             BIT DEFAULT 0,
    is_video            BIT DEFAULT 0,
    over_18             BIT DEFAULT 0,
    created_utc         DATETIME2,
    -- subreddit
    subreddit           NVARCHAR(100),
    subreddit_subscribers INT DEFAULT 0,
    -- author
    author              NVARCHAR(100),
    -- statistics
    score               INT DEFAULT 0,
    upvote_ratio        DECIMAL(3,2) DEFAULT 0,
    num_comments        INT DEFAULT 0,
    total_awards        INT DEFAULT 0,
    -- engagement (computed)
    engagement_total AS (score + num_comments + total_awards) PERSISTED,
    -- flair
    link_flair_text     NVARCHAR(200),
    -- metadata
    extracted_at        DATETIME2 NOT NULL,
    updated_at          DATETIME2
);
-- Dropped: post_hint, spoiler, subreddit_id, author_fullname, num_crossposts, thumbnail
CREATE INDEX idx_rd_keyword ON reddit_posts(search_keyword);
CREATE INDEX idx_rd_score ON reddit_posts(score DESC);
CREATE INDEX idx_rd_subreddit ON reddit_posts(subreddit);
CREATE INDEX idx_rd_created ON reddit_posts(created_utc);

CREATE TABLE threads_posts (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    post_code           NVARCHAR(50) NOT NULL UNIQUE,
    post_pk             NVARCHAR(50),
    search_keyword      NVARCHAR(200),
    geo                 NVARCHAR(10),
    caption             NVARCHAR(MAX),
    url                 NVARCHAR(2048),
    taken_at            DATETIME2,
    media_type          NVARCHAR(50),
    -- author
    username            NVARCHAR(100),
    user_pk             NVARCHAR(50),
    full_name           NVARCHAR(200),
    follower_count      INT DEFAULT 0,
    is_verified         BIT DEFAULT 0,
    -- statistics
    like_count          INT DEFAULT 0,
    reply_count         INT DEFAULT 0,
    repost_count        INT DEFAULT 0,
    quote_count         INT DEFAULT 0,
    share_count         INT DEFAULT 0,
    -- engagement (computed)
    engagement_total AS (like_count + reply_count + repost_count + share_count) PERSISTED,
    -- metadata
    extracted_at        DATETIME2 NOT NULL,
    updated_at          DATETIME2
);
-- Dropped: profile_pic_url
CREATE INDEX idx_th_keyword ON threads_posts(search_keyword);
CREATE INDEX idx_th_likes ON threads_posts(like_count DESC);
CREATE INDEX idx_th_taken ON threads_posts(taken_at);
CREATE INDEX idx_th_username ON threads_posts(username);

-- ============================================
-- ADS & ANALYTICS
-- ============================================

CREATE TABLE ads_insight (
    hookd_id                INT PRIMARY KEY,
    external_id             NVARCHAR(100),
    search_keyword          NVARCHAR(200),
    platform                NVARCHAR(50),
    display_format          NVARCHAR(50),
    title                   NVARCHAR(500),
    body                    NVARCHAR(MAX),
    landing_page            NVARCHAR(2048),
    cta_type                NVARCHAR(50),
    cta_text                NVARCHAR(200),
    start_date              DATE,
    end_date                DATE,
    days_active             SMALLINT DEFAULT 0,
    active_in_library       BIT DEFAULT 0,
    performance_score       TINYINT,
    performance_score_title NVARCHAR(50),
    used_count              SMALLINT DEFAULT 0,
    age_audience_min        TINYINT,
    age_audience_max        TINYINT,
    gender_audience         NVARCHAR(20),
    eu_total_reach          INT,
    brand_name              NVARCHAR(200),
    brand_logo_url          NVARCHAR(2048),
    brand_active_ads        SMALLINT DEFAULT 0,
    media                   NVARCHAR(MAX),
    share_url               NVARCHAR(2048),
    extracted_at            DATETIME2,
    updated_at              DATETIME2
);
-- Dropped: link_description, is_aaa_eligible, ad_spend_range_score,
--          ad_spend_range_score_title, brand_external_id, ad_cards

-- ============================================
-- AUTH TABLES
-- ============================================

CREATE TABLE users (
    email       NVARCHAR(255) PRIMARY KEY,
    role        NVARCHAR(20) NOT NULL DEFAULT 'trends',
    created_at  DATETIME2 NOT NULL DEFAULT GETDATE()
);

CREATE TABLE auth_tokens (
    token       NVARCHAR(500) PRIMARY KEY,
    email       NVARCHAR(255) NOT NULL REFERENCES users(email),
    role        NVARCHAR(20) NOT NULL,
    created_at  DATETIME2 NOT NULL DEFAULT GETDATE(),
    expires_at  DATETIME2 NOT NULL
);
CREATE INDEX idx_auth_email ON auth_tokens(email);
CREATE INDEX idx_auth_expires ON auth_tokens(expires_at);

CREATE TABLE otp_codes (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    email       NVARCHAR(255) NOT NULL,
    code        NVARCHAR(10) NOT NULL,
    created_at  DATETIME2 NOT NULL DEFAULT GETDATE(),
    used        BIT NOT NULL DEFAULT 0
);
CREATE INDEX idx_otp_email ON otp_codes(email, created_at DESC);

-- ============================================
-- CONFIG & TRACKING
-- ============================================

CREATE TABLE niches (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    niche_name  NVARCHAR(100) NOT NULL,
    keyword     NVARCHAR(200) NOT NULL,
    created_at  DATETIME2 NOT NULL DEFAULT GETDATE(),
    CONSTRAINT uq_niche_keyword UNIQUE (niche_name, keyword)
);

CREATE TABLE token_usage (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    platform_id     TINYINT NOT NULL REFERENCES platforms(id),
    keyword         NVARCHAR(200),
    units_charged   DECIMAL(10,4) NOT NULL DEFAULT 0,
    geo             NVARCHAR(10),
    created_at      DATETIME2 NOT NULL DEFAULT GETDATE()
);
CREATE INDEX idx_usage_platform ON token_usage(platform_id, created_at);

-- ============================================
-- RAW DATA ARCHIVE (optional)
-- ============================================

CREATE TABLE raw_data_archive (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    source_table    NVARCHAR(50) NOT NULL,
    source_id       INT NOT NULL,
    raw_json        NVARCHAR(MAX),
    created_at      DATETIME2 DEFAULT GETDATE()
);
CREATE INDEX idx_raw_source ON raw_data_archive(source_table, source_id);
```

---

## Migration Script

After running the deduplication in SQLite (Optimization 1), use this Python script:

```python
import sqlite3, json, pyodbc, pandas as pd
from sqlalchemy import create_engine
from urllib.parse import quote_plus
from datetime import datetime

SQLITE_PATH = "src/collector/trends.db"
AZURE_SERVER = "your-server.database.windows.net"
AZURE_DB = "trendsdb"
AZURE_USER = "your_admin"
AZURE_PASS = "your_password"
DRIVER = "ODBC Driver 18 for SQL Server"

sqlite_conn = sqlite3.connect(SQLITE_PATH)
conn_str = (
    f"DRIVER={{{DRIVER}}};SERVER={AZURE_SERVER},1433;"
    f"DATABASE={AZURE_DB};UID={AZURE_USER};PWD={AZURE_PASS};"
    f"Encrypt=yes;TrustServerCertificate=no;"
)
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}")

# 1. Seed platforms lookup
PLATFORMS = {
    'Google Regions': 1, 'Google Interest': 2, 'YouTube': 3, 'HackerNews': 4,
    'TikTok': 5, 'Instagram': 6, 'GetHookdAI': 7, 'Google Related Queries': 8,
    'Reddit': 9, 'Google Trends': 10, 'Threads': 11, 'News': 12,
    'X (Twitter)': 13, 'Facebook': 14
}

# 2. Migrate trends (deduplicated)
print("Migrating trends...")
df = pd.read_sql_query("""
    SELECT MIN(id) AS id, platform, topic, growth, keyword, geo, extracted_at, extra_data
    FROM trends
    GROUP BY platform, topic, keyword, geo, growth, extracted_at
""", sqlite_conn)
df['platform_id'] = df['platform'].map(PLATFORMS)
df = df.drop(columns=['id', 'platform'])
df.to_sql('trends', engine, if_exists='append', index=False, chunksize=1000, method='multi')
print(f"  ✓ {len(df)} rows")

# 3. Migrate platform tables (extract raw_data to archive)
for table in ['tiktok_videos', 'instagram_posts', 'youtube_videos', 'reddit_posts', 'threads_posts']:
    print(f"Migrating {table}...")
    df = pd.read_sql_query(f"SELECT * FROM [{table}]", sqlite_conn)

    # Archive raw_data
    if 'raw_data' in df.columns:
        archive = df[['id', 'raw_data']].copy()
        archive['source_table'] = table
        archive = archive.rename(columns={'id': 'source_id', 'raw_data': 'raw_json'})
        archive.to_sql('raw_data_archive', engine, if_exists='append', index=False, chunksize=500)
        df = df.drop(columns=['raw_data'])

    if 'id' in df.columns:
        df = df.drop(columns=['id'])

    # Drop optimized-out columns per table
    drop_cols = {
        'tiktok_videos': ['video_duration', 'lose_count', 'lose_comment_count',
                          'author_avatar_uri', 'author_ins_id', 'music_album',
                          'music_is_commerce', 'video_has_watermark', 'cha_list',
                          'text_extra', 'engagement_total'],
        'instagram_posts': ['profile_pic_url', 'engagement_total'],
        'youtube_videos': ['dislike_count', 'favorite_count', 'engagement_total'],
        'reddit_posts': ['post_hint', 'spoiler', 'subreddit_id', 'author_fullname',
                         'num_crossposts', 'thumbnail', 'engagement_total'],
        'threads_posts': ['profile_pic_url', 'engagement_total'],
    }
    for col in drop_cols.get(table, []):
        if col in df.columns:
            df = df.drop(columns=[col])

    df.to_sql(table, engine, if_exists='append', index=False, chunksize=500, method='multi')
    print(f"  ✓ {len(df)} rows")

# 4. Migrate remaining tables
for table in ['scrape_log', 'scrape_errors', 'token_usage']:
    print(f"Migrating {table}...")
    df = pd.read_sql_query(f"SELECT * FROM [{table}]", sqlite_conn)
    if 'id' in df.columns:
        df = df.drop(columns=['id'])
    if 'platform' in df.columns:
        df['platform_id'] = df['platform'].map(PLATFORMS)
        df = df.drop(columns=['platform'])
    df.to_sql(table, engine, if_exists='append', index=False, chunksize=1000, method='multi')
    print(f"  ✓ {len(df)} rows")

for table in ['ads_insight', 'users', 'auth_tokens', 'otp_codes', 'niches']:
    print(f"Migrating {table}...")
    df = pd.read_sql_query(f"SELECT * FROM [{table}]", sqlite_conn)
    if table == 'ads_insight':
        drop = ['link_description', 'is_aaa_eligible', 'ad_spend_range_score',
                'ad_spend_range_score_title', 'brand_external_id', 'ad_cards', 'raw_data']
        for col in drop:
            if col in df.columns:
                df = df.drop(columns=[col])
    if 'id' in df.columns and table not in ['ads_insight']:
        df = df.drop(columns=['id'])
    df.to_sql(table, engine, if_exists='append', index=False, chunksize=1000, method='multi')
    print(f"  ✓ {len(df)} rows")

sqlite_conn.close()
print("\n✅ Migration complete!")
```

---

## Execution Order

1. **Run deduplication** on SQLite (Optimization 1 SQL above)
2. **Preserve URLs** in `extra_data` (Optimization 2 Python script)
3. **Create Azure SQL database** and run the optimized schema above
4. **Run the migration script**
5. **Verify row counts** in Azure SQL
6. **Update application code** to use `pyodbc`/`sqlalchemy` with `platform_id` lookups
7. **Test thoroughly** before decommissioning SQLite

---

## Application Code Changes Required

### Install dependencies

```powershell
pip install pyodbc sqlalchemy
```

### New `.env` variables

```env
AZURE_SQL_SERVER=your-server.database.windows.net
AZURE_SQL_DB=trendsdb
AZURE_SQL_USER=your_admin
AZURE_SQL_PASS=your_password
AZURE_SQL_DRIVER=ODBC Driver 18 for SQL Server
```

### New shared DB connection helper (`src/db/connection.py`)

```python
import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine

def get_engine():
    server = os.getenv("AZURE_SQL_SERVER")
    db = os.getenv("AZURE_SQL_DB")
    user = os.getenv("AZURE_SQL_USER")
    pwd = os.getenv("AZURE_SQL_PASS")
    driver = os.getenv("AZURE_SQL_DRIVER", "ODBC Driver 18 for SQL Server")

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server},1433;"
        f"DATABASE={db};"
        f"UID={user};PWD={pwd};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )
    return create_engine(
        f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}"
    )
```

### Replace all `sqlite3.connect(...)` calls

```python
# BEFORE (SQLite)
import sqlite3
conn = sqlite3.connect("src/collector/trends.db")
cursor = conn.execute("SELECT * FROM trends")

# AFTER (Azure SQL via SQLAlchemy)
from src.db.connection import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.connect() as conn:
    result = conn.execute(text("SELECT * FROM trends"))
```

### SQL Syntax Changes

| SQLite | Azure SQL Server |
|--------|-----------------|
| `AUTOINCREMENT` | `IDENTITY(1,1)` |
| `TEXT` | `NVARCHAR(MAX)` or `NVARCHAR(n)` |
| `REAL` | `FLOAT` or `DECIMAL` |
| `DATETIME` | `DATETIME2` |
| `LIMIT 10` | `TOP 10` or `OFFSET...FETCH` |
| `\|\|` (string concat) | `+` or `CONCAT()` |
| `strftime(...)` | `FORMAT(...)` or `CONVERT(...)` |
| `INSERT OR IGNORE` | Use `IF NOT EXISTS` or `MERGE` |
| `INSERT OR REPLACE` | Use `MERGE` |

### Docker changes

Add ODBC driver to Dockerfiles:

```dockerfile
RUN apt-get update && \
    curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev
```

Add env vars to `docker-compose.yml`:

```yaml
environment:
  - AZURE_SQL_SERVER=your-server.database.windows.net
  - AZURE_SQL_DB=trendsdb
  - AZURE_SQL_USER=${AZURE_SQL_USER}
  - AZURE_SQL_PASS=${AZURE_SQL_PASS}
```

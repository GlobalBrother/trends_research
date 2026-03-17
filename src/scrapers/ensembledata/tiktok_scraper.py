"""TikTok scraper using ensembledata API.

Saves comprehensive video data into a dedicated ``tiktok_videos`` table
as well as the shared ``trends`` table for cross-platform dashboards.
"""

import json
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from ensembledata.api import EDClient
from ensembledata.api.errors import EDError
from sqlalchemy import text

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(__file__))
from db_helper import save_trend, save_error, save_token_usage

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from src.db.connection import get_engine, is_sqlite
from src.db.sql_compat import tbl

_engine = get_engine()

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

PLATFORM = "TikTok"

# ---------------------------------------------------------------------------
# TikTok-specific table
# ---------------------------------------------------------------------------

_CREATE_TIKTOK_VIDEOS = """
CREATE TABLE IF NOT EXISTS tiktok_videos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- identifiers
    aweme_id            TEXT UNIQUE,
    search_keyword      TEXT,
    geo                 TEXT,

    -- content
    description         TEXT,
    desc_language       TEXT,
    share_url           TEXT,
    region              TEXT,
    create_time         INTEGER,
    aweme_type          INTEGER,
    duration            INTEGER,
    is_ads              INTEGER DEFAULT 0,
    is_top              INTEGER DEFAULT 0,
    content_type        TEXT,

    -- statistics
    digg_count          INTEGER DEFAULT 0,
    comment_count       INTEGER DEFAULT 0,
    share_count         INTEGER DEFAULT 0,
    play_count          INTEGER DEFAULT 0,
    download_count      INTEGER DEFAULT 0,
    forward_count       INTEGER DEFAULT 0,
    collect_count       INTEGER DEFAULT 0,
    -- author
    author_uid          TEXT,
    author_unique_id    TEXT,
    author_nickname     TEXT,
    author_signature    TEXT,
    author_region       TEXT,
    author_follower_count   INTEGER DEFAULT 0,
    author_following_count  INTEGER DEFAULT 0,
    author_total_favorited  INTEGER DEFAULT 0,
    author_avatar_uri   TEXT,
    author_sec_uid      TEXT,
    author_verified     INTEGER DEFAULT 0,
    author_ins_id       TEXT,

    -- music / sound
    music_id            TEXT,
    music_title         TEXT,
    music_author        TEXT,
    music_album         TEXT,
    music_duration      INTEGER,
    music_is_original   INTEGER DEFAULT 0,
    music_is_commerce   INTEGER DEFAULT 0,
    music_user_count    INTEGER DEFAULT 0,

    -- video technical
    video_height        INTEGER,
    video_width         INTEGER,
    video_ratio         TEXT,
    video_cover_url     TEXT,

    -- hashtags & challenges (JSON arrays)
    hashtags            TEXT,

    -- engagement helpers (computed)
    engagement_total    INTEGER DEFAULT 0,

    -- metadata
    extracted_at        TEXT,
    updated_at          TEXT
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_tiktok_keyword ON tiktok_videos (search_keyword);",
    "CREATE INDEX IF NOT EXISTS idx_tiktok_author  ON tiktok_videos (author_unique_id);",
    "CREATE INDEX IF NOT EXISTS idx_tiktok_create  ON tiktok_videos (create_time);",
    "CREATE INDEX IF NOT EXISTS idx_tiktok_plays   ON tiktok_videos (play_count DESC);",
]


def _ensure_table():
    """Tables are pre-created in Azure SQL via migration schema."""
    pass


def _save_tiktok_video(v: dict, keyword: str, geo: str):
    """Insert or update a single video row in tiktok_videos."""
    stats = v.get("statistics", {})
    author = v.get("author", {}) or {}
    music = v.get("music", {}) or {}
    video = v.get("video", {}) or {}

    aweme_id = str(v.get("aweme_id") or v.get("id") or "")
    if not aweme_id:
        return

    # hashtags
    hashtags = []
    if isinstance(v.get("text_extra"), list):
        hashtags = [t.get("hashtag_name", "") for t in v["text_extra"] if t.get("hashtag_name")]
    if not hashtags and isinstance(v.get("cha_list"), list):
        hashtags = [c.get("cha_name", "") for c in v["cha_list"] if c.get("cha_name")]

    # cover url
    cover_url = ""
    cover = video.get("cover") or video.get("origin_cover") or {}
    if isinstance(cover, dict):
        urls = cover.get("url_list", [])
        cover_url = urls[0] if urls else ""

    digg = stats.get("digg_count", 0) or 0
    comments = stats.get("comment_count", 0) or 0
    shares = stats.get("share_count", 0) or 0
    plays = stats.get("play_count", 0) or 0
    downloads = stats.get("download_count", 0) or 0
    forwards = stats.get("forward_count", 0) or 0
    collect = v.get("collect_stat", 0) or 0
    engagement = digg + comments + shares

    now = datetime.now().isoformat()

    params = {
        "aweme_id": aweme_id, "keyword": keyword, "geo": geo,
        "description": v.get("desc", ""), "desc_language": v.get("desc_language", ""),
        "share_url": v.get("share_url") or (v.get("share_info", {}) or {}).get("share_url", ""),
        "region": v.get("region", ""), "create_time": v.get("create_time", 0),
        "aweme_type": v.get("aweme_type", 0), "duration": v.get("duration", 0),
        "is_ads": 1 if v.get("is_ads") else 0,
        "is_top": v.get("is_top", 0),
        "content_type": v.get("content_type", ""),
        "digg_count": digg, "comment_count": comments, "share_count": shares,
        "play_count": plays, "download_count": downloads, "forward_count": forwards,
        "collect_count": collect,
        "author_uid": str(author.get("uid", "")), "author_unique_id": author.get("unique_id", ""),
        "author_nickname": author.get("nickname", ""), "author_signature": author.get("signature", ""),
        "author_region": author.get("region", ""),
        "author_follower_count": author.get("follower_count", 0) or 0,
        "author_following_count": author.get("following_count", 0) or 0,
        "author_total_favorited": author.get("total_favorited", 0) or 0,
        "author_sec_uid": author.get("sec_uid", ""),
        "author_verified": author.get("verification_type", 0) or 0,
        "music_id": str(music.get("id", "")), "music_title": music.get("title", ""),
        "music_author": music.get("author", ""),
        "music_duration": music.get("duration", 0) or 0,
        "music_is_original": 1 if music.get("is_original") else 0,
        "music_user_count": music.get("user_count", 0) or 0,
        "video_height": video.get("height", 0) or 0,
        "video_width": video.get("width", 0) or 0,
        "video_ratio": video.get("ratio", ""),
        "video_cover_url": cover_url,
        "hashtags": json.dumps(hashtags),
        "engagement_total": engagement,
        "extracted_at": now, "updated_at": now,
    }

    with _engine.connect() as conn:
        try:
            if is_sqlite():
                existing = conn.execute(text(f"SELECT 1 FROM {tbl('tiktok_videos')} WHERE aweme_id = :aweme_id"), {"aweme_id": aweme_id}).fetchone()
                if existing:
                    conn.execute(text(
                        f"UPDATE {tbl('tiktok_videos')} SET "
                        "digg_count = :digg_count, comment_count = :comment_count, "
                        "share_count = :share_count, play_count = :play_count, "
                        "download_count = :download_count, forward_count = :forward_count, "
                        "collect_count = :collect_count, "
                        "author_follower_count = :author_follower_count, "
                        "author_following_count = :author_following_count, "
                        "author_total_favorited = :author_total_favorited, "
                        "engagement_total = :engagement_total, "
                        "updated_at = :updated_at WHERE aweme_id = :aweme_id"
                    ), params)
                else:
                    conn.execute(text(
                        f"INSERT INTO {tbl('tiktok_videos')} ("
                        "aweme_id, search_keyword, geo, "
                        "description, desc_language, share_url, region, create_time, "
                        "aweme_type, duration, is_ads, is_top, content_type, "
                        "digg_count, comment_count, share_count, play_count, "
                        "download_count, forward_count, collect_count, "
                        "author_uid, author_unique_id, author_nickname, author_signature, "
                        "author_region, author_follower_count, author_following_count, "
                        "author_total_favorited, author_sec_uid, author_verified, "
                        "music_id, music_title, music_author, "
                        "music_duration, music_is_original, music_user_count, "
                        "video_height, video_width, video_ratio, video_cover_url, "
                        "hashtags, engagement_total, extracted_at, updated_at"
                        ") VALUES ("
                        ":aweme_id, :keyword, :geo, "
                        ":description, :desc_language, :share_url, :region, :create_time, "
                        ":aweme_type, :duration, :is_ads, :is_top, :content_type, "
                        ":digg_count, :comment_count, :share_count, :play_count, "
                        ":download_count, :forward_count, :collect_count, "
                        ":author_uid, :author_unique_id, :author_nickname, :author_signature, "
                        ":author_region, :author_follower_count, :author_following_count, "
                        ":author_total_favorited, :author_sec_uid, :author_verified, "
                        ":music_id, :music_title, :music_author, "
                        ":music_duration, :music_is_original, :music_user_count, "
                        ":video_height, :video_width, :video_ratio, :video_cover_url, "
                        ":hashtags, :engagement_total, :extracted_at, :updated_at)"
                    ), params)
            else:
                conn.execute(text(f"""
                    MERGE {tbl('tiktok_videos')} AS target
                    USING (SELECT :aweme_id AS aweme_id) AS source
                    ON target.aweme_id = source.aweme_id
                    WHEN MATCHED THEN UPDATE SET
                        digg_count = :digg_count, comment_count = :comment_count,
                        share_count = :share_count, play_count = :play_count,
                        download_count = :download_count, forward_count = :forward_count,
                        collect_count = :collect_count,
                        author_follower_count = :author_follower_count,
                        author_following_count = :author_following_count,
                        author_total_favorited = :author_total_favorited,
                        engagement_total = :engagement_total,
                        updated_at = :updated_at
                    WHEN NOT MATCHED THEN INSERT (
                        aweme_id, search_keyword, geo,
                        description, desc_language, share_url, region, create_time,
                        aweme_type, duration, is_ads, is_top, content_type,
                        digg_count, comment_count, share_count, play_count,
                        download_count, forward_count, collect_count,
                        author_uid, author_unique_id, author_nickname, author_signature,
                        author_region, author_follower_count, author_following_count,
                        author_total_favorited, author_sec_uid, author_verified,
                        music_id, music_title, music_author,
                        music_duration, music_is_original, music_user_count,
                        video_height, video_width, video_ratio, video_cover_url,
                        hashtags, engagement_total, extracted_at, updated_at
                    ) VALUES (
                        :aweme_id, :keyword, :geo,
                        :description, :desc_language, :share_url, :region, :create_time,
                        :aweme_type, :duration, :is_ads, :is_top, :content_type,
                        :digg_count, :comment_count, :share_count, :play_count,
                        :download_count, :forward_count, :collect_count,
                        :author_uid, :author_unique_id, :author_nickname, :author_signature,
                        :author_region, :author_follower_count, :author_following_count,
                        :author_total_favorited, :author_sec_uid, :author_verified,
                        :music_id, :music_title, :music_author,
                        :music_duration, :music_is_original, :music_user_count,
                        :video_height, :video_width, :video_ratio, :video_cover_url,
                        :hashtags, :engagement_total, :extracted_at, :updated_at
                    );
                """), params)
            conn.commit()
            logger.debug("Saved tiktok_video aweme_id=%s", aweme_id)
        except Exception:
            logger.error("Failed to save tiktok_video aweme_id=%s", aweme_id, exc_info=True)
            raise


# ---------------------------------------------------------------------------
# Public scrape entry-point
# ---------------------------------------------------------------------------

def scrape_tiktok(keywords, geo="Global", period="30"):
    """
    Fetch TikTok videos for each keyword via ensembledata.

    Parameters
    ----------
    keywords : list[str]
    geo : str
    period : str  – '0' (all), '1', '7', '30', '90', '180' days
    """
    token = os.getenv("ENSEMBLEDATA_TOKEN", "")
    if not token:
        logger.warning("ENSEMBLEDATA_TOKEN not set – skipping TikTok scrape.")
        return

    _ensure_table()
    client = EDClient(token=token)

    for kw in keywords:
        try:
            result = client.tiktok.keyword_search(keyword=kw, period=period)
            raw = result.data or []
            # ensembledata may return nested structure: {data: [{aweme_info: ...}, ...]}
            if isinstance(raw, dict):
                inner = raw.get("data", raw.get("videos", []))
                if isinstance(inner, list):
                    raw = inner
                else:
                    raw = []
            if not isinstance(raw, list):
                raw = []

            count = 0
            for item in raw[:50]:
                # unwrap aweme_info envelope if present
                v = item.get("aweme_info", item) if isinstance(item, dict) else item
                if not isinstance(v, dict):
                    continue

                # --- save to comprehensive tiktok_videos table ---
                try:
                    _save_tiktok_video(v, keyword=kw, geo=geo)
                except Exception:
                    logger.error("Failed saving tiktok_video detail for kw=%s", kw, exc_info=True)

                # --- save to shared trends table for dashboard ---
                stats = v.get("statistics", {})
                likes = stats.get("digg_count") or v.get("like_count") or v.get("diggCount") or 0
                comments = stats.get("comment_count") or v.get("comment_count") or v.get("commentCount") or 0
                shares = stats.get("share_count") or v.get("share_count") or v.get("shareCount") or 0
                views = stats.get("play_count") or v.get("view_count") or v.get("playCount") or 0
                engagement = likes + comments + shares

                desc = v.get("desc") or v.get("video_description") or ""
                hashtags = v.get("hashtag_names") or []
                if not hashtags and isinstance(v.get("text_extra"), list):
                    hashtags = [t.get("hashtag_name", "") for t in v["text_extra"] if t.get("hashtag_name")]
                if not hashtags and isinstance(v.get("textExtra"), list):
                    hashtags = [t.get("hashtagName", "") for t in v["textExtra"] if t.get("hashtagName")]
                if not hashtags and isinstance(v.get("cha_list"), list):
                    hashtags = [c.get("cha_name", "") for c in v["cha_list"] if c.get("cha_name")]
                topic = desc[:120] if desc else ", ".join(hashtags[:5]) if hashtags else f"Video {v.get('aweme_id', v.get('id', ''))}"

                username = v.get("username") or ""
                if not username and isinstance(v.get("author"), dict):
                    username = v["author"].get("unique_id") or v["author"].get("uniqueId", "")
                video_id = str(v.get("aweme_id") or v.get("id") or v.get("video_id") or "")
                url = f"https://www.tiktok.com/@{username}/video/{video_id}" if username and video_id else ""

                save_trend(
                    platform=PLATFORM,
                    topic=topic,
                    growth=engagement,
                    keyword=kw,
                    geo=geo,
                    url=url,
                    extra_data={
                        "views": views, "likes": likes, "comments": comments,
                        "shares": shares, "username": username, "hashtags": hashtags,
                        "video_id": video_id,
                    },
                )
                count += 1

            logger.info("Saved %d videos for '%s' (units charged: %s)", count, kw, result.units_charged)
            if result.units_charged:
                save_token_usage(PLATFORM, kw, result.units_charged, geo)

        except EDError as e:
            save_error(PLATFORM, kw, None, 0, str(e))
            if e.status_code == 495:
                logger.warning("Daily API limit reached. Stopping TikTok scraper.")
                break
            logger.error("Error for '%s': %s", kw, e, exc_info=True)
        except Exception as e:
            save_error(PLATFORM, kw, None, 0, str(e))
            logger.error("Error for '%s': %s", kw, e, exc_info=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords")
    parser.add_argument("--geo", default="Global")
    parser.add_argument("--period", default="30")
    args = parser.parse_args()
    scrape_tiktok([k.strip() for k in args.keywords.split(",")], geo=args.geo, period=args.period)

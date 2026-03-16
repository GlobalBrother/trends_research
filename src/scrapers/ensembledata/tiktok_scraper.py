"""TikTok scraper using ensembledata API.

Saves comprehensive video data into a dedicated ``tiktok_videos`` table
as well as the shared ``trends`` table for cross-platform dashboards.
"""

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime

from dotenv import load_dotenv
from ensembledata.api import EDClient
from ensembledata.api.errors import EDError

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(__file__))
from db_helper import save_trend, save_error, save_token_usage, DB_PATH

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
    lose_count          INTEGER DEFAULT 0,
    lose_comment_count  INTEGER DEFAULT 0,

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
    video_duration      INTEGER,
    video_has_watermark INTEGER DEFAULT 0,
    video_cover_url     TEXT,

    -- hashtags & challenges (JSON arrays)
    hashtags            TEXT,
    cha_list            TEXT,

    -- text_extra (full JSON for stickers, mentions, hashtags)
    text_extra          TEXT,

    -- engagement helpers (computed)
    engagement_total    INTEGER DEFAULT 0,

    -- raw JSON blob for any fields not explicitly stored
    raw_data            TEXT,

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
    """Create the tiktok_videos table and indexes if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_CREATE_TIKTOK_VIDEOS)
        for idx in _CREATE_INDEXES:
            conn.execute(idx)
        conn.commit()
        logger.debug("tiktok_videos table ensured.")
    finally:
        conn.close()


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

    # cha_list summary
    cha_list_data = []
    if isinstance(v.get("cha_list"), list):
        for c in v["cha_list"]:
            cha_list_data.append({
                "cha_id": c.get("cid") or c.get("cha_id"),
                "cha_name": c.get("cha_name", ""),
                "desc": c.get("desc", ""),
                "user_count": c.get("user_count", 0),
                "view_count": c.get("view_count") or c.get("views", 0),
            })

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
    lose = stats.get("lose_count", 0) or 0
    lose_comment = stats.get("lose_comment_count", 0) or 0
    engagement = digg + comments + shares

    now = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            INSERT INTO tiktok_videos (
                aweme_id, search_keyword, geo,
                description, desc_language, share_url, region, create_time,
                aweme_type, duration, is_ads, is_top, content_type,
                digg_count, comment_count, share_count, play_count,
                download_count, forward_count, collect_count,
                lose_count, lose_comment_count,
                author_uid, author_unique_id, author_nickname, author_signature,
                author_region, author_follower_count, author_following_count,
                author_total_favorited, author_avatar_uri, author_sec_uid,
                author_verified, author_ins_id,
                music_id, music_title, music_author, music_album,
                music_duration, music_is_original, music_is_commerce, music_user_count,
                video_height, video_width, video_ratio, video_duration,
                video_has_watermark, video_cover_url,
                hashtags, cha_list, text_extra,
                engagement_total, raw_data,
                extracted_at, updated_at
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,
                ?,?,?,?,?,?,?,?,?,
                ?,?,?,?,?,?,?,?,?,?,?,?,
                ?,?,?,?,?,?,?,?,
                ?,?,?,?,?,?,
                ?,?,?,
                ?,?,
                ?,?
            )
            ON CONFLICT(aweme_id) DO UPDATE SET
                digg_count=excluded.digg_count,
                comment_count=excluded.comment_count,
                share_count=excluded.share_count,
                play_count=excluded.play_count,
                download_count=excluded.download_count,
                forward_count=excluded.forward_count,
                collect_count=excluded.collect_count,
                lose_count=excluded.lose_count,
                lose_comment_count=excluded.lose_comment_count,
                author_follower_count=excluded.author_follower_count,
                author_following_count=excluded.author_following_count,
                author_total_favorited=excluded.author_total_favorited,
                engagement_total=excluded.engagement_total,
                raw_data=excluded.raw_data,
                updated_at=excluded.updated_at
        """, (
            aweme_id, keyword, geo,
            v.get("desc", ""), v.get("desc_language", ""),
            v.get("share_url") or (v.get("share_info", {}) or {}).get("share_url", ""),
            v.get("region", ""), v.get("create_time", 0),
            v.get("aweme_type", 0), v.get("duration", 0),
            1 if v.get("is_ads") else 0,
            v.get("is_top", 0),
            v.get("content_type", ""),
            digg, comments, shares, plays, downloads, forwards, collect,
            lose, lose_comment,
            str(author.get("uid", "")), author.get("unique_id", ""),
            author.get("nickname", ""), author.get("signature", ""),
            author.get("region", ""),
            author.get("follower_count", 0) or 0,
            author.get("following_count", 0) or 0,
            author.get("total_favorited", 0) or 0,
            author.get("avatar_uri", ""), author.get("sec_uid", ""),
            author.get("verification_type", 0) or 0,
            author.get("ins_id", ""),
            str(music.get("id", "")), music.get("title", ""),
            music.get("author", ""), music.get("album", ""),
            music.get("duration", 0) or 0,
            1 if music.get("is_original") else 0,
            1 if music.get("is_commerce_music") else 0,
            music.get("user_count", 0) or 0,
            video.get("height", 0) or 0, video.get("width", 0) or 0,
            video.get("ratio", ""), video.get("duration", 0) or 0,
            1 if video.get("has_watermark") else 0,
            cover_url,
            json.dumps(hashtags), json.dumps(cha_list_data),
            json.dumps(v.get("text_extra", []), default=str),
            engagement, json.dumps(v, default=str),
            now, now,
        ))
        conn.commit()
        logger.debug("Saved tiktok_video aweme_id=%s", aweme_id)
    except Exception:
        logger.error("Failed to save tiktok_video aweme_id=%s", aweme_id, exc_info=True)
        raise
    finally:
        conn.close()


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

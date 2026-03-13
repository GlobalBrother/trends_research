"""YouTube scraper using ensembledata API.

Saves comprehensive video data into a dedicated ``youtube_videos`` table
as well as the shared ``trends`` table for cross-platform dashboards.
"""

import json
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime

from dotenv import load_dotenv
from ensembledata.api import EDClient

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(__file__))
from db_helper import save_trend, save_error, DB_PATH

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

PLATFORM = "YouTube"

# ---------------------------------------------------------------------------
# YouTube-specific table
# ---------------------------------------------------------------------------

_CREATE_YOUTUBE_VIDEOS = """
CREATE TABLE IF NOT EXISTS youtube_videos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- identifiers
    video_id            TEXT UNIQUE,
    search_keyword      TEXT,
    geo                 TEXT,

    -- content
    title               TEXT,
    description         TEXT,
    channel_title       TEXT,
    channel_id          TEXT,
    published           TEXT,
    duration            TEXT,
    url                 TEXT,
    thumbnail_url       TEXT,
    category_id         TEXT,
    tags                TEXT,
    language            TEXT,

    -- statistics
    view_count          INTEGER DEFAULT 0,
    like_count          INTEGER DEFAULT 0,
    dislike_count       INTEGER DEFAULT 0,
    comment_count       INTEGER DEFAULT 0,
    favorite_count      INTEGER DEFAULT 0,

    -- engagement helpers (computed)
    engagement_total    INTEGER DEFAULT 0,

    -- raw JSON blob
    raw_data            TEXT,

    -- metadata
    extracted_at        TEXT,
    updated_at          TEXT
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_yt_keyword ON youtube_videos (search_keyword);",
    "CREATE INDEX IF NOT EXISTS idx_yt_channel ON youtube_videos (channel_title);",
    "CREATE INDEX IF NOT EXISTS idx_yt_published ON youtube_videos (published);",
    "CREATE INDEX IF NOT EXISTS idx_yt_views ON youtube_videos (view_count DESC);",
]


def _ensure_table():
    """Create the youtube_videos table and indexes if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_CREATE_YOUTUBE_VIDEOS)
        for idx in _CREATE_INDEXES:
            conn.execute(idx)
        conn.commit()
        logger.debug("youtube_videos table ensured.")
    finally:
        conn.close()


def _parse_int(val):
    """Safely parse an integer from a string that may contain commas or words."""
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        digits = re.sub(r"[^\d]", "", val)
        return int(digits) if digits else 0
    return 0


def _normalize_video(raw: dict) -> dict:
    """Flatten a videoRenderer envelope into a simple dict.

    The ensembledata YouTube API returns items wrapped as::

        {"videoRenderer": {"videoId": ..., "title": {"runs": [{"text": ...}]}, ...}}

    This helper unwraps the envelope and extracts nested text fields so that
    downstream code can use simple ``dict.get()`` calls.
    """
    vr = raw.get("videoRenderer") if isinstance(raw, dict) else None
    if not vr:
        # Already flat or unknown shape – return as-is
        return raw

    v = dict(vr)  # shallow copy

    # title.runs[0].text -> title
    title_obj = v.get("title")
    if isinstance(title_obj, dict):
        runs = title_obj.get("runs", [])
        v["title"] = runs[0].get("text", "") if runs else ""

    # ownerText / longBylineText / shortBylineText -> channelTitle
    for key in ("ownerText", "longBylineText", "shortBylineText"):
        obj = v.get(key)
        if isinstance(obj, dict):
            runs = obj.get("runs", [])
            if runs:
                v["channelTitle"] = runs[0].get("text", "")
                # channel id from browseEndpoint
                nav = runs[0].get("navigationEndpoint", {})
                browse = nav.get("browseEndpoint", {})
                if browse.get("browseId"):
                    v["channelId"] = browse["browseId"]
                break

    # viewCountText.simpleText -> viewCount  ("133,744 views")
    vct = v.get("viewCountText")
    if isinstance(vct, dict):
        v["viewCount"] = vct.get("simpleText", "0")

    # publishedTimeText.simpleText -> publishedTimeText
    ptt = v.get("publishedTimeText")
    if isinstance(ptt, dict):
        v["publishedTimeText"] = ptt.get("simpleText", "")

    # lengthText.simpleText -> lengthText
    lt = v.get("lengthText")
    if isinstance(lt, dict):
        v["lengthText"] = lt.get("simpleText", "")

    # detailedMetadataSnippets[0].snippetText.runs[0].text -> description
    snippets = v.get("detailedMetadataSnippets", [])
    if snippets and isinstance(snippets, list):
        snippet_text = snippets[0].get("snippetText", {})
        runs = snippet_text.get("runs", []) if isinstance(snippet_text, dict) else []
        if runs:
            v["description"] = "".join(r.get("text", "") for r in runs)

    return v


def _save_youtube_video(v: dict, keyword: str, geo: str):
    """Insert or update a single video row in youtube_videos."""
    video_id = v.get("videoId") or v.get("video_id") or ""
    if not video_id:
        return

    title = v.get("title", "") if isinstance(v.get("title"), str) else ""
    description = v.get("description") or v.get("descriptionSnippet") or ""
    channel = v.get("channelTitle") or v.get("channel") or ""
    channel_id = v.get("channelId") or v.get("channel_id") or ""
    published = v.get("publishedTimeText") if isinstance(v.get("publishedTimeText"), str) else ""
    if not published:
        published = v.get("published") or v.get("publishDate") or ""
    duration = v.get("lengthText") if isinstance(v.get("lengthText"), str) else ""
    if not duration:
        duration = v.get("duration") or ""
    url = f"https://www.youtube.com/watch?v={video_id}" if video_id else v.get("url", "")
    thumbnail = ""
    thumbs = v.get("thumbnail", {})
    if isinstance(thumbs, dict):
        thumb_list = thumbs.get("thumbnails", [])
        if thumb_list:
            thumbnail = thumb_list[-1].get("url", "")
    elif isinstance(thumbs, str):
        thumbnail = thumbs
    if not thumbnail:
        thumbnail = v.get("thumbnailUrl") or v.get("thumbnail_url") or ""

    category_id = v.get("categoryId") or v.get("category_id") or ""
    tags = v.get("tags") or v.get("keywords") or []
    if isinstance(tags, list):
        tags = json.dumps(tags)
    language = v.get("defaultLanguage") or v.get("language") or ""

    views = _parse_int(v.get("viewCount") or v.get("view_count") or v.get("views") or 0)
    likes = _parse_int(v.get("likeCount") or v.get("like_count") or v.get("likes") or 0)
    dislikes = _parse_int(v.get("dislikeCount") or v.get("dislike_count") or 0)
    comments = _parse_int(v.get("commentCount") or v.get("comment_count") or 0)
    favorites = _parse_int(v.get("favoriteCount") or v.get("favorite_count") or 0)

    engagement = int(likes) + int(comments) + int(dislikes)
    now = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            INSERT INTO youtube_videos (
                video_id, search_keyword, geo,
                title, description, channel_title, channel_id,
                published, duration, url, thumbnail_url,
                category_id, tags, language,
                view_count, like_count, dislike_count, comment_count, favorite_count,
                engagement_total, raw_data,
                extracted_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(video_id) DO UPDATE SET
                view_count=excluded.view_count,
                like_count=excluded.like_count,
                dislike_count=excluded.dislike_count,
                comment_count=excluded.comment_count,
                favorite_count=excluded.favorite_count,
                engagement_total=excluded.engagement_total,
                raw_data=excluded.raw_data,
                updated_at=excluded.updated_at
        """, (
            video_id, keyword, geo,
            title, description, channel, channel_id,
            published, duration, url, thumbnail,
            category_id, tags, language,
            int(views), int(likes), int(dislikes), int(comments), int(favorites),
            engagement, json.dumps(v, default=str),
            now, now,
        ))
        conn.commit()
        logger.debug("Saved youtube_video video_id=%s", video_id)
    except Exception:
        logger.error("Failed to save youtube_video video_id=%s", video_id, exc_info=True)
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public scrape entry-point
# ---------------------------------------------------------------------------

def scrape_youtube(keywords, geo="Global", depth=1, period="month", sorting="views"):
    """
    Fetch YouTube videos for each keyword via ensembledata.

    Parameters
    ----------
    keywords : list[str]
    geo : str
    depth : int  – pagination depth (1 = first page)
    period : str – 'overall', 'hour', 'today', 'week', 'month', 'year'
    sorting : str – 'relevance', 'time', 'views', 'rating'
    """
    token = os.getenv("ENSEMBLEDATA_TOKEN", "")
    if not token:
        logger.warning("ENSEMBLEDATA_TOKEN not set – skipping YouTube scrape.")
        return

    _ensure_table()
    client = EDClient(token=token)

    for kw in keywords:
        try:
            result = client.youtube.keyword_search(
                keyword=kw, depth=depth, period=period, sorting=sorting,
            )
            raw_data = result.data or []

            # Unwrap ensembledata envelope: data.posts[]
            if isinstance(raw_data, dict):
                items = (
                    raw_data.get("posts")
                    or raw_data.get("videos")
                    or raw_data.get("items")
                    or []
                )
            elif isinstance(raw_data, list):
                items = raw_data
            else:
                items = []

            # Normalize videoRenderer wrappers
            items = [_normalize_video(item) for item in items]

            count = 0
            for v in items[:50]:
                # --- save to comprehensive youtube_videos table ---
                try:
                    _save_youtube_video(v, keyword=kw, geo=geo)
                except Exception:
                    logger.error("Failed saving youtube_video detail for kw=%s", kw, exc_info=True)

                # --- save to shared trends table for dashboard ---
                title = v.get("title", "") if isinstance(v.get("title"), str) else ""
                views = _parse_int(v.get("viewCount") or v.get("view_count") or v.get("views") or 0)
                topic = title[:120] if title else f"Video {v.get('videoId', '')}"

                video_id = v.get("videoId") or v.get("video_id") or ""
                url = f"https://www.youtube.com/watch?v={video_id}" if video_id else v.get("url", "")
                channel = v.get("channelTitle") or v.get("channel") or ""
                published = v.get("publishedTimeText") if isinstance(v.get("publishedTimeText"), str) else ""
                if not published:
                    published = v.get("published") or ""

                save_trend(
                    platform=PLATFORM,
                    topic=topic,
                    growth=views,
                    keyword=kw,
                    geo=geo,
                    url=url,
                    extra_data={
                        "video_id": video_id, "channel": channel,
                        "published": published, "views": views,
                    },
                )
                count += 1

            logger.info("Saved %d videos for '%s' (units charged: %s)", count, kw, result.units_charged)

        except Exception as e:
            save_error(PLATFORM, kw, None, 0, str(e))
            logger.error("Error for '%s': %s", kw, e, exc_info=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords")
    parser.add_argument("--geo", default="Global")
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--period", default="month")
    parser.add_argument("--sorting", default="views")
    args = parser.parse_args()
    scrape_youtube([k.strip() for k in args.keywords.split(",")], geo=args.geo, depth=args.depth, period=args.period, sorting=args.sorting)

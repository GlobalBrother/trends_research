"""Instagram scraper using ensembledata API.

Saves comprehensive post data into a dedicated ``instagram_posts`` table
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

PLATFORM = "Instagram"

# ---------------------------------------------------------------------------
# Instagram-specific table
# ---------------------------------------------------------------------------

_CREATE_INSTAGRAM_POSTS = """
CREATE TABLE IF NOT EXISTS instagram_posts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- identifiers
    post_pk             TEXT UNIQUE,
    shortcode           TEXT,
    search_keyword      TEXT,
    geo                 TEXT,

    -- content
    caption             TEXT,
    media_type          INTEGER,
    url                 TEXT,
    thumbnail_url       TEXT,
    taken_at            INTEGER,
    location_name       TEXT,
    location_lat        REAL,
    location_lng        REAL,

    -- author
    username            TEXT,
    user_pk             TEXT,
    full_name           TEXT,
    follower_count      INTEGER DEFAULT 0,
    is_verified         INTEGER DEFAULT 0,
    profile_pic_url     TEXT,

    -- statistics
    like_count          INTEGER DEFAULT 0,
    comment_count       INTEGER DEFAULT 0,
    share_count         INTEGER DEFAULT 0,
    save_count          INTEGER DEFAULT 0,
    video_view_count    INTEGER DEFAULT 0,
    video_play_count    INTEGER DEFAULT 0,

    -- engagement helpers (computed)
    engagement_total    INTEGER DEFAULT 0,

    -- hashtags (JSON array)
    hashtags            TEXT,

    -- metadata
    extracted_at        TEXT,
    updated_at          TEXT
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ig_keyword ON instagram_posts (search_keyword);",
    "CREATE INDEX IF NOT EXISTS idx_ig_username ON instagram_posts (username);",
    "CREATE INDEX IF NOT EXISTS idx_ig_taken ON instagram_posts (taken_at);",
    "CREATE INDEX IF NOT EXISTS idx_ig_likes ON instagram_posts (like_count DESC);",
]


def _ensure_table():
    """Tables are pre-created in Azure SQL via migration schema."""
    pass


def _save_instagram_post(item: dict, keyword: str, geo: str):
    """Insert or update a single post row in instagram_posts."""
    post_pk = str(item.get("pk") or item.get("id") or "")
    if not post_pk:
        return

    user = item.get("user", {}) or {}
    username = user.get("username", "")
    user_pk = str(user.get("pk", ""))
    full_name = user.get("full_name", "")
    follower_count = user.get("follower_count", 0) or 0
    is_verified = 1 if user.get("is_verified") else 0
    profile_pic = user.get("profile_pic_url", "")

    caption = ""
    if isinstance(item.get("caption"), dict):
        caption = item["caption"].get("text", "")
    elif isinstance(item.get("caption"), str):
        caption = item["caption"]

    media_type = item.get("media_type", 0) or 0
    shortcode = item.get("code") or item.get("shortcode") or ""
    url = f"https://www.instagram.com/p/{shortcode}/" if shortcode else ""
    thumbnail = ""
    if isinstance(item.get("image_versions2"), dict):
        candidates = item["image_versions2"].get("candidates", [])
        if candidates:
            thumbnail = candidates[0].get("url", "")
    if not thumbnail:
        thumbnail = item.get("thumbnail_url") or item.get("display_url") or ""

    taken_at = item.get("taken_at", 0) or 0
    location = item.get("location", {}) or {}
    location_name = location.get("name", "") if isinstance(location, dict) else ""
    location_lat = location.get("lat", 0) if isinstance(location, dict) else 0
    location_lng = location.get("lng", 0) if isinstance(location, dict) else 0

    likes = item.get("like_count", 0) or 0
    comments = item.get("comment_count", 0) or 0
    shares = item.get("share_count", 0) or item.get("reshare_count", 0) or 0
    saves = item.get("save_count", 0) or 0
    video_views = item.get("video_view_count", 0) or 0
    video_plays = item.get("video_play_count") or item.get("play_count", 0) or 0
    engagement = likes + comments + shares + saves

    # Extract hashtags from caption
    hashtags = []
    if caption:
        import re
        hashtags = re.findall(r'#(\w+)', caption)

    now = datetime.now().isoformat()

    params = {
        "post_pk": post_pk, "shortcode": shortcode, "keyword": keyword, "geo": geo,
        "caption": caption, "media_type": media_type, "url": url, "thumbnail_url": thumbnail,
        "taken_at": taken_at, "location_name": location_name,
        "location_lat": location_lat, "location_lng": location_lng,
        "username": username, "user_pk": user_pk, "full_name": full_name,
        "follower_count": follower_count, "is_verified": is_verified, "profile_pic_url": profile_pic,
        "like_count": likes, "comment_count": comments, "share_count": shares,
        "save_count": saves, "video_view_count": video_views, "video_play_count": video_plays,
        "engagement_total": engagement, "hashtags": json.dumps(hashtags),
        "extracted_at": now, "updated_at": now,
    }

    with _engine.connect() as conn:
        try:
            if is_sqlite():
                existing = conn.execute(text(f"SELECT 1 FROM {tbl('instagram_posts')} WHERE post_pk = :post_pk"), {"post_pk": post_pk}).fetchone()
                if existing:
                    conn.execute(text(
                        f"UPDATE {tbl('instagram_posts')} SET like_count = :like_count, comment_count = :comment_count, "
                        "share_count = :share_count, save_count = :save_count, "
                        "video_view_count = :video_view_count, video_play_count = :video_play_count, "
                        "engagement_total = :engagement_total, follower_count = :follower_count, "
                        "updated_at = :updated_at WHERE post_pk = :post_pk"
                    ), params)
                else:
                    conn.execute(text(
                        f"INSERT INTO {tbl('instagram_posts')} ("
                        "post_pk, shortcode, search_keyword, geo, "
                        "caption, media_type, url, thumbnail_url, taken_at, "
                        "location_name, location_lat, location_lng, "
                        "username, user_pk, full_name, follower_count, is_verified, profile_pic_url, "
                        "like_count, comment_count, share_count, save_count, "
                        "video_view_count, video_play_count, "
                        "engagement_total, hashtags, extracted_at, updated_at"
                        ") VALUES ("
                        ":post_pk, :shortcode, :keyword, :geo, "
                        ":caption, :media_type, :url, :thumbnail_url, :taken_at, "
                        ":location_name, :location_lat, :location_lng, "
                        ":username, :user_pk, :full_name, :follower_count, :is_verified, :profile_pic_url, "
                        ":like_count, :comment_count, :share_count, :save_count, "
                        ":video_view_count, :video_play_count, "
                        ":engagement_total, :hashtags, :extracted_at, :updated_at)"
                    ), params)
            else:
                conn.execute(text(f"""
                    MERGE {tbl('instagram_posts')} AS target
                    USING (SELECT :post_pk AS post_pk) AS source
                    ON target.post_pk = source.post_pk
                    WHEN MATCHED THEN UPDATE SET
                        like_count = :like_count, comment_count = :comment_count,
                        share_count = :share_count, save_count = :save_count,
                        video_view_count = :video_view_count, video_play_count = :video_play_count,
                        engagement_total = :engagement_total, follower_count = :follower_count,
                        updated_at = :updated_at
                    WHEN NOT MATCHED THEN INSERT (
                        post_pk, shortcode, search_keyword, geo,
                        caption, media_type, url, thumbnail_url, taken_at,
                        location_name, location_lat, location_lng,
                        username, user_pk, full_name, follower_count, is_verified, profile_pic_url,
                        like_count, comment_count, share_count, save_count,
                        video_view_count, video_play_count,
                        engagement_total, hashtags, extracted_at, updated_at
                    ) VALUES (
                        :post_pk, :shortcode, :keyword, :geo,
                        :caption, :media_type, :url, :thumbnail_url, :taken_at,
                        :location_name, :location_lat, :location_lng,
                        :username, :user_pk, :full_name, :follower_count, :is_verified, :profile_pic_url,
                        :like_count, :comment_count, :share_count, :save_count,
                        :video_view_count, :video_play_count,
                        :engagement_total, :hashtags, :extracted_at, :updated_at
                    );
                """), params)
            conn.commit()
            logger.debug("Saved instagram_post pk=%s", post_pk)
        except Exception:
            logger.error("Failed to save instagram_post pk=%s", post_pk, exc_info=True)
            raise


# ---------------------------------------------------------------------------
# Public scrape entry-point
# ---------------------------------------------------------------------------

def scrape_instagram(keywords, geo="Global"):
    """Fetch Instagram search results for each keyword via ensembledata.

    The ``client.instagram.search()`` endpoint returns three categories:
    ``data.hashtags``, ``data.places``, and ``data.users``.  Each category
    is unwrapped and saved both to the dedicated ``instagram_posts`` table
    and the shared ``trends`` table.
    """
    token = os.getenv("ENSEMBLEDATA_TOKEN", "")
    if not token:
        logger.warning("ENSEMBLEDATA_TOKEN not set – skipping Instagram scrape.")
        return

    _ensure_table()
    client = EDClient(token=token)

    for kw in keywords:
        try:
            result = client.instagram.search(text=kw)
            raw = result.data or {}

            # ----------------------------------------------------------
            # The API returns {hashtags: [], places: [], users: []}
            # Unwrap each category into a flat list of pseudo-items that
            # _save_instagram_post and save_trend can consume.
            # ----------------------------------------------------------
            items = []

            if isinstance(raw, dict):
                # --- hashtags ---
                for entry in raw.get("hashtags", []):
                    ht = entry.get("hashtag", entry) if isinstance(entry, dict) else entry
                    if not isinstance(ht, dict):
                        continue
                    items.append({
                        "pk": str(ht.get("id", "")),
                        "_type": "hashtag",
                        "caption": {"text": f"#{ht.get('name', '')}"},
                        "like_count": ht.get("media_count", 0) or 0,
                        "user": {"username": f"#{ht.get('name', '')}"},
                        "_raw": entry,
                    })

                # --- users ---
                for entry in raw.get("users", []):
                    usr = entry.get("user", entry) if isinstance(entry, dict) else entry
                    if not isinstance(usr, dict):
                        continue
                    items.append({
                        "pk": str(usr.get("pk", "")),
                        "_type": "user",
                        "caption": {"text": usr.get("full_name", "") or usr.get("username", "")},
                        "user": usr,
                        "like_count": 0,
                        "code": "",
                        "_raw": entry,
                    })

                # --- places ---
                for entry in raw.get("places", []):
                    pl = entry.get("place", entry) if isinstance(entry, dict) else entry
                    if not isinstance(pl, dict):
                        continue
                    loc = pl.get("location", {}) or {}
                    items.append({
                        "pk": str(loc.get("pk", "")),
                        "_type": "place",
                        "caption": {"text": pl.get("title", "") or loc.get("name", "")},
                        "location": loc,
                        "user": {"username": pl.get("title", "")},
                        "like_count": 0,
                        "code": "",
                        "_raw": entry,
                    })

                # Fallback: if the response is a flat list of posts
                if not items:
                    items = raw.get("items", []) or raw.get("results", []) or []
            elif isinstance(raw, list):
                items = raw

            count = 0
            for item in items[:50]:
                # --- save to comprehensive instagram_posts table ---
                try:
                    _save_instagram_post(item, keyword=kw, geo=geo)
                except Exception:
                    logger.error("Failed saving instagram_post detail for kw=%s", kw, exc_info=True)

                # --- save to shared trends table for dashboard ---
                user = item.get("user", {}) or {}
                username = user.get("username", "")
                caption = ""
                if isinstance(item.get("caption"), dict):
                    caption = item["caption"].get("text", "")
                elif isinstance(item.get("caption"), str):
                    caption = item["caption"]

                topic = caption[:120] if caption else f"@{username}" if username else f"Post {item.get('pk', '')}"
                likes = item.get("like_count", 0) or 0
                comments = item.get("comment_count", 0) or 0
                engagement = likes + comments

                shortcode = item.get("code") or item.get("shortcode") or ""
                url = f"https://www.instagram.com/p/{shortcode}/" if shortcode else ""

                save_trend(
                    platform=PLATFORM,
                    topic=topic,
                    growth=engagement,
                    keyword=kw,
                    geo=geo,
                    url=url,
                    extra_data={
                        "likes": likes, "comments": comments,
                        "username": username, "shortcode": shortcode,
                        "type": item.get("_type", "post"),
                    },
                )
                count += 1

            logger.info("Saved %d items for '%s' (units charged: %s)", count, kw, result.units_charged)
            if result.units_charged:
                save_token_usage(PLATFORM, kw, result.units_charged, geo)

        except EDError as e:
            save_error(PLATFORM, kw, None, 0, str(e))
            if e.status_code == 495:
                logger.warning("Daily API limit reached. Stopping Instagram scraper.")
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
    args = parser.parse_args()
    scrape_instagram([k.strip() for k in args.keywords.split(",")], geo=args.geo)

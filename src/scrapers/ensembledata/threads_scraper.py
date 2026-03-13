"""Threads scraper using ensembledata API.

Saves comprehensive post data into a dedicated ``threads_posts`` table
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

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(__file__))
from db_helper import save_trend, save_error, DB_PATH

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

PLATFORM = "Threads"

# ---------------------------------------------------------------------------
# Threads-specific table
# ---------------------------------------------------------------------------

_CREATE_THREADS_POSTS = """
CREATE TABLE IF NOT EXISTS threads_posts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- identifiers
    post_code           TEXT UNIQUE,
    post_pk             TEXT,
    search_keyword      TEXT,
    geo                 TEXT,

    -- content
    caption             TEXT,
    url                 TEXT,
    taken_at            INTEGER,
    media_type          TEXT,

    -- author
    username            TEXT,
    user_pk             TEXT,
    full_name           TEXT,
    follower_count      INTEGER DEFAULT 0,
    is_verified         INTEGER DEFAULT 0,
    profile_pic_url     TEXT,

    -- statistics
    like_count          INTEGER DEFAULT 0,
    reply_count         INTEGER DEFAULT 0,
    repost_count        INTEGER DEFAULT 0,
    quote_count         INTEGER DEFAULT 0,
    share_count         INTEGER DEFAULT 0,

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
    "CREATE INDEX IF NOT EXISTS idx_th_keyword ON threads_posts (search_keyword);",
    "CREATE INDEX IF NOT EXISTS idx_th_username ON threads_posts (username);",
    "CREATE INDEX IF NOT EXISTS idx_th_taken ON threads_posts (taken_at);",
    "CREATE INDEX IF NOT EXISTS idx_th_likes ON threads_posts (like_count DESC);",
]


def _ensure_table():
    """Create the threads_posts table and indexes if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_CREATE_THREADS_POSTS)
        for idx in _CREATE_INDEXES:
            conn.execute(idx)
        conn.commit()
        logger.debug("threads_posts table ensured.")
    finally:
        conn.close()


def _save_threads_post(inner: dict, keyword: str, geo: str):
    """Insert or update a single post row in threads_posts."""
    code = inner.get("code") or ""
    if not code:
        return

    user = inner.get("user", {}) or {}
    username = user.get("username", "")
    user_pk = str(user.get("pk", ""))
    full_name = user.get("full_name", "")
    follower_count = user.get("follower_count", 0) or 0
    is_verified = 1 if user.get("is_verified") else 0
    profile_pic = user.get("profile_pic_url", "")

    text_info = inner.get("text_post_app_info", {}) or {}

    caption = ""
    if isinstance(inner.get("caption"), dict):
        caption = inner["caption"].get("text", "")
    elif isinstance(inner.get("caption"), str):
        caption = inner["caption"]
    # Fallback: extract from text_fragments (actual API format)
    if not caption and isinstance(text_info, dict):
        frags = (text_info.get("text_fragments") or {}).get("fragments", [])
        if frags:
            caption = " ".join(f.get("plaintext", "") for f in frags if isinstance(f, dict))
    if not caption:
        quoted = (text_info.get("share_info") or {}).get("quoted_text", "")
        if quoted:
            caption = quoted

    post_pk = str(inner.get("pk", ""))
    url = f"https://www.threads.net/@{username}/post/{code}" if username and code else ""
    taken_at = inner.get("taken_at", 0) or 0
    media_type = str(inner.get("media_type", ""))

    likes = inner.get("like_count", 0) or 0
    replies = 0
    if isinstance(text_info, dict):
        replies = text_info.get("direct_reply_count", 0) or 0
    repost_count = 0
    if isinstance(text_info, dict):
        repost_count = text_info.get("repost_count", 0) or 0
    if not repost_count:
        repost_count = inner.get("repost_count", 0) or inner.get("reshare_count", 0) or 0
    quote_count = 0
    if isinstance(text_info, dict):
        quote_count = text_info.get("quote_count", 0) or 0
    if not quote_count:
        quote_count = inner.get("quote_count", 0) or 0
    share_count = inner.get("share_count", 0) or 0
    engagement = likes + replies + repost_count + quote_count

    now = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            INSERT INTO threads_posts (
                post_code, post_pk, search_keyword, geo,
                caption, url, taken_at, media_type,
                username, user_pk, full_name, follower_count, is_verified, profile_pic_url,
                like_count, reply_count, repost_count, quote_count, share_count,
                engagement_total, raw_data,
                extracted_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(post_code) DO UPDATE SET
                like_count=excluded.like_count,
                reply_count=excluded.reply_count,
                repost_count=excluded.repost_count,
                quote_count=excluded.quote_count,
                share_count=excluded.share_count,
                engagement_total=excluded.engagement_total,
                follower_count=excluded.follower_count,
                raw_data=excluded.raw_data,
                updated_at=excluded.updated_at
        """, (
            code, post_pk, keyword, geo,
            caption, url, taken_at, media_type,
            username, user_pk, full_name, follower_count, is_verified, profile_pic,
            likes, replies, repost_count, quote_count, share_count,
            engagement, json.dumps(inner, default=str),
            now, now,
        ))
        conn.commit()
        logger.debug("Saved threads_post code=%s", code)
    except Exception:
        logger.error("Failed to save threads_post code=%s", code, exc_info=True)
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public scrape entry-point
# ---------------------------------------------------------------------------

def scrape_threads(keywords, geo="Global"):
    """Fetch Threads posts for each keyword via ensembledata."""
    token = os.getenv("ENSEMBLEDATA_TOKEN", "")
    if not token:
        logger.warning("ENSEMBLEDATA_TOKEN not set – skipping Threads scrape.")
        return

    _ensure_table()
    client = EDClient(token=token)

    for kw in keywords:
        try:
            result = client.threads.search_keyword(name=kw)
            items = result.data or []
            if isinstance(items, dict):
                items = items.get("items", []) or items.get("posts", []) or []

            count = 0
            for item in items[:50]:
                # Unwrap ensembledata envelope: data[].node.thread.thread_items[].post
                node = item.get("node", item) if isinstance(item, dict) else item
                thread = node.get("thread", node) if isinstance(node, dict) else node
                thread_items = thread.get("thread_items", []) if isinstance(thread, dict) else []
                if thread_items and isinstance(thread_items, list):
                    post = thread_items[0]
                else:
                    post = thread if isinstance(thread, dict) else item
                inner = post.get("post", post) if isinstance(post, dict) else post

                # --- save to comprehensive threads_posts table ---
                try:
                    _save_threads_post(inner, keyword=kw, geo=geo)
                except Exception:
                    logger.error("Failed saving threads_post detail for kw=%s", kw, exc_info=True)

                # --- save to shared trends table for dashboard ---
                caption = ""
                if isinstance(inner.get("caption"), dict):
                    caption = inner["caption"].get("text", "")
                elif isinstance(inner.get("caption"), str):
                    caption = inner["caption"]
                # Fallback: text_fragments from actual API format
                t_info = inner.get("text_post_app_info", {}) or {}
                if not caption and isinstance(t_info, dict):
                    frags = (t_info.get("text_fragments") or {}).get("fragments", [])
                    if frags:
                        caption = " ".join(f.get("plaintext", "") for f in frags if isinstance(f, dict))
                if not caption:
                    quoted = (t_info.get("share_info") or {}).get("quoted_text", "")
                    if quoted:
                        caption = quoted

                user = inner.get("user", {}) or {}
                username = user.get("username", "")
                topic = caption[:120] if caption else f"@{username}" if username else "Threads post"

                likes = inner.get("like_count", 0) or 0
                replies = 0
                if isinstance(t_info, dict):
                    replies = t_info.get("direct_reply_count", 0) or 0
                repost_c = 0
                if isinstance(t_info, dict):
                    repost_c = t_info.get("repost_count", 0) or 0
                engagement = likes + replies + repost_c

                code = inner.get("code") or ""
                url = f"https://www.threads.net/@{username}/post/{code}" if username and code else ""

                save_trend(
                    platform=PLATFORM,
                    topic=topic,
                    growth=engagement,
                    keyword=kw,
                    geo=geo,
                    url=url,
                    extra_data={
                        "likes": likes, "replies": replies,
                        "reposts": repost_c, "username": username,
                    },
                )
                count += 1

            logger.info("Saved %d posts for '%s' (units charged: %s)", count, kw, result.units_charged)

        except Exception as e:
            save_error(PLATFORM, kw, None, 0, str(e))
            logger.error("Error for '%s': %s", kw, e, exc_info=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords")
    parser.add_argument("--geo", default="Global")
    args = parser.parse_args()
    scrape_threads([k.strip() for k in args.keywords.split(",")], geo=args.geo)

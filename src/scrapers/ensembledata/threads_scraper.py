"""Threads scraper using ensembledata API.

Saves content data into the normalized ``content``, ``authors``,
``content_metrics``, and ``content_hashtags`` tables, as well as the
shared ``trends`` table for cross-platform dashboards.
"""

import json
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from dotenv import load_dotenv
from ensembledata.api import EDClient
from ensembledata.api.errors import EDError

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(__file__))
from db_helper import save_trend, save_error, save_token_usage, save_content_normalized

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

PLATFORM = "Threads"


def _save_threads_post(inner: dict, keyword: str, geo: str):
    """Save a single Threads post into the normalized content tables."""
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
    if not caption and isinstance(text_info, dict):
        frags = (text_info.get("text_fragments") or {}).get("fragments", [])
        if frags:
            caption = " ".join(f.get("plaintext", "") for f in frags if isinstance(f, dict))
    if not caption:
        quoted = (text_info.get("share_info") or {}).get("quoted_text", "")
        if quoted:
            caption = quoted

    url = f"https://www.threads.net/@{username}/post/{code}" if username and code else ""
    taken_at = inner.get("taken_at", 0) or 0

    likes = inner.get("like_count", 0) or 0
    replies = 0
    if isinstance(text_info, dict):
        replies = text_info.get("direct_reply_count", 0) or 0
    repost_count = 0
    if isinstance(text_info, dict):
        repost_count = text_info.get("repost_count", 0) or 0
    if not repost_count:
        repost_count = inner.get("repost_count", 0) or inner.get("reshare_count", 0) or 0
    share_count = inner.get("share_count", 0) or 0

    save_content_normalized(
        platform=PLATFORM,
        external_id=code,
        keyword=keyword,
        geo=geo,
        text_content=caption,
        media_type=str(inner.get("media_type", "")),
        url=url,
        content_created_at=datetime.fromtimestamp(taken_at) if taken_at else None,
        author_external_id=user_pk if user_pk else None,
        author_username=username,
        author_full_name=full_name,
        author_follower_count=follower_count,
        author_is_verified=is_verified,
        author_profile_pic=profile_pic,
        likes=likes,
        comments=replies,
        shares=share_count + repost_count,
    )


# ---------------------------------------------------------------------------
# Public scrape entry-point
# ---------------------------------------------------------------------------

def scrape_threads(keywords, geo="Global"):
    """Fetch Threads posts for each keyword via ensembledata."""
    token = os.getenv("ENSEMBLEDATA_TOKEN", "")
    if not token:
        logger.warning("ENSEMBLEDATA_TOKEN not set – skipping Threads scrape.")
        return

    client = EDClient(token=token)
    stop_event = threading.Event()

    def _scrape_keyword(kw):
        if stop_event.is_set():
            return
        try:
            result = client.threads.search_keyword(name=kw)
            items = result.data or []
            if isinstance(items, dict):
                items = items.get("items", []) or items.get("posts", []) or []

            count = 0
            for item in items[:50]:
                node = item.get("node", item) if isinstance(item, dict) else item
                thread = node.get("thread", node) if isinstance(node, dict) else node
                thread_items = thread.get("thread_items", []) if isinstance(thread, dict) else []
                if thread_items and isinstance(thread_items, list):
                    post = thread_items[0]
                else:
                    post = thread if isinstance(thread, dict) else item
                inner = post.get("post", post) if isinstance(post, dict) else post

                try:
                    _save_threads_post(inner, keyword=kw, geo=geo)
                except Exception:
                    logger.error("Failed saving threads content for kw=%s", kw, exc_info=True)

                caption = ""
                if isinstance(inner.get("caption"), dict):
                    caption = inner["caption"].get("text", "")
                elif isinstance(inner.get("caption"), str):
                    caption = inner["caption"]
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
            if result.units_charged:
                save_token_usage(PLATFORM, kw, result.units_charged, geo)

        except EDError as e:
            save_error(PLATFORM, kw, None, 0, str(e))
            if e.status_code == 495:
                logger.warning("Daily API limit reached. Stopping Threads scraper.")
                stop_event.set()
            else:
                logger.error("Error for '%s': %s", kw, e, exc_info=True)
        except Exception as e:
            save_error(PLATFORM, kw, None, 0, str(e))
            logger.error("Error for '%s': %s", kw, e, exc_info=True)

    with ThreadPoolExecutor(max_workers=min(len(keywords), 4)) as pool:
        list(pool.map(_scrape_keyword, keywords))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords")
    parser.add_argument("--geo", default="Global")
    args = parser.parse_args()
    scrape_threads([k.strip() for k in args.keywords.split(",")], geo=args.geo)

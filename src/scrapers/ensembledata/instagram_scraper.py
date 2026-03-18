"""Instagram scraper using ensembledata API.

Saves content data into the normalized ``content``, ``authors``,
``content_metrics``, and ``content_hashtags`` tables, as well as the
shared ``trends`` table for cross-platform dashboards.
"""

import json
import logging
import os
import re
import sys
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

PLATFORM = "Instagram"


def _save_instagram_post(item: dict, keyword: str, geo: str):
    """Save a single Instagram post into the normalized content tables."""
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

    media_type = str(item.get("media_type", 0) or 0)
    shortcode = item.get("code") or item.get("shortcode") or ""
    url = f"https://www.instagram.com/p/{shortcode}/" if shortcode else ""

    taken_at = item.get("taken_at", 0) or 0

    likes = item.get("like_count", 0) or 0
    comments = item.get("comment_count", 0) or 0
    shares = item.get("share_count", 0) or item.get("reshare_count", 0) or 0
    saves = item.get("save_count", 0) or 0
    video_views = item.get("video_view_count", 0) or 0
    video_plays = item.get("video_play_count") or item.get("play_count", 0) or 0

    # Extract hashtags from caption
    hashtags = []
    if caption:
        hashtags = re.findall(r'#(\w+)', caption)

    save_content_normalized(
        platform=PLATFORM,
        external_id=post_pk,
        keyword=keyword,
        geo=geo,
        text_content=caption,
        media_type=media_type,
        url=url,
        content_created_at=datetime.fromtimestamp(taken_at).isoformat() if taken_at else None,
        author_external_id=user_pk if user_pk else None,
        author_username=username,
        author_full_name=full_name,
        author_follower_count=follower_count,
        author_is_verified=is_verified,
        author_profile_pic=profile_pic,
        likes=likes,
        comments=comments,
        shares=shares,
        views=video_views + video_plays,
        saves=saves,
        hashtags=hashtags,
    )


# ---------------------------------------------------------------------------
# Public scrape entry-point
# ---------------------------------------------------------------------------

def scrape_instagram(keywords, geo="Global"):
    """Fetch Instagram search results for each keyword via ensembledata."""
    token = os.getenv("ENSEMBLEDATA_TOKEN", "")
    if not token:
        logger.warning("ENSEMBLEDATA_TOKEN not set – skipping Instagram scrape.")
        return

    client = EDClient(token=token)

    for kw in keywords:
        try:
            result = client.instagram.search(text=kw)
            raw = result.data or {}

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

                if not items:
                    items = raw.get("items", []) or raw.get("results", []) or []
            elif isinstance(raw, list):
                items = raw

            count = 0
            for item in items[:50]:
                # --- save to normalized content tables ---
                try:
                    _save_instagram_post(item, keyword=kw, geo=geo)
                except Exception:
                    logger.error("Failed saving instagram content for kw=%s", kw, exc_info=True)

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

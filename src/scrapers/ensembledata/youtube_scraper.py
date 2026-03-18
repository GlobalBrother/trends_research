"""YouTube scraper using ensembledata API.

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

PLATFORM = "YouTube"


def _parse_int(val):
    """Safely parse an integer from a string that may contain commas or words."""
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        digits = re.sub(r"[^\d]", "", val)
        return int(digits) if digits else 0
    return 0


def _normalize_video(raw: dict) -> dict:
    """Flatten a videoRenderer envelope into a simple dict."""
    vr = raw.get("videoRenderer") if isinstance(raw, dict) else None
    if not vr:
        return raw

    v = dict(vr)

    title_obj = v.get("title")
    if isinstance(title_obj, dict):
        runs = title_obj.get("runs", [])
        v["title"] = runs[0].get("text", "") if runs else ""

    for key in ("ownerText", "longBylineText", "shortBylineText"):
        obj = v.get(key)
        if isinstance(obj, dict):
            runs = obj.get("runs", [])
            if runs:
                v["channelTitle"] = runs[0].get("text", "")
                nav = runs[0].get("navigationEndpoint", {})
                browse = nav.get("browseEndpoint", {})
                if browse.get("browseId"):
                    v["channelId"] = browse["browseId"]
                break

    vct = v.get("viewCountText")
    if isinstance(vct, dict):
        v["viewCount"] = vct.get("simpleText", "0")

    ptt = v.get("publishedTimeText")
    if isinstance(ptt, dict):
        v["publishedTimeText"] = ptt.get("simpleText", "")

    lt = v.get("lengthText")
    if isinstance(lt, dict):
        v["lengthText"] = lt.get("simpleText", "")

    snippets = v.get("detailedMetadataSnippets", [])
    if snippets and isinstance(snippets, list):
        snippet_text = snippets[0].get("snippetText", {})
        runs = snippet_text.get("runs", []) if isinstance(snippet_text, dict) else []
        if runs:
            v["description"] = "".join(r.get("text", "") for r in runs)

    return v


def _save_youtube_video(v: dict, keyword: str, geo: str):
    """Save a single YouTube video into the normalized content tables."""
    video_id = v.get("videoId") or v.get("video_id") or ""
    if not video_id:
        return

    title = v.get("title", "") if isinstance(v.get("title"), str) else ""
    description = v.get("description") or v.get("descriptionSnippet") or ""
    channel = v.get("channelTitle") or v.get("channel") or ""
    channel_id = v.get("channelId") or v.get("channel_id") or ""
    url = f"https://www.youtube.com/watch?v={video_id}" if video_id else v.get("url", "")

    views = _parse_int(v.get("viewCount") or v.get("view_count") or v.get("views") or 0)
    likes = _parse_int(v.get("likeCount") or v.get("like_count") or v.get("likes") or 0)
    comments = _parse_int(v.get("commentCount") or v.get("comment_count") or 0)

    tags = v.get("tags") or v.get("keywords") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = []

    text_content = title
    if description:
        text_content = f"{title}\n{description}" if title else description

    save_content_normalized(
        platform=PLATFORM,
        external_id=video_id,
        keyword=keyword,
        geo=geo,
        text_content=text_content,
        media_type="video",
        url=url,
        content_created_at=None,
        author_external_id=channel_id if channel_id else None,
        author_username=channel,
        author_full_name=channel,
        likes=likes,
        comments=comments,
        views=views,
        hashtags=tags if isinstance(tags, list) else [],
    )


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

    client = EDClient(token=token)

    for kw in keywords:
        try:
            result = client.youtube.keyword_search(
                keyword=kw, depth=depth, period=period, sorting=sorting,
            )
            raw_data = result.data or []

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

            items = [_normalize_video(item) for item in items]

            count = 0
            for v in items[:50]:
                # --- save to normalized content tables ---
                try:
                    _save_youtube_video(v, keyword=kw, geo=geo)
                except Exception:
                    logger.error("Failed saving youtube content for kw=%s", kw, exc_info=True)

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
            if result.units_charged:
                save_token_usage(PLATFORM, kw, result.units_charged, geo)

        except EDError as e:
            save_error(PLATFORM, kw, None, 0, str(e))
            if e.status_code == 495:
                logger.warning("Daily API limit reached. Stopping YouTube scraper.")
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
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--period", default="month")
    parser.add_argument("--sorting", default="views")
    args = parser.parse_args()
    scrape_youtube([k.strip() for k in args.keywords.split(",")], geo=args.geo, depth=args.depth, period=args.period, sorting=args.sorting)

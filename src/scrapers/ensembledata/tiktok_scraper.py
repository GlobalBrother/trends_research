"""TikTok scraper using ensembledata API.

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
from db_helper import (
    archive_source_response,
    save_trend,
    save_error,
    save_token_usage,
    save_content_normalized,
)
from src.ingestion import IngestionService

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

PLATFORM = "TikTok"
ingestion = IngestionService()


def _save_tiktok_video(v: dict, keyword: str, geo: str):
    """Save a single TikTok video into the normalized content tables."""
    stats = v.get("statistics", {})
    author = v.get("author", {}) or {}
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

    digg = stats.get("digg_count", 0) or 0
    comments = stats.get("comment_count", 0) or 0
    shares = stats.get("share_count", 0) or 0
    plays = stats.get("play_count", 0) or 0
    collect = v.get("collect_stat", 0) or 0

    desc = v.get("desc", "")
    share_url = v.get("share_url") or (v.get("share_info", {}) or {}).get("share_url", "")

    author_uid = str(author.get("uid", "")) or str(author.get("id", ""))
    username = author.get("unique_id") or author.get("uniqueId", "")

    save_content_normalized(
        platform=PLATFORM,
        external_id=aweme_id,
        keyword=keyword,
        geo=geo,
        text_content=desc,
        media_type="video",
        url=share_url,
        content_created_at=datetime.fromtimestamp(v.get("create_time", 0)) if v.get("create_time") else None,
        author_external_id=author_uid if author_uid else None,
        author_username=username,
        author_full_name=author.get("nickname", ""),
        author_follower_count=author.get("follower_count", 0) or 0,
        author_is_verified=1 if author.get("verification_type") else 0,
        author_profile_pic=(author.get("avatar_uri") or ""),
        likes=digg,
        comments=comments,
        shares=shares,
        views=plays,
        saves=collect,
        hashtags=hashtags,
    )


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

    client = EDClient(token=token)
    stop_event = threading.Event()
    run = ingestion.start_run(PLATFORM, acquisition_mode="api", country=geo, language="en")

    def _scrape_keyword(kw):
        if stop_event.is_set():
            return
        try:
            result = ingestion.with_retry(
                PLATFORM,
                lambda: client.tiktok.keyword_search(keyword=kw, period=period),
                run=run,
                payload_hint={"keyword": kw, "geo": geo, "period": period},
            )
            raw = result.data or []
            archive_source_response(
                PLATFORM,
                raw,
                metadata={"keyword": kw, "geo": geo, "period": period, "units_charged": result.units_charged},
            )
            if isinstance(raw, dict):
                inner = raw.get("data", raw.get("videos", []))
                if isinstance(inner, list):
                    raw = inner
                else:
                    raw = []
            if not isinstance(raw, list):
                raw = []
            run.fetched_count += len(raw)

            count = 0
            for item in raw[:50]:
                v = item.get("aweme_info", item) if isinstance(item, dict) else item
                if not isinstance(v, dict):
                    continue

                try:
                    _save_tiktok_video(v, keyword=kw, geo=geo)
                except Exception:
                    logger.error("Failed saving tiktok content for kw=%s", kw, exc_info=True)

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
                    entity_type="video",
                    entity_id=video_id,
                    sampled_content_refs=[{
                        "id": video_id,
                        "url": url,
                        "title": topic[:250],
                        "snippet": desc[:280],
                    }],
                    fetch_metadata={"keyword": kw, "period": period, "granularity": "day"},
                    raw_payload=v,
                    run=run,
                )
                count += 1

            logger.info("Saved %d videos for '%s' (units charged: %s)", count, kw, result.units_charged)
            if result.units_charged:
                save_token_usage(PLATFORM, kw, result.units_charged, geo)
                run.quota_usage += float(result.units_charged)

        except EDError as e:
            save_error(PLATFORM, kw, None, 0, str(e), payload={"keyword": kw, "geo": geo}, run=run)
            if e.status_code == 495:
                logger.warning("Daily API limit reached. Stopping TikTok scraper.")
                stop_event.set()
            else:
                logger.error("Error for '%s': %s", kw, e, exc_info=True)
        except Exception as e:
            save_error(PLATFORM, kw, None, 0, str(e), payload={"keyword": kw, "geo": geo}, run=run)
            logger.error("Error for '%s': %s", kw, e, exc_info=True)

    try:
        with ThreadPoolExecutor(max_workers=min(len(keywords), 4)) as pool:
            list(pool.map(_scrape_keyword, keywords))
    finally:
        ingestion.finish_run(run)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords")
    parser.add_argument("--geo", default="Global")
    parser.add_argument("--period", default="30")
    args = parser.parse_args()
    scrape_tiktok([k.strip() for k in args.keywords.split(",")], geo=args.geo, period=args.period)

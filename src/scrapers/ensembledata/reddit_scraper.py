"""Reddit scraper using ensembledata API.

Saves content data into the normalized ``content``, ``authors``,
``content_metrics``, and ``content_hashtags`` tables, as well as the
shared ``trends`` table for cross-platform dashboards.
"""

import json
import logging
import os
import sys
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

PLATFORM = "Reddit"
ingestion = IngestionService()


def _save_reddit_post(data: dict, keyword: str, geo: str):
    """Save a single Reddit post into the normalized content tables."""
    post_id = data.get("id") or data.get("name") or ""
    if not post_id:
        return

    title = data.get("title", "")
    selftext = data.get("selftext", "")
    url = data.get("url", "")
    permalink = data.get("permalink", "")

    author = data.get("author", "")
    author_fullname = data.get("author_fullname", "")

    score = data.get("score", 0) or 0
    num_comments = data.get("num_comments") or data.get("numComments") or 0

    text_content = title
    if selftext:
        text_content = f"{title}\n{selftext}" if title else selftext

    full_url = f"https://www.reddit.com{permalink}" if permalink else url

    save_content_normalized(
        platform=PLATFORM,
        external_id=post_id,
        keyword=keyword,
        geo=geo,
        text_content=text_content,
        media_type="text" if data.get("is_self") else "link",
        url=full_url,
        content_created_at=datetime.fromtimestamp(data.get("created_utc", 0)) if data.get("created_utc") else None,
        author_external_id=author_fullname if author_fullname else (author if author else None),
        author_username=author,
        likes=score,
        comments=num_comments,
    )


# ---------------------------------------------------------------------------
# Public scrape entry-point
# ---------------------------------------------------------------------------

def scrape_reddit(subreddits, geo="Global", sort="hot", period="day"):
    """
    Fetch Reddit posts from subreddits via ensembledata.

    Parameters
    ----------
    subreddits : list[str]  – subreddit names (without r/)
    geo : str
    sort : str – 'hot', 'new', 'top', 'rising'
    period : str – 'hour', 'day', 'week', 'month', 'year', 'all'
    """
    token = os.getenv("ENSEMBLEDATA_TOKEN", "")
    if not token:
        logger.warning("ENSEMBLEDATA_TOKEN not set – skipping Reddit scrape.")
        return

    client = EDClient(token=token)
    run = ingestion.start_run(PLATFORM, acquisition_mode="api", country=geo, language="en", category=sort)

    try:
        for sub in subreddits:
            try:
                result = ingestion.with_retry(
                    PLATFORM,
                    lambda: client.reddit.subreddit_posts(name=sub, sort=sort, period=period),
                    run=run,
                    payload_hint={"subreddit": sub, "sort": sort, "period": period, "geo": geo},
                )
                archive_source_response(
                    PLATFORM,
                    result.data or [],
                    metadata={"subreddit": sub, "sort": sort, "period": period, "geo": geo, "units_charged": result.units_charged},
                )
                posts = result.data or []
                if isinstance(posts, dict):
                    posts = posts.get("posts", []) or posts.get("children", []) or []
                run.fetched_count += len(posts)

                count = 0
                for p in posts[:50]:
                    data = p.get("data", p) if isinstance(p, dict) else p
                    if not isinstance(data, dict):
                        continue

                    # --- save to normalized content tables ---
                    try:
                        _save_reddit_post(data, keyword=f"r/{sub}", geo=geo)
                    except Exception:
                        logger.error("Failed saving reddit content for r/%s", sub, exc_info=True)

                    # --- save to shared trends table for dashboard ---
                    title = data.get("title", "")
                    score = data.get("score", 0) or 0
                    num_comments = data.get("num_comments") or data.get("numComments") or 0
                    permalink = data.get("permalink", "")
                    url = f"https://www.reddit.com{permalink}" if permalink else ""
                    subreddit_name = data.get("subreddit", sub)

                    save_trend(
                        platform=PLATFORM,
                        topic=title[:120] if title else f"Post in r/{sub}",
                        growth=score * 5,
                        keyword=f"r/{sub}",
                        geo=geo,
                        url=url,
                        extra_data={
                            "score": score, "num_comments": num_comments,
                            "subreddit": subreddit_name,
                            "engagement": num_comments * 10,
                            "selftext": data.get("selftext", ""),
                            "units_charged": result.units_charged,
                        },
                        entity_type="post",
                        entity_id=str(data.get("id") or data.get("name") or title[:64]),
                        sampled_content_refs=[{
                            "id": str(data.get("id") or data.get("name") or ""),
                            "url": url,
                            "title": title[:250],
                            "snippet": (data.get("selftext") or "")[:280],
                        }],
                        fetch_metadata={"keyword": f"r/{sub}", "sort": sort, "period": period, "granularity": "hour"},
                        raw_payload=data,
                        run=run,
                    )
                    count += 1

                logger.info("Saved %d posts for r/%s (units charged: %s)", count, sub, result.units_charged)
                if result.units_charged:
                    save_token_usage(PLATFORM, sub, result.units_charged, geo)
                    run.quota_usage += float(result.units_charged)

            except EDError as e:
                save_error(PLATFORM, f"r/{sub}", None, 0, str(e), payload={"subreddit": sub, "geo": geo}, run=run)
                if e.status_code == 495:
                    logger.warning("Daily API limit reached. Stopping Reddit scraper.")
                    break
                logger.error("Error for r/%s: %s", sub, e, exc_info=True)
            except Exception as e:
                save_error(PLATFORM, f"r/{sub}", None, 0, str(e), payload={"subreddit": sub, "geo": geo}, run=run)
                logger.error("Error for r/%s: %s", sub, e, exc_info=True)
    finally:
        ingestion.finish_run(run)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--subreddits", required=True, help="Comma-separated subreddit names")
    parser.add_argument("--geo", default="Global")
    parser.add_argument("--sort", default="hot")
    parser.add_argument("--period", default="day")
    args = parser.parse_args()
    scrape_reddit([s.strip() for s in args.subreddits.split(",")], geo=args.geo, sort=args.sort, period=args.period)

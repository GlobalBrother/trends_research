"""Reddit scraper using ensembledata API.

Saves comprehensive post data into a dedicated ``reddit_posts`` table
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

PLATFORM = "Reddit"

# ---------------------------------------------------------------------------
# Reddit-specific table
# ---------------------------------------------------------------------------

_CREATE_REDDIT_POSTS = """
CREATE TABLE IF NOT EXISTS reddit_posts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- identifiers
    post_id             TEXT UNIQUE,
    search_keyword      TEXT,
    geo                 TEXT,

    -- content
    title               TEXT,
    selftext            TEXT,
    url                 TEXT,
    permalink           TEXT,
    domain              TEXT,
    post_hint           TEXT,
    is_self             INTEGER DEFAULT 0,
    is_video            INTEGER DEFAULT 0,
    over_18             INTEGER DEFAULT 0,
    spoiler             INTEGER DEFAULT 0,
    created_utc         INTEGER,
    thumbnail           TEXT,

    -- subreddit
    subreddit           TEXT,
    subreddit_id        TEXT,
    subreddit_subscribers INTEGER DEFAULT 0,

    -- author
    author              TEXT,
    author_fullname     TEXT,

    -- statistics
    score               INTEGER DEFAULT 0,
    upvote_ratio        REAL DEFAULT 0,
    num_comments        INTEGER DEFAULT 0,
    num_crossposts      INTEGER DEFAULT 0,
    total_awards        INTEGER DEFAULT 0,

    -- engagement helpers (computed)
    engagement_total    INTEGER DEFAULT 0,

    -- flair / tags
    link_flair_text     TEXT,

    -- metadata
    extracted_at        TEXT,
    updated_at          TEXT
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_rd_keyword ON reddit_posts (search_keyword);",
    "CREATE INDEX IF NOT EXISTS idx_rd_subreddit ON reddit_posts (subreddit);",
    "CREATE INDEX IF NOT EXISTS idx_rd_created ON reddit_posts (created_utc);",
    "CREATE INDEX IF NOT EXISTS idx_rd_score ON reddit_posts (score DESC);",
]


def _ensure_table():
    """Tables are pre-created in Azure SQL via migration schema."""
    pass


def _save_reddit_post(data: dict, keyword: str, geo: str):
    """Insert or update a single post row in reddit_posts."""
    post_id = data.get("id") or data.get("name") or ""
    if not post_id:
        return

    title = data.get("title", "")
    selftext = data.get("selftext", "")
    url = data.get("url", "")
    permalink = data.get("permalink", "")
    domain = data.get("domain", "")
    post_hint = data.get("post_hint", "")
    is_self = 1 if data.get("is_self") else 0
    is_video = 1 if data.get("is_video") else 0
    over_18 = 1 if data.get("over_18") else 0
    spoiler = 1 if data.get("spoiler") else 0
    created_utc = data.get("created_utc", 0) or 0
    thumbnail = data.get("thumbnail", "")

    subreddit = data.get("subreddit", "")
    subreddit_id = data.get("subreddit_id", "")
    subreddit_subscribers = data.get("subreddit_subscribers", 0) or 0

    author = data.get("author", "")
    author_fullname = data.get("author_fullname", "")

    score = data.get("score", 0) or 0
    upvote_ratio = data.get("upvote_ratio", 0) or 0
    num_comments = data.get("num_comments") or data.get("numComments") or 0
    num_crossposts = data.get("num_crossposts", 0) or 0
    total_awards = data.get("total_awards_received", 0) or 0
    engagement = score + (num_comments * 10)

    link_flair = data.get("link_flair_text", "")

    now = datetime.now().isoformat()

    params = {
        "post_id": post_id, "keyword": keyword, "geo": geo,
        "title": title, "selftext": selftext, "url": url, "permalink": permalink,
        "domain": domain, "post_hint": post_hint,
        "is_self": is_self, "is_video": is_video, "over_18": over_18,
        "spoiler": spoiler, "created_utc": int(created_utc), "thumbnail": thumbnail,
        "subreddit": subreddit, "subreddit_id": subreddit_id,
        "subreddit_subscribers": subreddit_subscribers,
        "author": author, "author_fullname": author_fullname,
        "score": score, "upvote_ratio": upvote_ratio, "num_comments": num_comments,
        "num_crossposts": num_crossposts, "total_awards": total_awards,
        "engagement_total": engagement, "link_flair_text": link_flair,
        "extracted_at": now, "updated_at": now,
    }

    with _engine.connect() as conn:
        try:
            if is_sqlite():
                existing = conn.execute(text(f"SELECT 1 FROM {tbl('reddit_posts')} WHERE post_id = :post_id"), {"post_id": post_id}).fetchone()
                if existing:
                    conn.execute(text(
                        f"UPDATE {tbl('reddit_posts')} SET "
                        "score = :score, upvote_ratio = :upvote_ratio, "
                        "num_comments = :num_comments, num_crossposts = :num_crossposts, "
                        "total_awards = :total_awards, engagement_total = :engagement_total, "
                        "updated_at = :updated_at WHERE post_id = :post_id"
                    ), params)
                else:
                    conn.execute(text(
                        f"INSERT INTO {tbl('reddit_posts')} ("
                        "post_id, search_keyword, geo, "
                        "title, selftext, url, permalink, domain, post_hint, "
                        "is_self, is_video, over_18, spoiler, created_utc, thumbnail, "
                        "subreddit, subreddit_id, subreddit_subscribers, "
                        "author, author_fullname, "
                        "score, upvote_ratio, num_comments, num_crossposts, total_awards, "
                        "engagement_total, link_flair_text, extracted_at, updated_at"
                        ") VALUES ("
                        ":post_id, :keyword, :geo, "
                        ":title, :selftext, :url, :permalink, :domain, :post_hint, "
                        ":is_self, :is_video, :over_18, :spoiler, :created_utc, :thumbnail, "
                        ":subreddit, :subreddit_id, :subreddit_subscribers, "
                        ":author, :author_fullname, "
                        ":score, :upvote_ratio, :num_comments, :num_crossposts, :total_awards, "
                        ":engagement_total, :link_flair_text, :extracted_at, :updated_at)"
                    ), params)
            else:
                conn.execute(text(f"""
                    MERGE {tbl('reddit_posts')} AS target
                    USING (SELECT :post_id AS post_id) AS source
                    ON target.post_id = source.post_id
                    WHEN MATCHED THEN UPDATE SET
                        score = :score, upvote_ratio = :upvote_ratio,
                        num_comments = :num_comments, num_crossposts = :num_crossposts,
                        total_awards = :total_awards, engagement_total = :engagement_total,
                        updated_at = :updated_at
                    WHEN NOT MATCHED THEN INSERT (
                        post_id, search_keyword, geo,
                        title, selftext, url, permalink, domain, post_hint,
                        is_self, is_video, over_18, spoiler, created_utc, thumbnail,
                        subreddit, subreddit_id, subreddit_subscribers,
                        author, author_fullname,
                        score, upvote_ratio, num_comments, num_crossposts, total_awards,
                        engagement_total, link_flair_text, extracted_at, updated_at
                    ) VALUES (
                        :post_id, :keyword, :geo,
                        :title, :selftext, :url, :permalink, :domain, :post_hint,
                        :is_self, :is_video, :over_18, :spoiler, :created_utc, :thumbnail,
                        :subreddit, :subreddit_id, :subreddit_subscribers,
                        :author, :author_fullname,
                        :score, :upvote_ratio, :num_comments, :num_crossposts, :total_awards,
                        :engagement_total, :link_flair_text, :extracted_at, :updated_at
                    );
                """), params)
            conn.commit()
            logger.debug("Saved reddit_post id=%s", post_id)
        except Exception:
            logger.error("Failed to save reddit_post id=%s", post_id, exc_info=True)
            raise


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

    _ensure_table()
    client = EDClient(token=token)

    for sub in subreddits:
        try:
            result = client.reddit.subreddit_posts(name=sub, sort=sort, period=period)
            posts = result.data or []
            if isinstance(posts, dict):
                posts = posts.get("posts", []) or posts.get("children", []) or []

            count = 0
            for p in posts[:50]:
                data = p.get("data", p) if isinstance(p, dict) else p
                if not isinstance(data, dict):
                    continue

                # --- save to comprehensive reddit_posts table ---
                try:
                    _save_reddit_post(data, keyword=f"r/{sub}", geo=geo)
                except Exception:
                    logger.error("Failed saving reddit_post detail for r/%s", sub, exc_info=True)

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
                    },
                )
                count += 1

            logger.info("Saved %d posts for r/%s (units charged: %s)", count, sub, result.units_charged)
            if result.units_charged:
                save_token_usage(PLATFORM, sub, result.units_charged, geo)

        except EDError as e:
            save_error(PLATFORM, f"r/{sub}", None, 0, str(e))
            if e.status_code == 495:
                logger.warning("Daily API limit reached. Stopping Reddit scraper.")
                break
            logger.error("Error for r/%s: %s", sub, e, exc_info=True)
        except Exception as e:
            save_error(PLATFORM, f"r/{sub}", None, 0, str(e))
            logger.error("Error for r/%s: %s", sub, e, exc_info=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--subreddits", required=True, help="Comma-separated subreddit names")
    parser.add_argument("--geo", default="Global")
    parser.add_argument("--sort", default="hot")
    parser.add_argument("--period", default="day")
    args = parser.parse_args()
    scrape_reddit([s.strip() for s in args.subreddits.split(",")], geo=args.geo, sort=args.sort, period=args.period)

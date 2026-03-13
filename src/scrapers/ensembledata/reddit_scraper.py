"""Reddit scraper using ensembledata API."""

import os
import sys
from dotenv import load_dotenv
from ensembledata.api import EDClient

sys.path.insert(0, os.path.dirname(__file__))
from db_helper import save_trend, save_error

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

PLATFORM = "Reddit"


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
        print("[reddit] ENSEMBLEDATA_TOKEN not set – skipping.")
        return

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

            print(f"[reddit] Saved {count} posts for r/{sub} (units charged: {result.units_charged})")

        except Exception as e:
            save_error(PLATFORM, f"r/{sub}", None, 0, str(e))
            print(f"[reddit] Error for r/{sub}: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--subreddits", required=True, help="Comma-separated subreddit names")
    parser.add_argument("--geo", default="Global")
    parser.add_argument("--sort", default="hot")
    parser.add_argument("--period", default="day")
    args = parser.parse_args()
    scrape_reddit([s.strip() for s in args.subreddits.split(",")], geo=args.geo, sort=args.sort, period=args.period)

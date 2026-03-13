"""YouTube scraper using ensembledata API."""

import os
import sys
from dotenv import load_dotenv
from ensembledata.api import EDClient

sys.path.insert(0, os.path.dirname(__file__))
from db_helper import save_trend, save_error

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

PLATFORM = "YouTube"


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
        print("[youtube] ENSEMBLEDATA_TOKEN not set – skipping.")
        return

    client = EDClient(token=token)

    for kw in keywords:
        try:
            result = client.youtube.keyword_search(
                keyword=kw, depth=depth, period=period, sorting=sorting,
            )
            items = result.data or []
            if isinstance(items, dict):
                items = items.get("videos", []) or items.get("items", []) or []

            count = 0
            for v in items[:50]:
                title = v.get("title", "")
                views = v.get("viewCount") or v.get("view_count") or v.get("views") or 0
                if isinstance(views, str):
                    views = int(views.replace(",", "").replace(" ", "") or 0)
                topic = title[:120] if title else f"Video {v.get('videoId', '')}"

                video_id = v.get("videoId") or v.get("video_id") or ""
                url = f"https://www.youtube.com/watch?v={video_id}" if video_id else v.get("url", "")
                channel = v.get("channelTitle") or v.get("channel") or ""
                published = v.get("publishedTimeText") or v.get("published") or ""

                save_trend(
                    platform=PLATFORM,
                    topic=topic,
                    growth=int(views),
                    keyword=kw,
                    geo=geo,
                    url=url,
                    extra_data={
                        "video_id": video_id, "channel": channel,
                        "published": published, "views": int(views),
                    },
                )
                count += 1

            print(f"[youtube] Saved {count} videos for '{kw}' (units charged: {result.units_charged})")

        except Exception as e:
            save_error(PLATFORM, kw, None, 0, str(e))
            print(f"[youtube] Error for '{kw}': {e}")


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

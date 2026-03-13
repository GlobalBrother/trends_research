"""TikTok scraper using ensembledata API."""

import os
import sys
from dotenv import load_dotenv
from ensembledata.api import EDClient

sys.path.insert(0, os.path.dirname(__file__))
from db_helper import save_trend, save_error

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

PLATFORM = "TikTok"


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
        print("[tiktok] ENSEMBLEDATA_TOKEN not set – skipping.")
        return

    client = EDClient(token=token)

    for kw in keywords:
        try:
            result = client.tiktok.keyword_search(keyword=kw, period=period)
            videos = result.data or []
            if not isinstance(videos, list):
                videos = videos.get("videos", []) if isinstance(videos, dict) else []

            count = 0
            for v in videos[:50]:
                likes = v.get("like_count") or v.get("diggCount") or 0
                comments = v.get("comment_count") or v.get("commentCount") or 0
                shares = v.get("share_count") or v.get("shareCount") or 0
                views = v.get("view_count") or v.get("playCount") or 0
                engagement = likes + comments + shares

                desc = v.get("video_description") or v.get("desc") or ""
                hashtags = v.get("hashtag_names") or []
                if isinstance(v.get("textExtra"), list):
                    hashtags = [t.get("hashtagName", "") for t in v["textExtra"] if t.get("hashtagName")]
                topic = desc[:120] if desc else ", ".join(hashtags[:5]) if hashtags else f"Video {v.get('id', '')}"

                username = v.get("username") or ""
                if not username and isinstance(v.get("author"), dict):
                    username = v["author"].get("uniqueId", "")
                video_id = str(v.get("id") or v.get("video_id") or "")
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
                )
                count += 1

            print(f"[tiktok] Saved {count} videos for '{kw}' (units charged: {result.units_charged})")

        except Exception as e:
            save_error(PLATFORM, kw, None, 0, str(e))
            print(f"[tiktok] Error for '{kw}': {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords")
    parser.add_argument("--geo", default="Global")
    parser.add_argument("--period", default="30")
    args = parser.parse_args()
    scrape_tiktok([k.strip() for k in args.keywords.split(",")], geo=args.geo, period=args.period)

"""Instagram scraper using ensembledata API."""

import os
import sys
from dotenv import load_dotenv
from ensembledata.api import EDClient

sys.path.insert(0, os.path.dirname(__file__))
from db_helper import save_trend, save_error

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

PLATFORM = "Instagram"


def scrape_instagram(keywords, geo="Global"):
    """Fetch Instagram posts for each keyword via ensembledata."""
    token = os.getenv("ENSEMBLEDATA_TOKEN", "")
    if not token:
        print("[instagram] ENSEMBLEDATA_TOKEN not set – skipping.")
        return

    client = EDClient(token=token)

    for kw in keywords:
        try:
            result = client.instagram.search(text=kw)
            items = result.data or []
            if isinstance(items, dict):
                items = items.get("items", []) or items.get("results", []) or []

            count = 0
            for item in items[:50]:
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
                    },
                )
                count += 1

            print(f"[instagram] Saved {count} posts for '{kw}' (units charged: {result.units_charged})")

        except Exception as e:
            save_error(PLATFORM, kw, None, 0, str(e))
            print(f"[instagram] Error for '{kw}': {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords")
    parser.add_argument("--geo", default="Global")
    args = parser.parse_args()
    scrape_instagram([k.strip() for k in args.keywords.split(",")], geo=args.geo)

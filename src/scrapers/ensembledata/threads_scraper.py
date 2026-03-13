"""Threads scraper using ensembledata API."""

import os
import sys
from dotenv import load_dotenv
from ensembledata.api import EDClient

sys.path.insert(0, os.path.dirname(__file__))
from db_helper import save_trend, save_error

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

PLATFORM = "Threads"


def scrape_threads(keywords, geo="Global"):
    """Fetch Threads posts for each keyword via ensembledata."""
    token = os.getenv("ENSEMBLEDATA_TOKEN", "")
    if not token:
        print("[threads] ENSEMBLEDATA_TOKEN not set – skipping.")
        return

    client = EDClient(token=token)

    for kw in keywords:
        try:
            result = client.threads.search_keyword(name=kw)
            items = result.data or []
            if isinstance(items, dict):
                items = items.get("items", []) or items.get("posts", []) or []

            count = 0
            for item in items[:50]:
                post = item.get("thread_items", [{}])[0] if isinstance(item.get("thread_items"), list) and item["thread_items"] else item
                inner = post.get("post", post)

                caption = ""
                if isinstance(inner.get("caption"), dict):
                    caption = inner["caption"].get("text", "")
                elif isinstance(inner.get("caption"), str):
                    caption = inner["caption"]
                elif inner.get("text_post_app_info", {}).get("share_info", {}).get("quoted_text"):
                    caption = inner["text_post_app_info"]["share_info"]["quoted_text"]

                user = inner.get("user", {}) or {}
                username = user.get("username", "")
                topic = caption[:120] if caption else f"@{username}" if username else "Threads post"

                likes = inner.get("like_count", 0) or 0
                replies = 0
                text_info = inner.get("text_post_app_info", {})
                if isinstance(text_info, dict):
                    replies = text_info.get("direct_reply_count", 0) or 0
                engagement = likes + replies

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
                        "username": username,
                    },
                )
                count += 1

            print(f"[threads] Saved {count} posts for '{kw}' (units charged: {result.units_charged})")

        except Exception as e:
            save_error(PLATFORM, kw, None, 0, str(e))
            print(f"[threads] Error for '{kw}': {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords")
    parser.add_argument("--geo", default="Global")
    args = parser.parse_args()
    scrape_threads([k.strip() for k in args.keywords.split(",")], geo=args.geo)

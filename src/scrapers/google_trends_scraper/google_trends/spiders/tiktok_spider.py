"""
TikTok Research API spider.

Uses the official TikTok Research API v2 (https://developers.tiktok.com/doc/research-api-specs-query-videos/)
to fetch trending videos for given keywords and region.

Auto-fetches an access token via OAuth client_credentials using TIKTOK_CLIENT_KEY
and TIKTOK_CLIENT_SECRET from .env. Alternatively, set TIKTOK_ACCESS_TOKEN directly.
"""

import json
import os
from datetime import datetime, timedelta
from urllib.parse import urlencode

import scrapy

try:
    from ..items import TikTokItem, ScrapeErrorItem
except ImportError:
    from google_trends.items import TikTokItem, ScrapeErrorItem


class TikTokSpider(scrapy.Spider):
    """Fetch TikTok videos via the official Research API."""

    name = "tiktok_trends"
    data_type = "tiktok_trends"

    TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
    QUERY_URL = "https://open.tiktokapis.com/v2/research/video/query/"
    FIELDS = "id,like_count,comment_count,share_count,view_count,create_time,username,video_description,hashtag_names"

    def __init__(self, keywords=None, geo="US", timeframe="today 12-m",
                 category=0, access_token=None, max_count=100,
                 client_key=None, client_secret=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if isinstance(keywords, str):
            self.keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        else:
            self.keywords = keywords or ["Survival", "Health"]
        self.geo = geo
        self.timeframe = timeframe
        self.category = int(category)
        self.max_count = int(max_count)

        self.access_token = access_token or os.getenv("TIKTOK_ACCESS_TOKEN", "")
        self.client_key = client_key or os.getenv("TIKTOK_CLIENT_KEY", "")
        self.client_secret = client_secret or os.getenv("TIKTOK_CLIENT_SECRET", "")

    # ------------------------------------------------------------------ dates
    def _parse_date_range(self):
        """Convert timeframe like 'today 12-m' or 'today 3-m' to (start, end) as YYYYMMDD strings."""
        end = datetime.utcnow()
        tf = self.timeframe.lower().strip()
        if tf.startswith("today"):
            parts = tf.split()
            if len(parts) == 2 and "-" in parts[1]:
                num, unit = parts[1].split("-")
                num = int(num)
                if unit == "m":
                    start = end - timedelta(days=num * 30)
                elif unit == "d":
                    start = end - timedelta(days=num)
                else:
                    start = end - timedelta(days=365)
            else:
                start = end - timedelta(days=365)
        else:
            start = end - timedelta(days=365)
        return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    # -------------------------------------------------------------- requests
    def start_requests(self):
        if not self.access_token:
            if self.client_key and self.client_secret:
                self.logger.info("No access token — fetching via OAuth client_credentials...")
                body = urlencode({
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                })
                yield scrapy.Request(
                    url=self.TOKEN_URL,
                    method="POST",
                    body=body,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Cache-Control": "no-cache",
                    },
                    callback=self.parse_token,
                    errback=self.handle_error,
                    dont_filter=True,
                )
                return
            else:
                self.logger.error(
                    "No TikTok access token and no client_key/client_secret — skipping. "
                    "Set TIKTOK_CLIENT_KEY + TIKTOK_CLIENT_SECRET (or TIKTOK_ACCESS_TOKEN) in .env"
                )
                return

        yield from self._make_video_requests()

    def parse_token(self, response):
        """Handle OAuth token response and proceed to video queries."""
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            self.logger.error("Failed to decode OAuth token response: %s", response.text[:300])
            return

        token = data.get("access_token")
        if not token:
            error_msg = data.get("message") or data.get("error_description") or str(data)
            self.logger.error("OAuth token request failed: %s", error_msg)
            return

        self.access_token = token
        expires_in = data.get("expires_in", "unknown")
        self.logger.info("Got TikTok access token (expires in %s seconds)", expires_in)
        yield from self._make_video_requests()

    def _make_video_requests(self):
        """Generate video query requests for all keywords."""
        start_date, end_date = self._parse_date_range()
        region_codes = [self.geo] if self.geo and self.geo != "Global" else ["US"]

        for kw in self.keywords:
            body = {
                "query": {
                    "and": [
                        {"operation": "IN", "field_name": "region_code", "field_values": region_codes},
                        {"operation": "EQ", "field_name": "keyword", "field_values": [kw]},
                    ]
                },
                "max_count": self.max_count,
                "cursor": 0,
                "start_date": start_date,
                "end_date": end_date,
                "is_random": False,
            }

            url = f"{self.QUERY_URL}?{urlencode({'fields': self.FIELDS})}"
            yield scrapy.Request(
                url=url,
                method="POST",
                body=json.dumps(body),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.access_token}",
                },
                callback=self.parse_videos,
                meta={
                    "keyword": kw,
                    "geo": self.geo,
                    "cursor": 0,
                    "body_template": body,
                },
                errback=self.handle_error,
                dont_filter=True,
            )

    # ----------------------------------------------------------- parse videos
    def parse_videos(self, response):
        keyword = response.meta["keyword"]

        if response.status != 200:
            yield self._record_error(
                keyword=keyword, url=response.url,
                status=response.status,
                reason=f"TikTok API error: {response.text[:500]}",
            )
            return

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            yield self._record_error(
                keyword=keyword, url=response.url,
                status=response.status,
                reason="Failed to decode TikTok API JSON",
            )
            return

        error = data.get("error", {})
        if error.get("code") != "ok" and error.get("code") is not None:
            yield self._record_error(
                keyword=keyword, url=response.url,
                status=response.status,
                reason=f"TikTok API error: {error.get('message', str(error))}",
            )
            return

        videos = data.get("data", {}).get("videos", [])
        results = []
        for v in videos:
            views = v.get("view_count", 0) or 0
            likes = v.get("like_count", 0) or 0
            comments = v.get("comment_count", 0) or 0
            shares = v.get("share_count", 0) or 0
            engagement = likes + comments + shares

            desc = v.get("video_description", "")
            hashtags = v.get("hashtag_names", [])
            topic = desc[:120] if desc else ", ".join(hashtags[:5]) if hashtags else f"Video {v.get('id', '')}"

            create_time = v.get("create_time")
            published = ""
            if create_time:
                try:
                    published = datetime.utcfromtimestamp(int(create_time)).strftime("%Y-%m-%d")
                except (ValueError, TypeError, OSError):
                    published = str(create_time)

            results.append({
                "topic": topic,
                "engagement": engagement,
                "views": views,
                "likes": likes,
                "comments": comments,
                "shares": shares,
                "username": v.get("username", ""),
                "hashtags": hashtags,
                "published": published,
                "video_id": str(v.get("id", "")),
                "url": f"https://www.tiktok.com/@{v.get('username', '')}/video/{v.get('id', '')}",
            })

        if results:
            yield TikTokItem(
                keyword=keyword,
                geo=self.geo,
                time_range=self.timeframe,
                category=self.category,
                data_type=self.data_type,
                results=results,
            )
            self.logger.info("[tiktok] Got %d videos for '%s'", len(results), keyword)

        # Handle pagination
        has_more = data.get("data", {}).get("has_more", False)
        cursor = data.get("data", {}).get("cursor", 0)
        if has_more and cursor:
            body_template = response.meta["body_template"].copy()
            body_template["cursor"] = cursor
            url = f"{self.QUERY_URL}?{urlencode({'fields': self.FIELDS})}"
            yield scrapy.Request(
                url=url,
                method="POST",
                body=json.dumps(body_template),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.access_token}",
                },
                callback=self.parse_videos,
                meta={
                    "keyword": keyword,
                    "geo": self.geo,
                    "cursor": cursor,
                    "body_template": body_template,
                },
                errback=self.handle_error,
                dont_filter=True,
            )

    # ----------------------------------------------------------- error helpers
    def _record_error(self, *, keyword=None, url=None, status=None, reason=None):
        return ScrapeErrorItem(
            platform=self.data_type,
            keyword=keyword,
            url=url,
            status=status,
            reason=reason,
            extracted_at=datetime.now().isoformat(),
        )

    def handle_error(self, failure):
        request = getattr(failure, "request", None)
        response = getattr(failure.value, "response", None)
        meta = getattr(request, "meta", {}) or {}
        yield self._record_error(
            keyword=meta.get("keyword"),
            url=getattr(response, "url", getattr(request, "url", None)),
            status=getattr(response, "status", None),
            reason=failure.getErrorMessage(),
        )
        self.logger.error("TikTok request failed: %s", failure.getErrorMessage())


if __name__ == "__main__":
    from run_spider import run
    run(TikTokSpider)

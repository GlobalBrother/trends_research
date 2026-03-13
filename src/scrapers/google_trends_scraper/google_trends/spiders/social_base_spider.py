"""
Base spider for social media trend discovery via Google Trends API.

Since platforms like Instagram, TikTok, Facebook, X, and Threads block direct
scraping (login walls, JS rendering, CAPTCHAs), we use Google Trends as a proxy
to discover what people are searching for in relation to each platform + niche.

Each platform spider inherits from this base and customises:
  - spider ``name``
  - ``data_type`` stored in the DB
  - ``platform_query_suffix`` appended to each keyword (e.g. "instagram")
"""

import json
import urllib.parse

import scrapy

try:
    from ..items import GoogleTrendItem, ScrapeErrorItem
except ImportError:
    from google_trends.items import GoogleTrendItem, ScrapeErrorItem


class SocialBaseTrendsSpider(scrapy.Spider):
    """Query Google Trends for *keyword + <platform>* related queries."""

    # --- subclass MUST override ---
    name = "social_base"            # overridden by each platform spider
    data_type: str = "social_trends"
    platform_query_suffix: str = ""  # e.g. "instagram", "tiktok"

    allowed_domains = ["trends.google.com"]

    EXPLORE_URL = "https://trends.google.com/trends/api/explore"
    RELATED_QUERIES_URL = "https://trends.google.com/trends/api/widgetdata/relatedsearches"
    INTEREST_OVER_TIME_URL = "https://trends.google.com/trends/api/widgetdata/multiline"

    # ------------------------------------------------------------------ init
    def __init__(self, keywords=None, geo="US", timeframe="today 12-m",
                 category=0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if isinstance(keywords, str):
            self.keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        else:
            self.keywords = keywords or ["Survival", "Health"]
        self.geo = geo
        self.timeframe = timeframe
        self.category = int(category)

    # --------------------------------------------------------- start_requests
    def start_requests(self):
        for kw in self.keywords:
            search_term = f"{kw} {self.platform_query_suffix}".strip()
            payload = {
                "comparisonItem": [{
                    "keyword": search_term,
                    "geo": self.geo if self.geo != "Global" else "",
                    "time": self.timeframe,
                }],
                "category": self.category,
                "property": "",
            }
            params = {
                "hl": "en-US",
                "tz": "-120",
                "req": json.dumps(payload, separators=(",", ":")),
            }
            url = f"{self.EXPLORE_URL}?{urllib.parse.urlencode(params)}"
            yield scrapy.Request(
                url=url,
                callback=self.parse_explore,
                meta={
                    "keyword": kw,
                    "search_term": search_term,
                    "geo": self.geo,
                    "timeframe": self.timeframe,
                    "category": self.category,
                },
                headers={"Referer": "https://trends.google.com/trends/explore"},
                errback=self.handle_error,
            )

    # ----------------------------------------------------------- JSON helper
    @staticmethod
    def _load_google_json(response):
        text = response.text
        if text.startswith(")]}',"):
            text = text[5:]
        elif text.startswith(")]}'"):
            text = text[4:].lstrip("\n")
        return json.loads(text)

    # ----------------------------------------------------------- error helper
    def _record_error(self, *, keyword=None, url=None, status=None, reason=None):
        from datetime import datetime
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
        self.logger.error("Request failed: %s", failure.getErrorMessage())

    # --------------------------------------------------------- parse explore
    def parse_explore(self, response):
        self.logger.info("[%s] Explore response %s for '%s'",
                         self.name, response.status, response.meta.get("search_term"))

        if response.status != 200:
            yield self._record_error(
                keyword=response.meta.get("keyword"),
                url=response.url, status=response.status,
                reason="Non-200 explore response",
            )
            return

        try:
            data = self._load_google_json(response)
        except json.JSONDecodeError:
            yield self._record_error(
                keyword=response.meta.get("keyword"),
                url=response.url, status=response.status,
                reason="Failed to decode explore JSON",
            )
            return

        widgets = data.get("widgets", [])
        for widget in widgets:
            widget_id = widget.get("id", "")
            token = widget.get("token")
            req = widget.get("request")
            if not token or not isinstance(req, dict):
                continue

            meta = {**response.meta, "download_delay": 5.0}

            if "RELATED_QUERIES" in widget_id:
                yield self._fetch_widget(
                    self.RELATED_QUERIES_URL, token, req, meta, "related_queries")

            elif "TIMESERIES" in widget_id:
                yield self._fetch_widget(
                    self.INTEREST_OVER_TIME_URL, token, req, meta, "interest_over_time")

    # --------------------------------------------------------- fetch widget
    def _fetch_widget(self, base_url, token, req, meta, widget_type):
        params = {
            "hl": "en-US",
            "tz": "-120",
            "req": json.dumps(req, separators=(",", ":")),
            "token": token,
        }
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        return scrapy.Request(
            url=url,
            callback=self.parse_widget,
            headers={"Referer": "https://trends.google.com/trends/explore"},
            meta={**meta, "widget_type": widget_type},
            errback=self.handle_error,
        )

    # --------------------------------------------------------- parse widget
    def parse_widget(self, response):
        widget_type = response.meta.get("widget_type", "unknown")
        keyword = response.meta.get("keyword")

        if response.status != 200:
            yield self._record_error(
                keyword=keyword, url=response.url,
                status=response.status,
                reason=f"Non-200 widget response ({widget_type})",
            )
            return

        try:
            data = self._load_google_json(response)
        except json.JSONDecodeError:
            yield self._record_error(
                keyword=keyword, url=response.url,
                status=response.status,
                reason=f"Failed to decode widget JSON ({widget_type})",
            )
            return

        results = []

        if widget_type == "related_queries":
            ranked_list = data.get("default", {}).get("rankedList", [])
            for idx, list_obj in enumerate(ranked_list):
                list_type = "top" if idx == 0 else "rising"
                for item in list_obj.get("rankedKeyword", []):
                    query = item.get("query", "")
                    raw_val = item.get("value")
                    if raw_val == "Breakout":
                        engagement = 5000
                    elif isinstance(raw_val, (int, float)):
                        engagement = int(raw_val) * 10
                    else:
                        engagement = 250
                    results.append({
                        "topic": query,
                        "engagement": engagement,
                        "type": list_type,
                        "url": item.get("link", response.url),
                    })

        elif widget_type == "interest_over_time":
            timeline = data.get("default", {}).get("timelineData", [])
            peak = 0
            for entry in timeline:
                vals = entry.get("value", [0])
                val = vals[0] if isinstance(vals, list) else vals
                if val > peak:
                    peak = val
            if peak > 0:
                results.append({
                    "topic": f"{keyword} (peak interest)",
                    "engagement": peak * 10,
                    "type": "interest",
                    "url": response.url,
                })

        if results:
            yield GoogleTrendItem(
                keyword=keyword,
                geo=self.geo,
                time_range=self.timeframe,
                category=self.category,
                data_type=self.data_type,
                results=results,
            )
        else:
            self.logger.info("[%s] No results for keyword '%s' (%s)",
                             self.name, keyword, widget_type)

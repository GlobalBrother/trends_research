import json
import urllib.parse

import scrapy

try:
    from ..items import GoogleTrendItem, ScrapeErrorItem
except ImportError:
    from google_trends.items import GoogleTrendItem, ScrapeErrorItem


class GoogleTrendsSpider(scrapy.Spider):
    name = "google_trends"
    allowed_domains = ["trends.google.com"]

    EXPLORE_URL = "https://trends.google.com/trends/api/explore"
    INTEREST_OVER_TIME_URL = "https://trends.google.com/trends/api/widgetdata/multiline"
    RELATED_QUERIES_URL = "https://trends.google.com/trends/api/widgetdata/relatedsearches"
    RELATED_TOPICS_URL = "https://trends.google.com/trends/api/widgetdata/relatedtopics"
    INTEREST_BY_REGION_URL = "https://trends.google.com/trends/api/widgetdata/comparedgeo"

    def __init__(self, keywords=None, geo="US", timeframe="today 12-m", category=0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if keywords:
            self.keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        else:
            self.keywords = ["Python", "Scrapy"]

        self.geo = geo
        self.timeframe = timeframe
        self.category = int(category)
        self.failed_items = []

    def start_requests(self):
        """Step 1: Get tokens via /trends/api/explore."""
        for keyword in self.keywords:
            payload = {
                "comparisonItem": [
                    {
                        "keyword": keyword,
                        "geo": self.geo,
                        "time": self.timeframe,
                    }
                ],
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
                    "keywords": self.keywords,
                    "keyword": keyword,
                    "geo": self.geo,
                    "timeframe": self.timeframe,
                    "category": self.category,
                },
                errback=self.handle_error,
            )

    def _record_failed_item(self, *, keyword=None, data_type=None, url=None, reason=None, status=None):
        from datetime import datetime
        return ScrapeErrorItem(
            platform="Google Trends",
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

        if response is not None:
            yield self._record_failed_item(
                keyword=meta.get("keyword"),
                data_type=meta.get("data_type", "explore"),
                url=response.url,
                status=response.status,
                reason=failure.getErrorMessage(),
            )
            self.logger.error(
                "Request failed with response status %s for URL: %s",
                response.status,
                response.url,
            )
        else:
            yield self._record_failed_item(
                keyword=meta.get("keyword"),
                data_type=meta.get("data_type", "explore"),
                url=getattr(request, "url", None),
                reason=failure.getErrorMessage(),
            )
            self.logger.error("Request failed: %s", failure.getErrorMessage())

    def _load_google_json(self, response):
        """
        Google Trends prefixes JSON with )]}'
        Strip it safely before parsing.
        """
        text = response.text
        if text.startswith(")]}',"):
            text = text[5:]
        elif text.startswith(")]}'"):
            text = text[4:].lstrip("\n")
        return json.loads(text)

    def parse_explore(self, response):
        """Parse tokens and trigger widget data requests."""
        self.logger.info("Response code from %s: %s", self.EXPLORE_URL, response.status)

        if response.status != 200:
            yield self._record_failed_item(
                keyword=response.meta.get("keyword"),
                data_type="explore",
                url=response.url,
                status=response.status,
                reason="Non-200 response in explore request",
            )
            self.logger.error("Failed to explore tokens. Status: %s", response.status)
            return

        try:
            data = self._load_google_json(response)
        except json.JSONDecodeError:
            yield self._record_failed_item(
                keyword=response.meta.get("keyword"),
                data_type="explore",
                url=response.url,
                status=response.status,
                reason="Failed to decode explore response JSON",
            )
            self.logger.error("Failed to decode explore response from URL: %s", response.url)
            return

        widgets = data.get("widgets", [])

        for widget in widgets:
            widget_id = widget.get("id", "")
            token = widget.get("token")
            req = widget.get("request")

            if not token or not isinstance(req, dict):
                yield self._record_failed_item(
                    keyword=response.meta.get("keyword"),
                    data_type=widget_id or "unknown_widget",
                    url=response.url,
                    status=response.status,
                    reason="Missing token or invalid widget request payload",
                )
                continue

            # Add a small delay between widget requests to avoid 429
            # Also clear any conflicting cookies or ensure a fresh state if possible
            # For now, just focus on the Referer and delay.
            meta_with_delay = {**response.meta, "download_delay": 5.0}

            if "TIMESERIES" in widget_id:
                yield self.fetch_interest_over_time(token, req, meta_with_delay)

            elif "RELATED_QUERIES" in widget_id:
                # IMPORTANT: Related queries often use 'IZG' or 'ISG' backend.
                # Ensure the request payload is not modified from what Google provided.
                yield self.fetch_related_data(
                    self.RELATED_QUERIES_URL,
                    token,
                    req,
                    meta_with_delay,
                    "related_queries",
                )

            elif "RELATED_TOPICS" in widget_id:
                yield self.fetch_related_data(
                    self.RELATED_TOPICS_URL,
                    token,
                    req,
                    meta_with_delay,
                    "related_topics",
                )

            elif "GEO_MAP" in widget_id:
                yield self.fetch_related_data(
                    self.INTEREST_BY_REGION_URL,
                    token,
                    req,
                    meta_with_delay,
                    "interest_by_region",
                )

    def fetch_interest_over_time(self, token, req, meta):
        params = {
            "hl": "en-US",
            "tz": "-120",
            "req": json.dumps(req, separators=(",", ":")),
            "token": token,
        }
        url = f"{self.INTEREST_OVER_TIME_URL}?{urllib.parse.urlencode(params)}"
        # Add referer to avoid 400
        headers = {'Referer': 'https://trends.google.com/trends/explore'}
        return scrapy.Request(
            url=url,
            callback=self.parse_widget_data,
            headers=headers,
            meta={**meta, "data_type": "interest_over_time"},
            errback=self.handle_error,
        )

    def fetch_related_data(self, base_url, token, req, meta, data_type):
        keyword = (
            req.get("restriction", {})
            .get("complexKeywordsRestriction", {})
            .get("keyword", [{}])[0]
            .get("value")
        ) or meta.get("keyword")

        params = {
            "hl": "en-US",
            "tz": "-120",
            "req": json.dumps(req, separators=(",", ":")),
            "token": token,
        }
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        # Add referer to avoid 400
        headers = {'Referer': 'https://trends.google.com/trends/explore'}

        return scrapy.Request(
            url=url,
            callback=self.parse_widget_data,
            headers=headers,
            meta={**meta, "data_type": data_type, "keyword": keyword},
            errback=self.handle_error,
        )

    def parse_widget_data(self, response):
        data_type = response.meta.get("data_type", "unknown")
        self.logger.info(
            "Response code from %s...: %s (Type: %s)",
            response.url[:60],
            response.status,
            data_type,
        )

        if response.status != 200:
            yield self._record_failed_item(
                keyword=response.meta.get("keyword"),
                data_type=data_type,
                url=response.url,
                status=response.status,
                reason="Non-200 response in widget request",
            )
            self.logger.error("Widget request failed. Status: %s URL: %s", response.status, response.url)
            return

        try:
            data = self._load_google_json(response)
        except json.JSONDecodeError:
            yield self._record_failed_item(
                keyword=response.meta.get("keyword"),
                data_type=data_type,
                url=response.url,
                status=response.status,
                reason="Failed to decode widget response JSON",
            )
            self.logger.error("Failed to decode widget response from URL: %s", response.url)
            return

        results = []

        if data_type == "interest_over_time":
            timeline_data = data.get("default", {}).get("timelineData", [])
            for entry in timeline_data:
                results.append(
                    {
                        "time": entry.get("formattedTime"),
                        "value": entry.get("value"),
                        "isPartial": entry.get("isPartial", False),
                    }
                )
        elif data_type == "interest_by_region":
            geo_data = data.get("default", {}).get("geoMapData", [])
            for entry in geo_data:
                results.append(
                    {
                        "geoName": entry.get("geoName"),
                        "geoCode": entry.get("geoCode"),
                        "value": entry.get("value"),
                        "maxValueIndex": entry.get("maxValueIndex"),
                    }
                )
        else:
            ranked_list = data.get("default", {}).get("rankedList", [])
            for index, list_obj in enumerate(ranked_list):
                list_type = "top" if index == 0 else "rising"
                for item in list_obj.get("rankedKeyword", []):
                    results.append(
                        {
                            "query": item.get("query"),
                            "topic": item.get("topic"),
                            "value": item.get("value"),
                            "link": item.get("link"),
                            "type": list_type,
                        }
                    )

        yield GoogleTrendItem(
            keyword=response.meta.get("keyword") or ", ".join(self.keywords),
            geo=response.meta.get("geo", self.geo),
            time_range=response.meta.get("timeframe", self.timeframe),
            category=response.meta.get("category", self.category),
            data_type=data_type,
            results=results,
        )

    def closed(self, reason):
        if not self.failed_items:
            self.logger.info("Spider closed (%s). No failed items were recorded.", reason)
            return

        self.logger.warning(
            "Spider closed (%s). Failed to scrape %s item(s).",
            reason,
            len(self.failed_items),
        )

        for index, item in enumerate(self.failed_items, start=1):
            self.logger.warning(
                "Failed item #%s | keyword=%s | data_type=%s | status=%s | reason=%s | url=%s",
                index,
                item.get("keyword"),
                item.get("data_type"),
                item.get("status"),
                item.get("reason"),
                item.get("url"),
            )


if __name__ == "__main__":
    from run_spider import run
    run(GoogleTrendsSpider)

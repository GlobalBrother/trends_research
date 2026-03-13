import json
import urllib.parse

import scrapy

try:
    from ..items import TokenImportItem, ScrapeErrorItem
except ImportError:
    from google_trends.items import TokenImportItem, ScrapeErrorItem


class TokenImportSpider(scrapy.Spider):
    """
    Spider that accepts pre-parsed widget tokens (from a manually downloaded
    Google Trends JSON file) and fetches widget data directly, bypassing the
    explore step that is often blocked by 429 rate limits.
    """

    name = "token_import"
    allowed_domains = ["trends.google.com"]

    INTEREST_OVER_TIME_URL = "https://trends.google.com/trends/api/widgetdata/multiline"
    RELATED_QUERIES_URL = "https://trends.google.com/trends/api/widgetdata/relatedsearches"
    RELATED_TOPICS_URL = "https://trends.google.com/trends/api/widgetdata/relatedtopics"
    INTEREST_BY_REGION_URL = "https://trends.google.com/trends/api/widgetdata/comparedgeo"

    def __init__(self, widgets_json=None, geo="US", keyword=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.widgets = json.loads(widgets_json) if widgets_json else []
        self.geo = geo
        self.keyword = keyword or "Unknown"
        self.failed_items = []

    def start_requests(self):
        for widget in self.widgets:
            widget_id = widget.get("id", "")
            token = widget.get("token")
            req = widget.get("request")

            if not token or not isinstance(req, dict):
                continue

            meta = {
                "keyword": self.keyword,
                "geo": self.geo,
                "download_delay": 5.0,
            }

            if "TIMESERIES" in widget_id:
                yield self._build_request(
                    self.INTEREST_OVER_TIME_URL, token, req, meta, "interest_over_time"
                )
            elif "RELATED_QUERIES" in widget_id:
                yield self._build_request(
                    self.RELATED_QUERIES_URL, token, req, meta, "related_queries"
                )
            elif "RELATED_TOPICS" in widget_id:
                yield self._build_request(
                    self.RELATED_TOPICS_URL, token, req, meta, "related_topics"
                )
            elif "GEO_MAP" in widget_id:
                yield self._build_request(
                    self.INTEREST_BY_REGION_URL, token, req, meta, "interest_by_region"
                )

    def _build_request(self, base_url, token, req, meta, data_type):
        params = {
            "hl": "en-US",
            "tz": "-120",
            "req": json.dumps(req, separators=(",", ":")),
            "token": token,
        }
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        headers = {"Referer": "https://trends.google.com/trends/explore"}
        return scrapy.Request(
            url=url,
            callback=self.parse_widget_data,
            headers=headers,
            meta={**meta, "data_type": data_type},
            errback=self.handle_error,
        )

    def handle_error(self, failure):
        from datetime import datetime

        request = getattr(failure, "request", None)
        response = getattr(failure.value, "response", None)
        meta = getattr(request, "meta", {}) or {}
        status = response.status if response else None
        url = response.url if response else getattr(request, "url", None)

        yield ScrapeErrorItem(
            platform="Google Trends (Token Import)",
            keyword=meta.get("keyword"),
            url=url,
            status=status,
            reason=failure.getErrorMessage(),
            extracted_at=datetime.now().isoformat(),
        )
        self.logger.error("Token import request failed: %s", failure.getErrorMessage())

    def _load_google_json(self, response):
        text = response.text
        if text.startswith(")]}',"):
            text = text[5:]
        elif text.startswith(")]}'"):
            text = text[4:].lstrip("\n")
        return json.loads(text)

    def parse_widget_data(self, response):
        data_type = response.meta.get("data_type", "unknown")
        self.logger.info(
            "Token import response from %s...: %s (Type: %s)",
            response.url[:60], response.status, data_type,
        )

        if response.status != 200:
            from datetime import datetime

            yield ScrapeErrorItem(
                platform="Google Trends (Token Import)",
                keyword=response.meta.get("keyword"),
                url=response.url,
                status=response.status,
                reason="Non-200 response in token import widget request",
                extracted_at=datetime.now().isoformat(),
            )
            return

        try:
            data = self._load_google_json(response)
        except json.JSONDecodeError:
            self.logger.error("Failed to decode widget response: %s", response.url)
            return

        results = []

        if data_type == "interest_over_time":
            for entry in data.get("default", {}).get("timelineData", []):
                results.append({
                    "time": entry.get("formattedTime"),
                    "value": entry.get("value"),
                    "isPartial": entry.get("isPartial", False),
                })
        elif data_type == "interest_by_region":
            for entry in data.get("default", {}).get("geoMapData", []):
                results.append({
                    "geoName": entry.get("geoName"),
                    "geoCode": entry.get("geoCode"),
                    "value": entry.get("value"),
                    "maxValueIndex": entry.get("maxValueIndex"),
                })
        else:
            for index, list_obj in enumerate(data.get("default", {}).get("rankedList", [])):
                list_type = "top" if index == 0 else "rising"
                for item in list_obj.get("rankedKeyword", []):
                    results.append({
                        "query": item.get("query"),
                        "topic": item.get("topic"),
                        "value": item.get("value"),
                        "link": item.get("link"),
                        "type": list_type,
                    })

        yield TokenImportItem(
            keyword=response.meta.get("keyword", self.keyword),
            geo=response.meta.get("geo", self.geo),
            time_range="today 12-m",
            category=0,
            data_type=data_type,
            results=results,
        )


if __name__ == "__main__":
    from run_spider import run
    run(TokenImportSpider)

import random
import os
import sys
import datetime
from scrapy.exceptions import IgnoreRequest
from sqlalchemy import text

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.db.connection import get_engine

class SkipRecentlyScrapedMiddleware:
    def __init__(self, hours):
        self.engine = get_engine()
        self.hours = hours

    @classmethod
    def from_crawler(cls, crawler):
        hours = crawler.settings.getint('SCRAPE_FRESHNESS_HOURS', 24)
        return cls(hours)

    def process_request(self, request, spider):
        # Identify the platform and identifier
        platform = spider.name
        url = request.url
        
        # Determine the keyword/geo identifier if possible
        kw_id = None
        # Check meta first (best source)
        if 'keyword' in request.meta:
            kw = str(request.meta['keyword'])
            geo = request.meta.get('geo', 'Global')
            kw_id = f"{kw}_{geo}"
        elif hasattr(spider, 'keywords') and spider.keywords:
            geo = getattr(spider, 'geo', 'Global')
            if isinstance(spider.keywords, list):
                if len(spider.keywords) == 1:
                    kw_id = f"{spider.keywords[0]}_{geo}"
            elif isinstance(spider.keywords, str):
                kw_id = f"{spider.keywords}_{geo}"

        # Check URL first
        if self._is_recently_scraped(platform, url):
            spider.logger.info(f"Skipping recently scraped URL: {url}")
            raise IgnoreRequest(f"URL recently scraped: {url}")
            
        # Check keyword identifier if available
        if kw_id and self._is_recently_scraped(platform, kw_id):
            spider.logger.info(f"Skipping recently scraped keyword: {kw_id}")
            raise IgnoreRequest(f"Keyword recently scraped: {kw_id}")

    def _is_recently_scraped(self, platform, identifier):
        try:
            since = (datetime.datetime.now() - datetime.timedelta(hours=self.hours)).isoformat()
            
            # Using platform names as they appear in the log (usually capitalized in pipelines)
            # We'll check both the spider name and the formatted name
            platform_variants = [platform.lower(), platform.capitalize(), platform.title()]
            if platform == 'google_trends':
                platform_variants.append('Google Trends')
            elif platform == 'reddit':
                platform_variants.append('Reddit')

            # Ensure we have exactly 4 variants
            while len(platform_variants) < 4:
                platform_variants.append(platform)

            with self.engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT 1 FROM scrape_log "
                        "WHERE platform IN (:p0, :p1, :p2, :p3) "
                        "AND identifier = :identifier "
                        "AND status IN (200, 301) AND extracted_at > :since"
                    ),
                    {
                        "p0": platform_variants[0], "p1": platform_variants[1],
                        "p2": platform_variants[2], "p3": platform_variants[3],
                        "identifier": str(identifier).strip(), "since": since,
                    },
                ).fetchone()
            return row is not None
        except Exception:
            return False

class RandomUserAgentMiddleware:
    def __init__(self, user_agents):
        self.user_agents = user_agents or []
        self.selected_user_agent = random.choice(self.user_agents) if self.user_agents else None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(user_agents=crawler.settings.get('USER_AGENTS'))

    def process_request(self, request, spider):
        if self.selected_user_agent:
            request.headers.setdefault('User-Agent', self.selected_user_agent)


class ProxyMiddleware:
    def __init__(self, proxy_list):
        self.proxy_list = proxy_list or []
        self.proxy_index = 0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(proxy_list=crawler.settings.get('PROXY_LIST'))

    def process_request(self, request, spider):
        if self.proxy_list:
            proxy = self.proxy_list[self.proxy_index]
            self.proxy_index = (self.proxy_index + 1) % len(self.proxy_list)
            request.meta['proxy'] = proxy
            request.meta.setdefault('cookiejar', proxy)
        else:
            request.meta.setdefault('cookiejar', 'default')

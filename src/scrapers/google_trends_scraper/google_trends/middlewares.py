import random
import sqlite3
import os
import datetime
from scrapy.exceptions import IgnoreRequest

class SkipRecentlyScrapedMiddleware:
    def __init__(self, db_path, hours):
        self.db_path = db_path
        self.hours = hours

    @classmethod
    def from_crawler(cls, crawler):
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'collector', 'trends.db'))
        hours = crawler.settings.getint('SCRAPE_FRESHNESS_HOURS', 24)
        return cls(db_path, hours)

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
        if not os.path.exists(self.db_path):
            return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            clean_id = str(identifier).strip()
            since = (datetime.datetime.now() - datetime.timedelta(hours=self.hours)).isoformat()
            
            # Using platform names as they appear in the log (usually capitalized in pipelines)
            # We'll check both the spider name and the formatted name
            platform_variants = [platform.lower(), platform.capitalize(), platform.title()]
            if platform == 'google_trends':
                platform_variants.append('Google Trends')
            elif platform == 'reddit':
                platform_variants.append('Reddit')

            query = '''
                SELECT 1 FROM scrape_log 
                WHERE platform IN (?, ?, ?, ?) AND identifier = ? AND status IN (200, 301) AND extracted_at > ?
            '''
            params = platform_variants[:4] + [clean_id, since]
            # Ensure we have 4 platform variants for the IN clause
            while len(params) < 6:
                params.insert(0, platform)

            cursor.execute(query, params)
            result = cursor.fetchone()
            conn.close()
            return result is not None
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
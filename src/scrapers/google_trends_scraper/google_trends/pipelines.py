import json
import sqlite3
import os
import datetime
from .items import ScrapeErrorItem

class GoogleTrendsPipeline:
    def process_item(self, item, spider):
        item['extracted_at'] = datetime.datetime.now().isoformat()
        return item

class JSONLPipeline:
    def open_spider(self, spider):
        self.file = open('trends_output.jsonl', 'a', encoding='utf-8')

    def close_spider(self, spider):
        self.file.close()

    def process_item(self, item, spider):
        line = json.dumps(dict(item)) + "\n"
        self.file.write(line)
        return item

class SQLitePipeline:
    def __init__(self, db_path):
        self.db_path = db_path

    @classmethod
    def from_crawler(cls, crawler):
        # Path relative to scrapy.cfg or project root
        # Since we run from src/scrapers/google_trends_scraper, we go up to src/collector
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'collector', 'trends.db'))
        return cls(db_path=db_path)

    def open_spider(self, spider):
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self._create_table()

    def _create_table(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT,
                topic TEXT,
                growth REAL,
                keyword TEXT,
                geo TEXT,
                url TEXT,
                extracted_at DATETIME,
                extra_data TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS scrape_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT,
                keyword TEXT,
                url TEXT,
                status INTEGER,
                reason TEXT,
                extracted_at DATETIME
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS scrape_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT,
                identifier TEXT,
                status INTEGER,
                extracted_at DATETIME
            )
        """)
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_platform ON trends(platform)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_keyword ON trends(keyword)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_geo ON trends(geo)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_at ON trends(extracted_at)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_error_platform ON scrape_errors(platform)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_error_extracted_at ON scrape_errors(extracted_at)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_platform_id ON scrape_log(platform, identifier)")
        self.conn.commit()

    def is_recently_scraped(self, platform, identifier, hours=24):
        """Checks if the identifier was scraped for the platform in the last X hours."""
        since = (datetime.datetime.now() - datetime.timedelta(hours=hours)).isoformat()
        self.cursor.execute('''
            SELECT 1 FROM scrape_log 
            WHERE platform = ? AND identifier = ? AND status IN (200, 301) AND extracted_at > ?
            LIMIT 1
        ''', (platform, identifier, since))
        return self.cursor.fetchone() is not None

    def close_spider(self, spider):
        self.conn.close()

    def _parse_traffic(self, traffic_str):
        if not traffic_str or not isinstance(traffic_str, str):
            return None
        try:
            traffic_str = traffic_str.replace('+', '').replace(',', '')
            if 'K' in traffic_str:
                return int(float(traffic_str.replace('K', '')) * 1000)
            if 'M' in traffic_str:
                return int(float(traffic_str.replace('M', '')) * 1000000)
            return int(traffic_str)
        except:
            return None

    def _parse_views(self, views_str):
        import re
        if not views_str or not isinstance(views_str, str):
            return None
        try:
            match = re.search(r'([\d.,]+)\s*([KM]?)', views_str.upper())
            if match:
                num_str = match.group(1).replace(',', '')
                multiplier = match.group(2)
                val = float(num_str)
                if multiplier == 'K':
                    return int(val * 1000)
                if multiplier == 'M':
                    return int(val * 1000000)
                return int(val)
            return None
        except:
            return None

    def process_item(self, item, spider):
        if isinstance(item, ScrapeErrorItem):
            self.cursor.execute('''
                INSERT INTO scrape_errors (platform, keyword, url, status, reason, extracted_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (item.get('platform'), item.get('keyword'), item.get('url'), item.get('status'), item.get('reason'), item.get('extracted_at')))
            self.conn.commit()
            return item

        data_type = item.get('data_type')
        keyword = item.get('keyword', 'Unknown')
        geo = item.get('geo', '')
        extracted_at = item.get('extracted_at')
        results = item.get('results', [])

        for res in results:
            platform = None
            topic = None
            growth = 0
            url = res.get('url')
            extra_data = {}

            if data_type == 'trending_searches':
                platform = "Google Trends"
                topic = res.get('query') or res.get('title')
                growth = self._parse_traffic(res.get('traffic')) or 500
            elif data_type in ['related_queries', 'related_topics']:
                platform = f"Google {data_type.replace('_', ' ').title()}"
                topic = res.get('query') or res.get('topic')
                val = res.get('value')
                if val == 'Breakout':
                    growth = 5000
                elif isinstance(val, (int, float)):
                    growth = val * 10
                else:
                    growth = 250
            elif data_type == 'youtube_trends':
                platform = "YouTube"
                topic = res.get('title')
                growth = self._parse_views(res.get('views')) or 0
                extra_data['published'] = res.get('published')
                extra_data['video_id'] = res.get('video_id')
            elif data_type in ['x_trends', 'threads_trends', 'instagram_trends']:
                platform_map = {'x_trends': 'X (Twitter)', 'threads_trends': 'Threads', 'instagram_trends': 'Instagram'}
                platform = platform_map.get(data_type)
                topic = res.get('topic')
                growth = res.get('engagement', 0)
                extra_data['posts'] = res.get('posts')
                extra_data['replies'] = res.get('replies')
            elif data_type == 'hackernews_trends':
                platform = "HackerNews"
                topic = res.get('title')
                growth = res.get('score', 0) * 10
                extra_data['engagement'] = res.get('descendants', 0) * 5
                extra_data['author'] = res.get('by')
            elif data_type == 'reddit_trends':
                platform = "Reddit"
                topic = res.get('title')
                growth = res.get('score', 0) * 5
                extra_data['engagement'] = res.get('num_comments', 0) * 10
                extra_data['subreddit'] = res.get('subreddit')
            elif data_type == 'news_trends':
                platform = "News"
                topic = res.get('title')
                growth = res.get('popularity', 50) * 10
                extra_data['source'] = res.get('source')
            elif data_type == 'interest_over_time':
                platform = "Google Interest"
                topic = item.get('keyword')
                # For interest over time, we use the peak interest as growth
                if results:
                    growth = max([r.get('value', [0])[0] if isinstance(r.get('value'), list) else r.get('value', 0) for r in results])
                else:
                    growth = 0
                extra_data['time_series'] = results
            elif data_type == 'interest_by_region':
                platform = "Google Regions"
                topic = item.get('keyword')
                regions = [r for r in results if (r.get('value', [0])[0] if isinstance(r.get('value'), list) else r.get('value', 0)) > 0]
                for r in regions:
                    reg_topic = f"{topic} in {r.get('geoName')}"
                    reg_growth = r.get('value', [0])[0] if isinstance(r.get('value'), list) else r.get('value', 0)
                    reg_extra = {
                        'geoCode': r.get('geoCode'),
                        'geoName': r.get('geoName'),
                        'region_value': reg_growth
                    }
                    self.cursor.execute('''
                        INSERT INTO trends (platform, topic, growth, keyword, geo, url, extracted_at, extra_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (platform, reg_topic, reg_growth, keyword, geo, url, extracted_at, json.dumps(reg_extra)))
                
                # We skip the default insert for Google Regions since we added per-region rows
                continue

            if platform and topic:
                self.cursor.execute('''
                    INSERT INTO trends (platform, topic, growth, keyword, geo, url, extracted_at, extra_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (platform, topic, growth, keyword, geo, url, extracted_at, json.dumps(extra_data)))
                
                # Also log the successful scrape by URL if it exists
                if url:
                    self.cursor.execute('''
                        INSERT OR REPLACE INTO scrape_log (platform, identifier, status, extracted_at)
                        VALUES (?, ?, ?, ?)
                    ''', (platform, url, 200, extracted_at))

                # Also log the successful scrape by keyword_geo for broader skipping
                identifier = f"{keyword}_{geo}" if geo else keyword
                self.cursor.execute('''
                    INSERT OR REPLACE INTO scrape_log (platform, identifier, status, extracted_at)
                    VALUES (?, ?, ?, ?)
                ''', (platform, identifier, 200, extracted_at))
        
        self.conn.commit()
        return item

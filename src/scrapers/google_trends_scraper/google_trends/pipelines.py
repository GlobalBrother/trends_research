import json
import sqlite3
import os
from datetime import datetime

class GoogleTrendsPipeline:
    def process_item(self, item, spider):
        item['extracted_at'] = datetime.now().isoformat()
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
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_platform ON trends(platform)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_keyword ON trends(keyword)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_geo ON trends(geo)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_at ON trends(extracted_at)")
        self.conn.commit()

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
            elif data_type == 'interest_by_region':
                platform = "Google Regions"
                topic = item.get('keyword')
                regions = [r for r in results if r.get('value', [0])[0] > 0]
                growth = len(regions) * 10
                extra_data['spread'] = len(regions)

            if platform and topic:
                self.cursor.execute('''
                    INSERT INTO trends (platform, topic, growth, keyword, geo, url, extracted_at, extra_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (platform, topic, growth, keyword, geo, url, extracted_at, json.dumps(extra_data)))
        
        self.conn.commit()
        return item

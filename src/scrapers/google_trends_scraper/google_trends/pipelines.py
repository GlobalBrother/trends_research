import json
import os
import sys
import datetime

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.db.connection import get_session
from src.db.models import Trend, ScrapeError, ScrapeLog
from src.db.sql_compat import (
    is_duplicate_trend, upsert_scrape_log, get_platform_id,
)

from .items import (
    BaseItem, GoogleTrendsItem, TrendingNowItem,
    SocialMediaItem, HackerNewsItem,
    NewsItem, TokenImportItem, ScrapeErrorItem,
)

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
    """Pipeline that writes to the database via SQLAlchemy ORM."""

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def is_recently_scraped(self, platform, identifier, hours=24):
        """Checks if the identifier was scraped for the platform in the last X hours."""
        since = datetime.datetime.now() - datetime.timedelta(hours=hours)
        session = get_session()
        try:
            row = session.query(ScrapeLog).filter(
                ScrapeLog.platform == platform,
                ScrapeLog.identifier == identifier,
                ScrapeLog.status.in_([200, 301]),
                ScrapeLog.extracted_at > since.isoformat(),
            ).first()
            return row is not None
        finally:
            session.close()

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
        session = get_session()
        try:
            if isinstance(item, ScrapeErrorItem):
                session.add(ScrapeError(
                    platform=item.get('platform'), keyword=item.get('keyword'),
                    url=item.get('url'), status=item.get('status'),
                    reason=item.get('reason'), extracted_at=item.get('extracted_at'),
                ))
                session.commit()
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
                    extra_data['channel'] = res.get('channel')
                    extra_data['duration'] = res.get('duration')
                    extra_data['description'] = res.get('description')
                elif data_type in ['threads_trends', 'instagram_trends', 'tiktok_trends']:
                    platform_map = {'threads_trends': 'Threads', 'instagram_trends': 'Instagram', 'tiktok_trends': 'TikTok'}
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
                        platform_id = get_platform_id(session, platform)
                        if not is_duplicate_trend(session, platform_id, reg_topic, keyword, geo):
                            session.add(Trend(
                                platform_id=platform_id, topic=reg_topic, growth=reg_growth,
                                keyword=keyword, geo=geo, extracted_at=extracted_at,
                                extra_data=json.dumps(reg_extra),
                            ))
                    
                    # We skip the default insert for Google Regions since we added per-region rows
                    continue

                if platform and topic:
                    platform_id = get_platform_id(session, platform)
                    if is_duplicate_trend(session, platform_id, topic, keyword, geo):
                        continue
                    # Merge url into extra_data (url column removed from trends table)
                    if url:
                        extra_data['url'] = url
                    session.add(Trend(
                        platform_id=platform_id, topic=topic, growth=growth,
                        keyword=keyword, geo=geo, extracted_at=extracted_at,
                        extra_data=json.dumps(extra_data),
                    ))
                    
                    # Also log the successful scrape by URL if it exists
                    if url:
                        upsert_scrape_log(session, platform, url, 200, extracted_at)

                    # Also log the successful scrape by keyword_geo for broader skipping
                    identifier = f"{keyword}_{geo}" if geo else keyword
                    upsert_scrape_log(session, platform, identifier, 200, extracted_at)
            
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        return item

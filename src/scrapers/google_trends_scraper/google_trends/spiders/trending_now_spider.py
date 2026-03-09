import scrapy
import json
import urllib.parse
from datetime import datetime
from ..items import GoogleTrendItem

class TrendingNowSpider(scrapy.Spider):
    name = "trending_now"
    allowed_domains = ["trends.google.com"]
    
    TRENDING_NOW_URL = "https://trends.google.com/trends/api/realtimetrends"
    DAILY_TRENDS_URL = "https://trends.google.com/trends/api/dailytrends"
    
    def __init__(self, geo='US', type='daily', *args, **kwargs):
        super(TrendingNowSpider, self).__init__(*args, **kwargs)
        self.geo = geo
        self.type = type # 'daily' or 'realtime'

    def start_requests(self):
        if self.type == 'realtime':
            params = {
                "hl": "en-US",
                "tz": "-120",
                "ni": 10,
                "cat": "all",
                "fi": 0,
                "fs": 0,
                "geo": self.geo,
                "ri": 300,
                "rs": 20,
                "sort": 0
            }
            url = f"{self.TRENDING_NOW_URL}?{urllib.parse.urlencode(params)}"
        else:
            params = {
                "hl": "en-US",
                "tz": "-120",
                "geo": self.geo,
                "ns": 15
            }
            url = f"{self.DAILY_TRENDS_URL}?{urllib.parse.urlencode(params)}"
            
        yield scrapy.Request(url=url, callback=self.parse)

    def parse(self, response):
        raw_data = response.text[5:]
        data = json.loads(raw_data)
        
        results = []
        if self.type == 'realtime':
            trending_stories = data.get('trendingStoryList', [])
            for story in trending_stories:
                results.append({
                    'title': story.get('title'),
                    'articles': [a.get('title') for a in story.get('articles', [])],
                    'entity_names': [e.get('name') for e in story.get('entityNames', [])]
                })
        else:
            days = data.get('default', {}).get('trendingSearchesDays', [])
            for day in days:
                date = day.get('date')
                for search in day.get('trendingSearches', []):
                    results.append({
                        'date': date,
                        'query': search.get('title', {}).get('query'),
                        'traffic': search.get('formattedTraffic'),
                        'related_queries': [q.get('query') for q in search.get('relatedQueries', [])]
                    })

        yield GoogleTrendItem(
            keyword=f"Trending {self.type.capitalize()}",
            geo=self.geo,
            time_range="current",
            category=0,
            data_type="trending_searches",
            results=results
        )

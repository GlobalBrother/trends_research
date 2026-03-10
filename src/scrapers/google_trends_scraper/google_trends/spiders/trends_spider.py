import scrapy
import json
import urllib.parse
from datetime import datetime
from ..items import GoogleTrendItem

class GoogleTrendsSpider(scrapy.Spider):
    name = "google_trends"
    allowed_domains = ["trends.google.com"]
    
    # Internal endpoints
    EXPLORE_URL = "https://trends.google.com/trends/api/explore"
    INTEREST_OVER_TIME_URL = "https://trends.google.com/trends/api/widgetdata/multiline"
    RELATED_QUERIES_URL = "https://trends.google.com/trends/api/widgetdata/relatedsearches"
    
    def __init__(self, keywords=None, geo='US', timeframe='today 12-m', category=0, *args, **kwargs):
        super(GoogleTrendsSpider, self).__init__(*args, **kwargs)
        if keywords:
            self.keywords = [k.strip() for k in keywords.split(',')]
        else:
            self.keywords = ["Python", "Scrapy"] # Default keywords
        
        self.geo = geo
        self.timeframe = timeframe
        self.category = category

    def start_requests(self):
        """Step 1: Get tokens via /trends/api/explore"""
        # Google expects a specific comparisonItem structure
        comparison_items = []
        for kw in self.keywords:
            comparison_items.append({
                'keyword': kw,
                'geo': self.geo,
                'time': self.timeframe
            })
            
        payload = {
            "comparisonItem": comparison_items,
            "category": self.category,
            "property": ""
        }
        
        params = {
            "hl": "en-US",
            "tz": "-120", # Offset
            "req": json.dumps(payload)
        }
        
        url = f"{self.EXPLORE_URL}?{urllib.parse.urlencode(params)}"
        
        yield scrapy.Request(
            url=url,
            callback=self.parse_explore,
            meta={'keywords': self.keywords, 'geo': self.geo, 'timeframe': self.timeframe, 'category': self.category},
            errback=self.handle_error
        )

    def handle_error(self, failure):
        response = failure.value.response
        if response:
            self.logger.error(f"Request failed with response status: {response.status} for URL: {response.url}")
        else:
            self.logger.error(f"Request failed: {failure.getErrorMessage()}")

    def parse_explore(self, response):
        """Parse tokens and trigger widget data requests"""
        self.logger.info(f"Response code from {self.EXPLORE_URL}: {response.status}")
        
        if response.status != 200:
            self.logger.error(f"Failed to explore tokens. Status: {response.status}")
            return

        # Google Trends API prepends ")]}'\n" to prevent JSON hijacking
        raw_data = response.text[5:]
        data = json.loads(raw_data)
        
        widgets = data.get('widgets', [])
        
        for widget in widgets:
            widget_id = widget.get('id')
            token = widget.get('token')
            req = widget.get('request')
            
            # 1. Interest Over Time
            if widget_id == 'TIMESERIES':
                yield self.fetch_interest_over_time(token, req, response.meta)
            
            # 2. Related Queries (one per keyword usually)
            elif 'RELATED_QUERIES' in widget_id:
                yield self.fetch_related_data(self.RELATED_QUERIES_URL, token, req, response.meta, 'related_queries')
                
            # 3. Related Topics
            elif 'RELATED_TOPICS' in widget_id:
                yield self.fetch_related_data(self.RELATED_QUERIES_URL.replace('relatedsearches', 'relatedtopics'), 
                                              token, req, response.meta, 'related_topics')

    def fetch_interest_over_time(self, token, req, meta):
        params = {
            "hl": "en-US",
            "tz": "-120",
            "req": json.dumps(req),
            "token": token,
            "tz": "-120"
        }
        url = f"{self.INTEREST_OVER_TIME_URL}?{urllib.parse.urlencode(params)}"
        return scrapy.Request(
            url=url,
            callback=self.parse_widget_data,
            meta={**meta, 'data_type': 'interest_over_time'},
            errback=self.handle_error
        )

    def fetch_related_data(self, base_url, token, req, meta, data_type):
        params = {
            "hl": "en-US",
            "tz": "-120",
            "req": json.dumps(req),
            "token": token
        }
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        return scrapy.Request(
            url=url,
            callback=self.parse_widget_data,
            meta={**meta, 'data_type': data_type, 'keyword': req.get('restriction', {}).get('complexKeywordsRestriction', {}).get('keyword', [{}])[0].get('value')},
            errback=self.handle_error
        )

    def parse_widget_data(self, response):
        data_type = response.meta['data_type']
        self.logger.info(f"Response code from {response.url[:60]}...: {response.status} (Type: {data_type})")
        raw_data = response.text[5:]
        data = json.loads(raw_data)
        
        results = []
        if data_type == 'interest_over_time':
            # Extraction of timeline data
            timeline_data = data.get('default', {}).get('timelineData', [])
            for entry in timeline_data:
                results.append({
                    'time': entry.get('formattedTime'),
                    'value': entry.get('value'),
                    'isPartial': entry.get('isPartial', False)
                })
        else:
            # Extraction of related queries/topics
            ranked_list = data.get('default', {}).get('rankedList', [])
            for list_obj in ranked_list:
                list_type = 'top' if ranked_list.index(list_obj) == 0 else 'rising'
                for item in list_obj.get('rankedKeyword', []):
                    results.append({
                        'query': item.get('query'),
                        'topic': item.get('topic'),
                        'value': item.get('value'),
                        'link': item.get('link'),
                        'type': list_type
                    })

        yield GoogleTrendItem(
            keyword=response.meta.get('keyword') or ", ".join(self.keywords),
            geo=response.meta['geo'],
            time_range=response.meta['timeframe'],
            category=response.meta['category'],
            data_type=data_type,
            results=results
        )

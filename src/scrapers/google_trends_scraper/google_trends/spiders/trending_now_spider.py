import scrapy
import json
import urllib.parse
from datetime import datetime
try:
    from ..items import TrendingNowItem
except ImportError:
    from google_trends.items import TrendingNowItem

class TrendingNowSpider(scrapy.Spider):
    name = "trending_now"
    allowed_domains = ["trends.google.com"]
    
    RSS_URL = "https://trends.google.com/trending/rss"
    
    def __init__(self, geo='US', type='daily', *args, **kwargs):
        super(TrendingNowSpider, self).__init__(*args, **kwargs)
        self.geo = geo
        self.type = type # 'daily' (realtime not supported via RSS)

    def start_requests(self):
        params = {"geo": self.geo}
        url = f"{self.RSS_URL}?{urllib.parse.urlencode(params)}"
        yield scrapy.Request(url=url, callback=self.parse)

    def parse(self, response):
        self.logger.info(f"Parsing RSS feed from {response.url}")
        
        # Define namespaces for XPath
        namespaces = {'ht': 'https://trends.google.com/trending/rss'}
        
        # Scrapy's Selector handles XML/RSS well
        items = response.xpath('//item')
        results = []
        
        for item in items:
            query = item.xpath('./title/text()').get()
            traffic = item.xpath('./ht:approx_traffic/text()', namespaces=namespaces).get()
            pub_date = item.xpath('./pubDate/text()').get()
            
            # Get news items
            news_items = item.xpath('./ht:news_item', namespaces=namespaces)
            articles = []
            for ni in news_items:
                title = ni.xpath('./ht:news_item_title/text()', namespaces=namespaces).get()
                if title:
                    articles.append(title)
            
            results.append({
                'date': pub_date,
                'query': query,
                'traffic': traffic,
                'articles': articles
            })

        yield TrendingNowItem(
            keyword=f"Trending {self.type.capitalize()}",
            geo=self.geo,
            time_range="current",
            category=0,
            data_type="trending_searches",
            results=results
        )


if __name__ == "__main__":
    from run_spider import run
    run(TrendingNowSpider)

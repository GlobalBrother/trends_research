import scrapy
from datetime import datetime
from ..items import GoogleTrendItem

class StackExchangeSpider(scrapy.Spider):
    name = "stackexchange"
    allowed_domains = ["api.stackexchange.com"]
    
    # Endpoints: /questions?sort=hot
    
    def __init__(self, site='stackoverflow', sort='hot', *args, **kwargs):
        super(StackExchangeSpider, self).__init__(*args, **kwargs)
        self.site = site
        self.sort = sort
        self.url = f"https://api.stackexchange.com/2.3/questions?order=desc&sort={sort}&site={site}"

    def start_requests(self):
        yield scrapy.Request(self.url, callback=self.parse)

    def parse(self, response):
        data = response.json()
        items = data.get('items', [])
        
        results = []
        # Limit to top 10 items as requested
        for item in items[:10]:
            results.append({
                'title': item.get('title'),
                'tags': item.get('tags', []),
                'score': item.get('score', 0),
                'view_count': item.get('view_count', 0),
                'answer_count': item.get('answer_count', 0),
                'url': item.get('link'),
                'is_answered': item.get('is_answered')
            })

        yield GoogleTrendItem(
            keyword=self.site,
            geo="Global",
            time_range=self.sort,
            category=0,
            data_type="stackexchange_trends",
            results=results,
            extracted_at=datetime.now().isoformat()
        )

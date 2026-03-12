import scrapy
from datetime import datetime
from ..items import GoogleTrendItem

class StackExchangeSpider(scrapy.Spider):
    name = "stackexchange"
    allowed_domains = ["api.stackexchange.com"]
    
    # Endpoints: /questions?sort=hot
    
    def __init__(self, site='stackoverflow', sort='hot', keywords=None, *args, **kwargs):
        super(StackExchangeSpider, self).__init__(*args, **kwargs)
        self.site = site
        self.sort = sort
        if isinstance(keywords, str):
            self.keywords = keywords.split(',')
        else:
            self.keywords = keywords

    def start_requests(self):
        if self.keywords:
            for kw in self.keywords:
                # Use advanced search with 'q' for general keywords
                url = f"https://api.stackexchange.com/2.3/search/advanced?order=desc&sort={self.sort}&q={kw}&site={self.site}"
                yield scrapy.Request(url, callback=self.parse, meta={'keyword': kw})
        else:
            url = f"https://api.stackexchange.com/2.3/questions?order=desc&sort={self.sort}&site={self.site}"
            yield scrapy.Request(url, callback=self.parse, meta={'keyword': self.site})

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
            keyword=response.meta.get('keyword', self.site),
            geo="Global",
            time_range=self.sort,
            category=0,
            data_type="stackexchange_trends",
            results=results,
            extracted_at=datetime.now().isoformat()
        )

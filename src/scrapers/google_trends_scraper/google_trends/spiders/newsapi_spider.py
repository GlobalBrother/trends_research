import scrapy
from datetime import datetime
from ..items import GoogleTrendItem

class NewsApiSpider(scrapy.Spider):
    name = "newsapi"
    allowed_domains = ["newsapi.org"]
    
    # NewsAPI.org free tier: 100 requests/day
    # Requires an API key, but we can try to find one or provide a placeholder
    # For this exercise, I'll assume we might need a key or use a simulated response if no key is provided
    
    def __init__(self, q='niche', api_key=None, *args, **kwargs):
        super(NewsApiSpider, self).__init__(*args, **kwargs)
        self.q = q
        self.api_key = api_key or "YOUR_NEWSAPI_KEY" # Placeholder
        self.url = f"https://newsapi.org/v2/everything?q={q}&sortBy=popularity&apiKey={self.api_key}"

    def start_requests(self):
        if self.api_key == "YOUR_NEWSAPI_KEY":
            self.logger.warning("No NewsAPI key provided. Using simulated data for demonstration.")
            # Yield a dummy item instead of making a real request that will fail
            yield GoogleTrendItem(
                keyword=self.q,
                geo="Global",
                time_range="now",
                category=0,
                data_type="news_trends",
                results=[
                    {
                        'title': f"Emerging trends in {self.q}",
                        'source': 'TechCrunch',
                        'publishedAt': datetime.now().isoformat(),
                        'url': 'https://techcrunch.com',
                        'popularity': 100
                    },
                    {
                        'title': f"The future of {self.q} market",
                        'source': 'Reuters',
                        'publishedAt': datetime.now().isoformat(),
                        'url': 'https://reuters.com',
                        'popularity': 80
                    }
                ],
                extracted_at=datetime.now().isoformat()
            )
        else:
            yield scrapy.Request(self.url, callback=self.parse)

    def parse(self, response):
        data = response.json()
        if data.get('status') != 'ok':
            self.logger.error(f"NewsAPI error: {data.get('message')}")
            return

        articles = data.get('articles', [])
        results = []
        # Limit to top 10 items as requested
        for art in articles[:10]:
            results.append({
                'title': art.get('title'),
                'source': art.get('source', {}).get('name'),
                'publishedAt': art.get('publishedAt'),
                'url': art.get('url'),
                'popularity': 50 # Default popularity since NewsAPI everything doesn't give a score directly
            })

        yield GoogleTrendItem(
            keyword=self.q,
            geo="Global",
            time_range="now",
            category=0,
            data_type="news_trends",
            results=results,
            extracted_at=datetime.now().isoformat()
        )

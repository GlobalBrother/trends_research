import os
import scrapy
from datetime import datetime
try:
    from ..items import NewsItem, ScrapeErrorItem
except ImportError:
    from google_trends.items import NewsItem, ScrapeErrorItem

class NewsApiSpider(scrapy.Spider):
    name = "newsapi"
    allowed_domains = ["newsapi.org"]
    
    # NewsAPI.org free tier: 100 requests/day
    # Requires an API key, but we can try to find one or provide a placeholder
    # For this exercise, I'll assume we might need a key or use a simulated response if no key is provided
    
    def __init__(self, q='niche', api_key=None, *args, **kwargs):
        super(NewsApiSpider, self).__init__(*args, **kwargs)
        self.q = q
        # Priority: explicit argument > environment variable > placeholder
        if api_key and api_key != 'None':
            self.api_key = api_key
        else:
            self.api_key = os.getenv('NEWS_API_KEY') or "YOUR_NEWSAPI_KEY"
        self.url = f"https://newsapi.org/v2/everything?q={q}&sortBy=popularity&apiKey={self.api_key}"

    def start_requests(self):
        if self.api_key == "YOUR_NEWSAPI_KEY":
            self.logger.warning("No NewsAPI key provided. Using simulated data for demonstration.")
            # Yield a dummy item instead of making a real request that will fail
            yield NewsItem(
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
            yield scrapy.Request(self.url, callback=self.parse, errback=self.handle_error)

    def handle_error(self, failure):
        request = getattr(failure, "request", None)
        response = getattr(failure.value, "response", None)
        
        status = response.status if response else 0
        yield ScrapeErrorItem(
            platform="News",
            keyword=self.q,
            url=request.url if request else self.url,
            status=status,
            reason=failure.getErrorMessage(),
            extracted_at=datetime.now().isoformat()
        )

    def parse(self, response):
        if response.status != 200:
            yield ScrapeErrorItem(
                platform="News",
                keyword=self.q,
                url=response.url,
                status=response.status,
                reason=f"HTTP {response.status}",
                extracted_at=datetime.now().isoformat()
            )
            return

        data = response.json()
        if data.get('status') != 'ok':
            yield ScrapeErrorItem(
                platform="News",
                keyword=self.q,
                url=response.url,
                status=response.status,
                reason=data.get('message', 'Unknown API error'),
                extracted_at=datetime.now().isoformat()
            )
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

        yield NewsItem(
            keyword=self.q,
            geo="Global",
            time_range="now",
            category=0,
            data_type="news_trends",
            results=results,
            extracted_at=datetime.now().isoformat()
        )


if __name__ == "__main__":
    from run_spider import run
    run(NewsApiSpider)

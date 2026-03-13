import scrapy
from datetime import datetime
try:
    from ..items import RedditItem, ScrapeErrorItem
except ImportError:
    from google_trends.items import RedditItem, ScrapeErrorItem

class RedditSpider(scrapy.Spider):
    name = "reddit"
    allowed_domains = ["www.reddit.com"]
    
    # We'll fetch the JSON feed for top-level subreddits or r/all
    # Reddit's API can be accessed via .json on many URLs for basic info
    # Note: For production, using 'praw' (Python Reddit API Wrapper) is better
    # but as a Scrapy spider, we can fetch JSON directly for a simple free-tier approach.
    
    def __init__(self, subreddit='all', trend_type='hot', keywords=None, *args, **kwargs):
        super(RedditSpider, self).__init__(*args, **kwargs)
        self.subreddit = subreddit
        self.trend_type = trend_type # 'hot', 'new', 'rising', 'top'
        
        if isinstance(keywords, str):
            self.keywords = keywords.split(',')
        else:
            self.keywords = keywords

    def start_requests(self):
        # We need a User-Agent to avoid being blocked by Reddit
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 TrendDiscoveryBot/0.1'
        }
        
        if self.keywords:
            for kw in self.keywords:
                # Search across all of Reddit for the keyword
                search_url = f"https://www.reddit.com/search.json?q={kw}&sort={self.trend_type}"
                yield scrapy.Request(
                    search_url, 
                    headers=headers, 
                    callback=self.parse, 
                    dont_filter=True, 
                    meta={'proxy': None, 'keyword': kw},
                    errback=self.handle_error
                )
        else:
            base_url = f"https://www.reddit.com/r/{self.subreddit}/{self.trend_type}.json"
            yield scrapy.Request(
                base_url, 
                headers=headers, 
                callback=self.parse, 
                dont_filter=True, 
                meta={'proxy': None, 'keyword': f"r/{self.subreddit}"},
                errback=self.handle_error
            )

    def handle_error(self, failure):
        request = getattr(failure, "request", None)
        response = getattr(failure.value, "response", None)
        meta = getattr(request, "meta", {}) or {}
        
        status = response.status if response else 0
        yield ScrapeErrorItem(
            platform="Reddit",
            keyword=meta.get('keyword'),
            url=request.url if request else None,
            status=status,
            reason=failure.getErrorMessage(),
            extracted_at=datetime.now().isoformat()
        )

    def parse(self, response):
        if response.status != 200:
            yield ScrapeErrorItem(
                platform="Reddit",
                keyword=response.meta.get('keyword'),
                url=response.url,
                status=response.status,
                reason=f"Non-200 response: {response.status}",
                extracted_at=datetime.now().isoformat()
            )
            self.logger.error(f"Failed to fetch Reddit data: {response.status} for {response.url}")
            return

        data = response.json()
        posts = data.get('data', {}).get('children', [])
        
        results = []
        # Limit to top 10 items as requested
        for post in posts[:10]:
            pdata = post.get('data', {})
            results.append({
                'title': pdata.get('title'),
                'subreddit': pdata.get('subreddit'),
                'score': pdata.get('score', 0),
                'num_comments': pdata.get('num_comments', 0),
                'url': f"https://www.reddit.com{pdata.get('permalink')}",
                'upvote_ratio': pdata.get('upvote_ratio', 0),
                'created_utc': pdata.get('created_utc')
            })

        yield RedditItem(
            keyword=response.meta.get('keyword', f"r/{self.subreddit}"),
            geo="Global",
            time_range=self.trend_type,
            category=0,
            data_type="reddit_trends",
            results=results,
            extracted_at=datetime.now().isoformat()
        )


if __name__ == "__main__":
    from run_spider import run
    run(RedditSpider)

import scrapy
from datetime import datetime
from ..items import GoogleTrendItem

class RedditSpider(scrapy.Spider):
    name = "reddit"
    allowed_domains = ["www.reddit.com"]
    
    # We'll fetch the JSON feed for top-level subreddits or r/all
    # Reddit's API can be accessed via .json on many URLs for basic info
    # Note: For production, using 'praw' (Python Reddit API Wrapper) is better
    # but as a Scrapy spider, we can fetch JSON directly for a simple free-tier approach.
    
    def __init__(self, subreddit='all', trend_type='hot', *args, **kwargs):
        super(RedditSpider, self).__init__(*args, **kwargs)
        self.subreddit = subreddit
        self.trend_type = trend_type # 'hot', 'new', 'rising', 'top'
        self.base_url = f"https://www.reddit.com/r/{self.subreddit}/{self.trend_type}.json"

    def start_requests(self):
        # We need a User-Agent to avoid being blocked by Reddit
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 TrendDiscoveryBot/0.1'
        }
        # bypass_middlewares=True or similar isn't a thing in scrapy by default, 
        # but we can set meta to tell our middlewares to skip if we had such logic.
        # For now, let's just try to set it directly and hope the middleware doesn't overwrite if it's already there.
        # In Scrapy, process_request usually setdefault, so it shouldn't overwrite.
        yield scrapy.Request(self.base_url, headers=headers, callback=self.parse, dont_filter=True, meta={'proxy': None})

    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch Reddit data: {response.status}")
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

        yield GoogleTrendItem(
            keyword=f"r/{self.subreddit}",
            geo="Global",
            time_range=self.trend_type,
            category=0,
            data_type="reddit_trends",
            results=results,
            extracted_at=datetime.now().isoformat()
        )

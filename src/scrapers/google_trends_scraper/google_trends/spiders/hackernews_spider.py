import scrapy
from ..items import GoogleTrendItem

class HackerNewsSpider(scrapy.Spider):
    name = "hackernews"
    allowed_domains = ["hacker-news.firebaseio.com"]
    
    TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
    ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"

    def start_requests(self):
        yield scrapy.Request(self.TOP_STORIES_URL, callback=self.parse_top_stories)

    def parse_top_stories(self, response):
        story_ids = response.json()
        # Limit to top 10 stories as requested
        for story_id in story_ids[:10]:
            yield scrapy.Request(self.ITEM_URL.format(story_id), callback=self.parse_story)

    def parse_story(self, response):
        story = response.json()
        if not story or story.get('type') != 'story':
            return

        # Map HN story to GoogleTrendItem for compatibility
        # We'll use score as a proxy for growth/engagement
        yield GoogleTrendItem(
            keyword="HackerNews Top",
            geo="Global",
            time_range="current",
            category=0,
            data_type="hackernews_trends",
            results=[{
                'title': story.get('title'),
                'score': story.get('score'),
                'url': story.get('url'),
                'by': story.get('by'),
                'descendants': story.get('descendants', 0) # number of comments
            }]
        )

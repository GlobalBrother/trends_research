import scrapy
from ..items import GoogleTrendItem

class HackerNewsSpider(scrapy.Spider):
    name = "hackernews"
    allowed_domains = ["hacker-news.firebaseio.com", "hn.algolia.com"]
    
    TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
    ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"
    SEARCH_URL = "https://hn.algolia.com/api/v1/search?query={}&tags=story"

    def __init__(self, keywords=None, *args, **kwargs):
        super(HackerNewsSpider, self).__init__(*args, **kwargs)
        if isinstance(keywords, str):
            self.keywords = keywords.split(',')
        else:
            self.keywords = keywords

    def start_requests(self):
        if self.keywords:
            for kw in self.keywords:
                yield scrapy.Request(self.SEARCH_URL.format(kw), callback=self.parse_search_results, meta={'keyword': kw})
        else:
            yield scrapy.Request(self.TOP_STORIES_URL, callback=self.parse_top_stories)

    def parse_top_stories(self, response):
        story_ids = response.json()
        # Limit to top 10 stories as requested
        for story_id in story_ids[:10]:
            yield scrapy.Request(self.ITEM_URL.format(story_id), callback=self.parse_story)

    def parse_search_results(self, response):
        data = response.json()
        hits = data.get('hits', [])
        # Limit to top 10 as requested
        for hit in hits[:10]:
            yield GoogleTrendItem(
                keyword=response.meta.get('keyword', "HackerNews Search"),
                geo="Global",
                time_range="current",
                category=0,
                data_type="hackernews_trends",
                results=[{
                    'title': hit.get('title'),
                    'score': hit.get('points'),
                    'url': hit.get('url') or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                    'by': hit.get('author'),
                    'descendants': hit.get('num_comments', 0)
                }]
            )

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

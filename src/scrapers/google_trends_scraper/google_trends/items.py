import scrapy


class BaseItem(scrapy.Item):
    """Base item with fields common to all scrapers."""
    keyword = scrapy.Field()
    geo = scrapy.Field()
    time_range = scrapy.Field()
    category = scrapy.Field()
    data_type = scrapy.Field()
    results = scrapy.Field()
    extracted_at = scrapy.Field()


# Keep GoogleTrendItem as an alias for backward compatibility
GoogleTrendItem = BaseItem


class GoogleTrendsItem(BaseItem):
    """Item for Google Trends spider (interest over time, related queries/topics, regions)."""
    pass


class TrendingNowItem(BaseItem):
    """Item for Google Trending Now / Daily Trends spider."""
    pass


class YouTubeItem(BaseItem):
    """Item for YouTube trends spider."""
    pass


class SocialMediaItem(BaseItem):
    """Item for social media spiders (X, Threads, Instagram, TikTok, Facebook)."""
    platform_name = scrapy.Field()


class TikTokItem(SocialMediaItem):
    """Item for TikTok Research API spider."""
    access_token_used = scrapy.Field()


class HackerNewsItem(BaseItem):
    """Item for Hacker News spider."""
    pass


class RedditItem(BaseItem):
    """Item for Reddit spider."""
    subreddit = scrapy.Field()


class NewsItem(BaseItem):
    """Item for News API spider."""
    query = scrapy.Field()


class TokenImportItem(BaseItem):
    """Item for token import spider (manually downloaded Google Trends JSON)."""
    widget_id = scrapy.Field()


class ScrapeErrorItem(scrapy.Item):
    platform = scrapy.Field()
    keyword = scrapy.Field()
    url = scrapy.Field()
    status = scrapy.Field()
    reason = scrapy.Field()
    extracted_at = scrapy.Field()

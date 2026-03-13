from .social_base_spider import SocialBaseTrendsSpider


class TikTokSpider(SocialBaseTrendsSpider):
    """Discover TikTok-related trends via Google Trends API."""

    name = "tiktok_trends"
    data_type = "tiktok_trends"
    platform_query_suffix = "tiktok"

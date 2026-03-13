from .social_base_spider import SocialBaseTrendsSpider


class InstagramSpider(SocialBaseTrendsSpider):
    """Discover Instagram-related trends via Google Trends API."""

    name = "instagram_trends"
    data_type = "instagram_trends"
    platform_query_suffix = "instagram"

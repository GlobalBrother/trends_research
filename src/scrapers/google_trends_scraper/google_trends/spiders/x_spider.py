from .social_base_spider import SocialBaseTrendsSpider


class XSpider(SocialBaseTrendsSpider):
    """Discover X (Twitter)-related trends via Google Trends API."""

    name = "x_trends"
    data_type = "x_trends"
    platform_query_suffix = "twitter"

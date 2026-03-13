try:
    from .social_base_spider import SocialBaseTrendsSpider
except ImportError:
    from social_base_spider import SocialBaseTrendsSpider


class ThreadsSpider(SocialBaseTrendsSpider):
    """Discover Threads-related trends via Google Trends API."""

    name = "threads_trends"
    data_type = "threads_trends"
    platform_query_suffix = "threads"


if __name__ == "__main__":
    from run_spider import run
    run(ThreadsSpider)

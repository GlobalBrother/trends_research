"""
Shared utility to run any spider standalone.

Usage from within a spider file:
    if __name__ == "__main__":
        from run_spider import run
        run(MySpiderClass)

Or directly from the command line:
    python run_spider.py <spider_module> [--keywords kw1,kw2] [--geo US] [...]
"""
import argparse
import os
import sys


def run(spider_cls, **default_kwargs):
    """Run a spider class standalone using CrawlerProcess with project settings."""
    # Ensure the scrapy project root is on sys.path so settings resolve
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    os.environ.setdefault('SCRAPY_SETTINGS_MODULE', 'google_trends.settings')

    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings

    settings = get_project_settings()
    process = CrawlerProcess(settings)

    # Parse CLI arguments: any --key value pair becomes a spider kwarg
    parser = argparse.ArgumentParser(description=f"Run {spider_cls.name} spider standalone")
    parser.add_argument('--keywords', type=str, default=default_kwargs.get('keywords'), help='Comma-separated keywords')
    parser.add_argument('--geo', type=str, default=default_kwargs.get('geo', 'US'), help='Geo code (e.g. US, GB)')
    parser.add_argument('--timeframe', type=str, default=default_kwargs.get('timeframe', 'today 12-m'), help='Timeframe')
    parser.add_argument('--category', type=int, default=default_kwargs.get('category', 0), help='Category ID')
    # Extra args used by specific spiders
    parser.add_argument('--type', type=str, default=default_kwargs.get('type'), dest='trend_type', help='Trend type (e.g. daily, realtime)')
    parser.add_argument('--platform', type=str, default=default_kwargs.get('platform'), help='Platform name')
    parser.add_argument('--subreddit', type=str, default=default_kwargs.get('subreddit', 'all'), help='Subreddit name')
    parser.add_argument('--trend_type', type=str, default=default_kwargs.get('trend_type', 'hot'), dest='reddit_trend_type', help='Reddit trend type')
    parser.add_argument('--query', type=str, default=default_kwargs.get('query'), help='Search query (NewsAPI)')
    parser.add_argument('--api_key', type=str, default=default_kwargs.get('api_key'), help='API key (NewsAPI)')
    parser.add_argument('--widgets_json', type=str, default=default_kwargs.get('widgets_json'), help='Widgets JSON string (token import)')
    parser.add_argument('--keyword', type=str, default=default_kwargs.get('keyword'), help='Single keyword (token import)')

    args = parser.parse_args()

    # Build spider kwargs from parsed args, only passing non-None values
    spider_kwargs = {}
    for key, val in vars(args).items():
        if val is not None:
            spider_kwargs[key] = val

    # Rename reddit_trend_type back to trend_type for reddit spider
    if 'reddit_trend_type' in spider_kwargs:
        spider_kwargs['trend_type'] = spider_kwargs.pop('reddit_trend_type')
    if 'trend_type' in spider_kwargs and spider_kwargs['trend_type'] is None:
        del spider_kwargs['trend_type']

    process.crawl(spider_cls, **spider_kwargs)
    process.start()

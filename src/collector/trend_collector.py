import os
import pandas as pd
import json
import subprocess
import sys
import re

# Ensembledata scrapers
try:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scrapers", "ensembledata")))
    from tiktok_scraper import scrape_tiktok
    from instagram_scraper import scrape_instagram
    from youtube_scraper import scrape_youtube
    from reddit_scraper import scrape_reddit
    from threads_scraper import scrape_threads
    HAS_ENSEMBLEDATA = True
except ImportError:
    HAS_ENSEMBLEDATA = False

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import func
from src.db.connection import get_session
from src.db.models import Trend, Platform, ScrapeError


class TrendCollector:
    def __init__(self):
        pass
        
    def get_db_trends(self, geo=None, include_trending_now=False, include_youtube=False, include_social=False, include_hackernews=False, include_reddit=False, include_news=False):
        """Reads trends from the database."""
        try:
            # Platform filtering
            included_platforms = []
            if include_trending_now:
                included_platforms.append('Google Trends')
            if include_youtube:
                included_platforms.append('YouTube')
            if include_social:
                included_platforms.extend(['Threads', 'Instagram', 'TikTok'])
            if include_hackernews:
                included_platforms.append('HackerNews')
            if include_reddit:
                included_platforms.append('Reddit')
            if include_news:
                included_platforms.append('News')
            
            # Always include Google niche platforms
            always_included = ['Google Interest', 'Google Regions', 'Google Related Queries', 'Google Related Topics']
            included_platforms.extend(always_included)

            session = get_session()
            try:
                query = session.query(
                    Platform.name.label('platform'),
                    Trend.topic, Trend.growth, Trend.keyword,
                    Trend.geo, Trend.extracted_at, Trend.extra_data,
                ).join(Platform, Platform.id == Trend.platform_id).filter(
                    Platform.name.in_(included_platforms),
                )

                # Geo filtering
                if geo is not None and geo != "Global":
                    query = query.filter(
                        (func.upper(Trend.geo) == func.upper(geo)) |
                        (Trend.geo == '') |
                        (func.upper(Trend.geo) == 'GLOBAL') |
                        (Trend.geo.is_(None))
                    )
                elif geo == "Global":
                    query = query.filter(
                        (func.upper(Trend.geo) == 'GLOBAL') |
                        (Trend.geo == '') |
                        (Trend.geo.is_(None))
                    )

                query = query.order_by(Trend.extracted_at.desc())
                rows = query.all()
            finally:
                session.close()

            trends = []
            for row in rows:
                item = {
                    "platform": row.platform,
                    "topic": row.topic,
                    "growth": row.growth,
                    "keyword": row.keyword,
                    "geo": row.geo,
                    "extracted_at": row.extracted_at,
                }
                
                # Expand extra_data
                if row.extra_data:
                    try:
                        extra = json.loads(row.extra_data)
                        item.update(extra)
                    except:
                        pass
                
                trends.append(item)
                
            return trends
        except Exception as e:
            print(f"Error reading trends from DB: {e}")
            return []

    def run_google_trends_scraper(self, keywords, geo="US", timeframe="today 12-m", category=0):
        """Runs the Scrapy Google Trends spider for specific keywords."""
        return self._run_scraper("google_trends", keywords=keywords, geo=geo, timeframe=timeframe, category=category)

    def run_trending_now_scraper(self, geo="US", trend_type="daily"):
        """Runs the Scrapy Trending Now spider."""
        return self._run_scraper("trending_now", geo=geo, type=trend_type)

    def _run_scraper(self, spider_name, **kwargs):
        """Helper to run a Scrapy spider with given arguments."""
        # Use absolute path for the scraper directory
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        project_dir = os.path.join(base_dir, "src", "scrapers", "google_trends_scraper")
        
        cmd = [sys.executable, "-m", "scrapy", "crawl", spider_name]
        
        for key, value in kwargs.items():
            if key == "keywords" and isinstance(value, list):
                value = ",".join(value)
            cmd.extend(["-a", f"{key}={value}"])

        try:
            print(f"Running scraper command: {' '.join(cmd)} in {project_dir}")
            
            result = subprocess.run(
                cmd,
                cwd=project_dir,
                capture_output=False,
                text=True
            )
            
            if result.returncode != 0:
                print(f"Scraper {spider_name} failed with return code {result.returncode}")
                return False
            
            print(f"Scraper {spider_name} completed successfully.")
            return True
        except Exception as e:
            print(f"Failed to run Scrapy scraper {spider_name}: {e}")
            return False

    def run_youtube_trends_scraper(self, keywords, geo="Global"):
        """Runs the YouTube scraper via ensembledata."""
        if not HAS_ENSEMBLEDATA or not os.getenv("ENSEMBLEDATA_TOKEN"):
            print("[youtube] ensembledata not available – skipping.")
            return False
        kw_list = keywords if isinstance(keywords, list) else [k.strip() for k in keywords.split(",")]
        scrape_youtube(kw_list, geo=geo)
        return True

    def run_social_trends_scraper(self, platform, keywords, geo="Global"):
        """Runs the social media scraper via ensembledata."""
        kw_list = keywords if isinstance(keywords, list) else [k.strip() for k in keywords.split(",")]
        if HAS_ENSEMBLEDATA and os.getenv("ENSEMBLEDATA_TOKEN"):
            scraper_map = {
                "TikTok": lambda: scrape_tiktok(kw_list, geo=geo),
                "Instagram": lambda: scrape_instagram(kw_list, geo=geo),
                "Threads": lambda: scrape_threads(kw_list, geo=geo),
            }
            fn = scraper_map.get(platform)
            if fn:
                fn()
                return True
        if platform in ("TikTok", "Instagram", "Threads"):
            print(f"[{platform.lower()}] ensembledata not available – skipping.")
            return False
        print(f"Unknown social platform: {platform}")
        return False

    def run_hackernews_scraper(self, keywords=None, geo="Global"):
        """Runs the Scrapy HackerNews spider."""
        return self._run_scraper("hackernews", keywords=keywords, geo=geo)

    def run_reddit_scraper(self, subreddit='all', trend_type='hot', keywords=None, geo="Global"):
        """Runs the Reddit scraper via ensembledata."""
        if not HAS_ENSEMBLEDATA or not os.getenv("ENSEMBLEDATA_TOKEN"):
            print("[reddit] ensembledata not available – skipping.")
            return False
        subs = [subreddit] if isinstance(subreddit, str) else subreddit
        scrape_reddit(subs, geo=geo, sort=trend_type)
        return True

    def run_news_scraper(self, query='niche', api_key=None, geo="Global"):
        """Runs the Scrapy NewsAPI spider."""
        return self._run_scraper("newsapi", q=query, api_key=api_key, geo=geo)

    def run_token_import(self, widgets_json, geo="US", keyword="Unknown"):
        """Runs the token import spider with pre-parsed widget tokens from a downloaded JSON file."""
        return self._run_scraper("token_import", widgets_json=widgets_json, geo=geo, keyword=keyword)

    def run_niche_comprehensive_scrape(self, niche_name, keywords, geo="US", timeframe="today 12-m", category=0):
        """Triggers all scrapers for a specific niche in sequence."""
        print(f"Starting comprehensive scrape for niche: {niche_name}")
        
        # 1. Google Trends (the core scraper) - Use ALL keywords
        self.run_google_trends_scraper(keywords, geo=geo, timeframe=timeframe, category=category)
        
        # 2. YouTube - Use ALL keywords
        self.run_youtube_trends_scraper(keywords, geo=geo)
        
        # 3. Social - Use ALL keywords
        self.run_social_trends_scraper("Threads", keywords, geo=geo)
        self.run_social_trends_scraper("Instagram", keywords, geo=geo)
        self.run_social_trends_scraper("TikTok", keywords, geo=geo)
        
        # 4. Reddit - Use ALL keywords
        self.run_reddit_scraper(keywords=keywords, geo=geo)
        
        # 5. HackerNews - Use ALL keywords
        self.run_hackernews_scraper(keywords=keywords, geo=geo)
        
        # 6. NewsAPI (just use the niche name for NewsAPI)
        self.run_news_scraper(query=niche_name, geo=geo)
        
        print(f"Comprehensive scrape for {niche_name} finished.")
        return True

    def collect_all(self, geo=None, include_trending_now=False, include_youtube=False, include_social=False, include_hackernews=False, include_reddit=False, include_news=False):
        all_trends = []
        # Prefer DB over JSONL
        all_trends.extend(self.get_db_trends(geo=geo, include_trending_now=include_trending_now, include_youtube=include_youtube, include_social=include_social, include_hackernews=include_hackernews, include_reddit=include_reddit, include_news=include_news))
        
        if all_trends:
            return pd.DataFrame(all_trends)
        else:
            # Return empty DataFrame with expected columns
            return pd.DataFrame(columns=['platform', 'topic', 'growth', 'keyword', 'extracted_at'])

    def get_scrape_errors(self, platform=None):
        """Reads scrape errors from the database."""
        try:
            session = get_session()
            try:
                query = session.query(
                    ScrapeError.platform, ScrapeError.keyword,
                    ScrapeError.url, ScrapeError.status,
                    ScrapeError.reason, ScrapeError.extracted_at,
                )
                if platform:
                    query = query.filter(ScrapeError.platform == platform)
                query = query.order_by(ScrapeError.extracted_at.desc())
                rows = query.all()
            finally:
                session.close()

            if rows:
                return pd.DataFrame(rows, columns=['platform', 'keyword', 'url', 'status', 'reason', 'extracted_at'])
            return pd.DataFrame(columns=['platform', 'keyword', 'url', 'status', 'reason', 'extracted_at'])
        except Exception as e:
            print(f"Error reading scrape errors from DB: {e}")
            return pd.DataFrame(columns=['platform', 'keyword', 'url', 'status', 'reason', 'extracted_at'])

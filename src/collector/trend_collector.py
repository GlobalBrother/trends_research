import os
import pandas as pd
import json
import subprocess
import sys
import re

class TrendCollector:
    def __init__(self):
        # Define the path to SQLite database relative to project root
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.db_path = os.path.join(base_dir, "src", "collector", "trends.db")
        
    def get_db_trends(self, geo=None, include_trending_now=False, include_youtube=False, include_social=False, include_hackernews=False, include_reddit=False, include_news=False, include_stackexchange=False):
        """Reads trends from SQLite database."""
        import sqlite3
        import json

        if not os.path.exists(self.db_path):
            print(f"Database not found at {self.db_path}. No trends available.")
            return []

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = "SELECT * FROM trends WHERE 1=1"
            params = []

            # Platform filtering
            excluded_platforms = []
            if not include_trending_now:
                excluded_platforms.append('Google Trends')
            if not include_youtube:
                excluded_platforms.append('YouTube')
            if not include_social:
                excluded_platforms.extend(['X (Twitter)', 'Threads', 'Instagram'])
            if not include_hackernews:
                excluded_platforms.append('HackerNews')
            if not include_reddit:
                excluded_platforms.append('Reddit')
            if not include_news:
                excluded_platforms.append('News')
            if not include_stackexchange:
                excluded_platforms.append('StackExchange')
            
            if excluded_platforms:
                placeholders = ', '.join(['?'] * len(excluded_platforms))
                query += f" AND platform NOT IN ({placeholders})"
                params.extend(excluded_platforms)

            # Geo filtering (only for Google platforms that have geo)
            if geo is not None:
                # We want trends that either have no geo (Global) OR match requested geo
                # But wait, original logic was:
                # if data_type not in [...] and geo is not None:
                #     if str(item_geo).upper() != str(geo).upper(): continue
                
                google_platforms = ['Google Trends', 'Google Related Queries', 'Google Related Topics', 'Google Interest', 'Google Regions']
                gp_placeholders = ', '.join(['?'] * len(google_platforms))
                query += f" AND (platform NOT IN ({gp_placeholders}) OR UPPER(geo) = UPPER(?) OR geo = '' OR geo = 'Global' OR geo IS NULL)"
                params.extend(google_platforms)
                params.append(geo)

            query += " ORDER BY extracted_at DESC"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            trends = []
            seen = set()
            for row in rows:
                platform = row['platform']
                topic = row['topic']
                
                if (platform, topic) in seen:
                    continue
                
                item = {
                    "platform": platform,
                    "topic": topic,
                    "growth": row['growth'],
                    "keyword": row['keyword'],
                    "geo": row['geo'],
                    "url": row['url'],
                    "extracted_at": row['extracted_at']
                }
                
                # Expand extra_data
                if row['extra_data']:
                    try:
                        extra = json.loads(row['extra_data'])
                        item.update(extra)
                    except:
                        pass
                
                trends.append(item)
                seen.add((platform, topic))
                
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

    def run_youtube_trends_scraper(self, keywords):
        """Runs the Scrapy YouTube Trends spider for specific keywords."""
        return self._run_scraper("youtube_trends", keywords=keywords)

    def run_social_trends_scraper(self, platform, keywords):
        """Runs the Scrapy Social Trends spider for a specific platform."""
        return self._run_scraper("social_trends", platform=platform, keywords=keywords)

    def run_hackernews_scraper(self, keywords=None):
        """Runs the Scrapy HackerNews spider."""
        return self._run_scraper("hackernews", keywords=keywords)

    def run_reddit_scraper(self, subreddit='all', trend_type='hot', keywords=None):
        """Runs the Scrapy Reddit spider."""
        return self._run_scraper("reddit", subreddit=subreddit, trend_type=trend_type, keywords=keywords)

    def run_news_scraper(self, query='niche', api_key=None):
        """Runs the Scrapy NewsAPI spider."""
        return self._run_scraper("newsapi", q=query, api_key=api_key)

    def run_stackexchange_scraper(self, site='stackoverflow', sort='hot', keywords=None):
        """Runs the Scrapy StackExchange spider."""
        return self._run_scraper("stackexchange", site=site, sort=sort, keywords=keywords)

    def run_niche_comprehensive_scrape(self, niche_name, keywords, geo="US", timeframe="today 12-m", category=0):
        """Triggers all scrapers for a specific niche in sequence."""
        print(f"Starting comprehensive scrape for niche: {niche_name}")
        
        # We'll use a subset of keywords for more performant scraping across many platforms
        limited_keywords = keywords[:3] if len(keywords) > 3 else keywords
        
        # 1. Google Trends (the core scraper)
        self.run_google_trends_scraper(keywords, geo=geo, timeframe=timeframe, category=category)
        
        # 2. YouTube
        self.run_youtube_trends_scraper(limited_keywords)
        
        # 3. Social
        self.run_social_trends_scraper("X", limited_keywords)
        self.run_social_trends_scraper("Threads", limited_keywords)
        self.run_social_trends_scraper("Instagram", limited_keywords)
        
        # 4. Reddit
        self.run_reddit_scraper(keywords=limited_keywords)
        
        # 5. HackerNews
        self.run_hackernews_scraper(keywords=limited_keywords)
        
        # 6. StackExchange
        self.run_stackexchange_scraper(keywords=limited_keywords)
        
        # 7. NewsAPI (just use the niche name for NewsAPI)
        self.run_news_scraper(query=niche_name)
        
        print(f"Comprehensive scrape for {niche_name} finished.")
        return True

    def collect_all(self, geo=None, include_trending_now=False, include_youtube=False, include_social=False, include_hackernews=False, include_reddit=False, include_news=False, include_stackexchange=False):
        all_trends = []
        # Prefer DB over JSONL
        all_trends.extend(self.get_db_trends(geo=geo, include_trending_now=include_trending_now, include_youtube=include_youtube, include_social=include_social, include_hackernews=include_hackernews, include_reddit=include_reddit, include_news=include_news, include_stackexchange=include_stackexchange))
        
        if all_trends:
            return pd.DataFrame(all_trends)
        else:
            # Return empty DataFrame with expected columns
            return pd.DataFrame(columns=['platform', 'topic', 'growth', 'keyword', 'extracted_at'])

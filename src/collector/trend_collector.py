"""
TrendCollector — orchestrates data collection from scrapers and the SQLite database.

Responsibilities:
  1. Read aggregated trend data from the database.
  2. Invoke individual Scrapy spiders via subprocess.
  3. Provide a convenience method for comprehensive niche scrapes.
"""

import json
import logging
import os
import sqlite3
import subprocess
import sys
from typing import Optional

import pandas as pd

from src.config import (
    ALWAYS_INCLUDED_PLATFORMS,
    DB_PATH,
    SCRAPER_DIR,
)

logger = logging.getLogger(__name__)


class TrendCollector:
    """Central data-collection facade used by the API and dashboard."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Return a WAL-mode SQLite connection with performance pragmas."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA cache_size=-8000")
        conn.execute("PRAGMA mmap_size=67108864")
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Read trends
    # ------------------------------------------------------------------

    def get_db_trends(
        self,
        geo: Optional[str] = None,
        include_trending_now: bool = False,
        include_youtube: bool = False,
        include_social: bool = False,
        include_hackernews: bool = False,
        include_reddit: bool = False,
        include_news: bool = False,
    ) -> list[dict]:
        """Fetch trend rows from the database, filtered by platform flags and geo."""

        if not os.path.exists(self.db_path):
            logger.warning("Database not found at %s", self.db_path)
            return []

        # Build the list of platforms to include
        included_platforms: list[str] = list(ALWAYS_INCLUDED_PLATFORMS)
        _flag_map = {
            include_trending_now: ["Google Trends"],
            include_youtube: ["YouTube"],
            include_social: ["X (Twitter)", "Threads", "Instagram"],
            include_hackernews: ["HackerNews"],
            include_reddit: ["Reddit"],
            include_news: ["News"],
        }
        for flag, platforms in _flag_map.items():
            if flag:
                included_platforms.extend(platforms)

        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            placeholders = ", ".join(["?"] * len(included_platforms))
            query = (
                "SELECT platform, topic, growth, keyword, geo, url, "
                "extracted_at, extra_data FROM trends "
                f"WHERE platform IN ({placeholders})"
            )
            params: list = list(included_platforms)

            # Geo filtering
            if geo and geo != "Global":
                query += (
                    " AND (UPPER(geo) = UPPER(?) OR geo = '' "
                    "OR UPPER(geo) = 'GLOBAL' OR geo IS NULL)"
                )
                params.append(geo)
            elif geo == "Global":
                query += " AND (UPPER(geo) = 'GLOBAL' OR geo = '' OR geo IS NULL)"

            query += " ORDER BY extracted_at DESC"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            trends: list[dict] = []
            for row in rows:
                item = dict(row)
                extra_data = item.pop("extra_data", None)
                if extra_data:
                    try:
                        item.update(json.loads(extra_data))
                    except (json.JSONDecodeError, TypeError):
                        pass
                trends.append(item)

            return trends

        except Exception:
            logger.exception("Error reading trends from DB")
            return []

    # ------------------------------------------------------------------
    # Scraper invocation
    # ------------------------------------------------------------------

    def _run_scraper(self, spider_name: str, **kwargs) -> bool:
        """Run a Scrapy spider as a subprocess and return success status."""
        cmd = [sys.executable, "-m", "scrapy", "crawl", spider_name]
        for key, value in kwargs.items():
            if key == "keywords" and isinstance(value, list):
                value = ",".join(value)
            cmd.extend(["-a", f"{key}={value}"])

        logger.info("Running scraper: %s in %s", " ".join(cmd), SCRAPER_DIR)
        try:
            result = subprocess.run(cmd, cwd=SCRAPER_DIR, capture_output=False, text=True)
            if result.returncode != 0:
                logger.error("Scraper %s exited with code %d", spider_name, result.returncode)
                return False
            logger.info("Scraper %s completed successfully", spider_name)
            return True
        except Exception:
            logger.exception("Failed to run scraper %s", spider_name)
            return False

    # Convenience wrappers for each spider
    def run_google_trends_scraper(self, keywords, geo="US", timeframe="today 12-m", category=0):
        return self._run_scraper("google_trends", keywords=keywords, geo=geo, timeframe=timeframe, category=category)

    def run_trending_now_scraper(self, geo="US", trend_type="daily"):
        return self._run_scraper("trending_now", geo=geo, type=trend_type)

    def run_youtube_trends_scraper(self, keywords, geo="Global"):
        return self._run_scraper("youtube_trends", keywords=keywords, geo=geo)

    def run_social_trends_scraper(self, platform, keywords, geo="Global"):
        return self._run_scraper("social_trends", platform=platform, keywords=keywords, geo=geo)

    def run_hackernews_scraper(self, keywords=None, geo="Global"):
        return self._run_scraper("hackernews", keywords=keywords, geo=geo)

    def run_reddit_scraper(self, subreddit="all", trend_type="hot", keywords=None, geo="Global"):
        return self._run_scraper("reddit", subreddit=subreddit, trend_type=trend_type, keywords=keywords, geo=geo)

    def run_news_scraper(self, query="niche", api_key=None, geo="Global"):
        return self._run_scraper("newsapi", q=query, api_key=api_key, geo=geo)

    # ------------------------------------------------------------------
    # Comprehensive niche scrape
    # ------------------------------------------------------------------

    def run_niche_comprehensive_scrape(
        self, niche_name: str, keywords: list[str],
        geo: str = "US", timeframe: str = "today 12-m", category: int = 0,
    ) -> bool:
        """Run all scrapers sequentially for a given niche."""
        logger.info("Starting comprehensive scrape for niche: %s", niche_name)

        self.run_google_trends_scraper(keywords, geo=geo, timeframe=timeframe, category=category)
        self.run_youtube_trends_scraper(keywords, geo=geo)

        for social_platform in ("X", "Threads", "Instagram"):
            self.run_social_trends_scraper(social_platform, keywords, geo=geo)

        self.run_reddit_scraper(keywords=keywords, geo=geo)
        self.run_hackernews_scraper(keywords=keywords, geo=geo)
        self.run_news_scraper(query=niche_name, geo=geo)

        logger.info("Comprehensive scrape for %s finished", niche_name)
        return True

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def collect_all(self, **kwargs) -> pd.DataFrame:
        """Return a DataFrame of all matching trends from the DB."""
        trends = self.get_db_trends(**kwargs)
        if trends:
            return pd.DataFrame(trends)
        return pd.DataFrame(columns=["platform", "topic", "growth", "keyword", "extracted_at"])

    # ------------------------------------------------------------------
    # Errors
    # ------------------------------------------------------------------

    def get_scrape_errors(self, platform: Optional[str] = None) -> pd.DataFrame:
        """Read scrape errors from the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            query = "SELECT platform, keyword, url, status, reason, extracted_at FROM scrape_errors"
            params: list = []
            if platform:
                query += " WHERE platform = ?"
                params.append(platform)
            query += " ORDER BY extracted_at DESC"
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            return df
        except Exception:
            logger.exception("Error reading scrape errors from DB")
            return pd.DataFrame(columns=["platform", "keyword", "url", "status", "reason", "extracted_at"])

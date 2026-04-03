"""
Trend collector — orchestrates data collection from all scraper sources.

Reads stored trends from the database and dispatches scraping jobs
to Google Trends (Scrapy), EnsembleData social scrapers, and NewsAPI.

Optimizations
-------------
* Uses ``session_scope()`` context manager for clean session lifecycle.
* ``get_db_trends()`` now accepts a ``limit`` parameter (default 10 000)
  to prevent loading millions of rows into memory.
* Geo filtering normalises values at comparison time and avoids
  ``func.upper()`` on the column side where possible.
"""

import json
import logging
import os
import subprocess
import sys
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# EnsembleData scraper imports (optional dependency)
# ---------------------------------------------------------------------------

try:
    _ensembledata_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "scrapers", "ensembledata"),
    )
    if _ensembledata_dir not in sys.path:
        sys.path.insert(0, _ensembledata_dir)
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

from src.db.connection import session_scope
from src.db.models import Trend, Platform, ScrapeError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GOOGLE_NICHE_PLATFORMS = (
    "Google Interest",
    "Google Regions",
    "Google Related Queries",
    "Google Related Topics",
)

SOCIAL_PLATFORMS = ("TikTok", "Instagram", "Threads")

EXPECTED_COLUMNS = ("platform", "topic", "growth", "keyword", "extracted_at")

_SOCIAL_SCRAPER_MAP = {
    "TikTok": lambda kws, geo: scrape_tiktok(kws, geo=geo),
    "Instagram": lambda kws, geo: scrape_instagram(kws, geo=geo),
    "Threads": lambda kws, geo: scrape_threads(kws, geo=geo),
}

# Default row limit for get_db_trends — prevents loading the entire table.
DEFAULT_TREND_LIMIT = int(os.getenv("TREND_QUERY_LIMIT", "10000"))


class TrendCollector:
    """Orchestrates trend collection from multiple data sources."""

    # ------------------------------------------------------------------
    # Database reads
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
        limit: int = DEFAULT_TREND_LIMIT,
    ) -> list[dict]:
        """Read trends from the database, filtered by platform and geo.

        Parameters
        ----------
        limit : int
            Maximum number of rows to return (default 10 000).  Set to 0
            to disable the limit (use with caution on large tables).
        """
        try:
            included_platforms = list(GOOGLE_NICHE_PLATFORMS)
            if include_trending_now:
                included_platforms.append("Google Trends")
            if include_youtube:
                included_platforms.append("YouTube")
            if include_social:
                included_platforms.extend(SOCIAL_PLATFORMS)
            if include_hackernews:
                included_platforms.append("HackerNews")
            if include_reddit:
                included_platforms.append("Reddit")
            if include_news:
                included_platforms.append("News")

            with session_scope() as session:
                query = (
                    session.query(
                        Platform.name.label("platform"),
                        Trend.topic,
                        Trend.growth,
                        Trend.keyword,
                        Trend.geo,
                        Trend.extracted_at,
                        Trend.extra_data,
                    )
                    .join(Platform, Platform.id == Trend.platform_id)
                    .filter(Platform.name.in_(included_platforms))
                )

                query = self._apply_geo_filter(query, geo)
                query = query.order_by(Trend.extracted_at.desc())

                if limit > 0:
                    query = query.limit(limit)

                rows = query.all()

            return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            logger.error("Error reading trends from DB: %s", e)
            return []

    @staticmethod
    def _apply_geo_filter(query, geo: Optional[str]):
        """Apply geo filtering to a SQLAlchemy query.

        Uses direct string comparisons with common case variants to
        enable index usage. Avoids wrapping the column in func.upper()
        which prevents SQL Server from using indexes.
        """
        if geo is None:
            return query
        geo_clean = geo.strip()
        if geo_clean.upper() in ("GLOBAL", ""):
            return query.filter(
                (Trend.geo == "Global")
                | (Trend.geo == "GLOBAL")
                | (Trend.geo == "global")
                | (Trend.geo == "")
                | (Trend.geo.is_(None))
            )
        # Match common case variants to avoid func.upper() on the column
        return query.filter(
            (Trend.geo == geo_clean)
            | (Trend.geo == geo_clean.upper())
            | (Trend.geo == geo_clean.lower())
            | (Trend.geo == "")
            | (Trend.geo == "Global")
            | (Trend.geo == "GLOBAL")
            | (Trend.geo.is_(None))
        )

    @staticmethod
    def _row_to_dict(row) -> dict:
        """Convert a database row to a dictionary, expanding extra_data JSON."""
        item = {
            "platform": row.platform,
            "topic": row.topic,
            "growth": row.growth,
            "keyword": row.keyword,
            "geo": row.geo,
            "extracted_at": row.extracted_at,
        }
        if row.extra_data:
            try:
                item.update(json.loads(row.extra_data))
            except (json.JSONDecodeError, TypeError):
                logger.debug("Failed to parse extra_data for topic: %s", row.topic)
        return item

    # ------------------------------------------------------------------
    # Scrapy spider runner
    # ------------------------------------------------------------------

    def _run_scraper(self, spider_name: str, **kwargs) -> bool:
        """Run a Scrapy spider with the given arguments."""
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        project_dir = os.path.join(base_dir, "src", "scrapers", "google_trends_scraper")

        cmd = [sys.executable, "-m", "scrapy", "crawl", spider_name]
        for key, value in kwargs.items():
            if key == "keywords" and isinstance(value, list):
                value = ",".join(value)
            cmd.extend(["-a", f"{key}={value}"])

        try:
            logger.info("Running scraper: %s in %s", " ".join(cmd), project_dir)
            result = subprocess.run(cmd, cwd=project_dir, capture_output=False, text=True)

            if result.returncode != 0:
                logger.error("Scraper %s failed with return code %d", spider_name, result.returncode)
                return False

            logger.info("Scraper %s completed successfully.", spider_name)
            return True
        except Exception as e:
            logger.error("Failed to run Scrapy scraper %s: %s", spider_name, e)
            return False

    # ------------------------------------------------------------------
    # Individual scraper dispatchers
    # ------------------------------------------------------------------

    def run_google_trends_scraper(
        self,
        keywords: list[str],
        geo: str = "US",
        timeframe: str = "today 12-m",
        category: int = 0,
    ) -> bool:
        """Run the Scrapy Google Trends spider for specific keywords."""
        return self._run_scraper(
            "google_trends", keywords=keywords, geo=geo, timeframe=timeframe, category=category,
        )

    def run_trending_now_scraper(self, geo: str = "US", trend_type: str = "daily") -> bool:
        """Run the Scrapy Trending Now spider."""
        return self._run_scraper("trending_now", geo=geo, type=trend_type)

    def run_youtube_trends_scraper(self, keywords, geo: str = "Global") -> bool:
        """Run the YouTube scraper via EnsembleData."""
        if not HAS_ENSEMBLEDATA or not os.getenv("ENSEMBLEDATA_TOKEN"):
            logger.info("[youtube] EnsembleData not available — skipping.")
            return False
        kw_list = self._ensure_keyword_list(keywords)
        scrape_youtube(kw_list, geo=geo)
        return True

    def run_social_trends_scraper(self, platform: str, keywords, geo: str = "Global") -> bool:
        """Run a social media scraper via EnsembleData."""
        kw_list = self._ensure_keyword_list(keywords)

        if HAS_ENSEMBLEDATA and os.getenv("ENSEMBLEDATA_TOKEN"):
            scraper_fn = _SOCIAL_SCRAPER_MAP.get(platform)
            if scraper_fn:
                scraper_fn(kw_list, geo)
                return True

        if platform in SOCIAL_PLATFORMS:
            logger.info("[%s] EnsembleData not available — skipping.", platform.lower())
            return False

        logger.warning("Unknown social platform: %s", platform)
        return False

    def run_hackernews_scraper(self, keywords=None, geo: str = "Global") -> bool:
        """Run the Scrapy HackerNews spider."""
        return self._run_scraper("hackernews", keywords=keywords, geo=geo)

    def run_reddit_scraper(
        self,
        subreddit: str = "all",
        trend_type: str = "hot",
        keywords=None,
        geo: str = "Global",
    ) -> bool:
        """Run the Reddit scraper via EnsembleData."""
        if not HAS_ENSEMBLEDATA or not os.getenv("ENSEMBLEDATA_TOKEN"):
            logger.info("[reddit] EnsembleData not available — skipping.")
            return False
        subs = [subreddit] if isinstance(subreddit, str) else subreddit
        scrape_reddit(subs, geo=geo, sort=trend_type)
        return True

    def run_news_scraper(self, query: str = "niche", api_key: Optional[str] = None, geo: str = "Global") -> bool:
        """Run the Scrapy NewsAPI spider."""
        return self._run_scraper("newsapi", q=query, api_key=api_key, geo=geo)

    def run_token_import(self, widgets_json: str, geo: str = "US", keyword: str = "Unknown") -> bool:
        """Run the token import spider with pre-parsed widget tokens."""
        return self._run_scraper("token_import", widgets_json=widgets_json, geo=geo, keyword=keyword)

    # ------------------------------------------------------------------
    # Comprehensive niche scrape
    # ------------------------------------------------------------------

    def run_niche_comprehensive_scrape(
        self,
        niche_name: str,
        keywords: list[str],
        geo: str = "US",
        timeframe: str = "today 12-m",
        category: int = 0,
    ) -> bool:
        """Trigger all scrapers for a specific niche in sequence."""
        logger.info("Starting comprehensive scrape for niche: %s", niche_name)

        self.run_google_trends_scraper(keywords, geo=geo, timeframe=timeframe, category=category)
        self.run_youtube_trends_scraper(keywords, geo=geo)

        for platform in SOCIAL_PLATFORMS:
            self.run_social_trends_scraper(platform, keywords, geo=geo)

        self.run_reddit_scraper(keywords=keywords, geo=geo)
        self.run_hackernews_scraper(keywords=keywords, geo=geo)
        self.run_news_scraper(query=niche_name, geo=geo)

        logger.info("Comprehensive scrape for %s finished.", niche_name)
        return True

    # ------------------------------------------------------------------
    # Collect all trends
    # ------------------------------------------------------------------

    def collect_all(self, **kwargs) -> pd.DataFrame:
        """Collect all trends from the database and return as a DataFrame."""
        all_trends = self.get_db_trends(**kwargs)
        if all_trends:
            return pd.DataFrame(all_trends)
        return pd.DataFrame(columns=list(EXPECTED_COLUMNS))

    # ------------------------------------------------------------------
    # Scrape errors
    # ------------------------------------------------------------------

    def get_scrape_errors(self, platform: Optional[str] = None) -> pd.DataFrame:
        """Read scrape errors from the database."""
        error_columns = ("platform", "keyword", "url", "status", "reason", "extracted_at")
        try:
            with session_scope() as session:
                query = session.query(
                    ScrapeError.platform,
                    ScrapeError.keyword,
                    ScrapeError.url,
                    ScrapeError.status,
                    ScrapeError.reason,
                    ScrapeError.extracted_at,
                )
                if platform:
                    query = query.filter(ScrapeError.platform == platform)
                query = query.order_by(ScrapeError.extracted_at.desc()).limit(5000)
                rows = query.all()

            if rows:
                return pd.DataFrame(rows, columns=list(error_columns))
            return pd.DataFrame(columns=list(error_columns))
        except Exception as e:
            logger.error("Error reading scrape errors from DB: %s", e)
            return pd.DataFrame(columns=list(error_columns))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_keyword_list(keywords) -> list[str]:
        """Normalise keywords to a list of strings."""
        if isinstance(keywords, list):
            return keywords
        return [k.strip() for k in str(keywords).split(",")]

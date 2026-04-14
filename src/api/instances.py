import os
import sys
from src.config import PROJECT_ROOT
from src.collector.trend_collector import TrendCollector
from src.analytics.analytics_engine import AnalyticsEngine
from src.insights import InsightPipeline
from src.niche.niche_discovery import NicheDiscovery

collector = TrendCollector()
analytics = AnalyticsEngine()
pipeline = InsightPipeline(analytics=analytics)
niche_discovery = NicheDiscovery()

# Try to import GetHookdAI ads scraper
try:
    _gha_dir = os.path.join(PROJECT_ROOT, "src", "scrapers", "gethookedai")
    if _gha_dir not in sys.path:
        sys.path.insert(0, _gha_dir)
    from ads_insight import (
        scrape_ads as gethookd_scrape_ads,
        scrape_brand_ads as gethookd_scrape_brand_ads,
        search_brands as gethookd_search_brands,
    )
    HAS_GETHOOKEDAI = True
except ImportError:
    HAS_GETHOOKEDAI = False
    gethookd_scrape_ads = None
    gethookd_scrape_brand_ads = None
    gethookd_search_brands = None

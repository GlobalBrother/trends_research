"""
Centralized configuration for the Trends Research System.

All environment variables, paths, and tunable constants are defined here
so that every other module imports from a single source of truth.
"""

import os
from dotenv import load_dotenv

# Load .env from project root (two levels up from src/)
# When running on Azure, secrets are already in env vars via Key Vault
# (loaded by main.py _init_secrets), so load_dotenv is a harmless no-op.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"), override=False)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = _PROJECT_ROOT
SCRAPER_DIR = os.path.join(PROJECT_ROOT, "src", "scrapers", "google_trends_scraper")

# ---------------------------------------------------------------------------
# API / Backend
# ---------------------------------------------------------------------------
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", 8000))
BACKEND_URL = os.getenv("BACKEND_URL", f"http://127.0.0.1:{BACKEND_PORT}")
CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "*").split(",")

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", 300))  # 5 min

# ---------------------------------------------------------------------------
# Scraper tunables (also consumed by Scrapy settings.py via env vars)
# ---------------------------------------------------------------------------
SCRAPE_FRESHNESS_HOURS = int(os.getenv("SCRAPE_FRESHNESS_HOURS", 144))
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
CLUSTER_THRESHOLD = float(os.getenv("CLUSTER_THRESHOLD", 0.7))
DEFAULT_N_CLUSTERS = int(os.getenv("DEFAULT_N_CLUSTERS", 5))

# Platform weights used in virality score calculation
PLATFORM_WEIGHTS: dict[str, float] = {
    "Google Trends": 1.0,
    "Google Related Queries": 1.1,
    "Google Related Topics": 1.1,
    "Google Interest": 1.0,
    "Google Regions": 1.2,
    "YouTube": 1.3,
    "Threads": 1.2,
    "Instagram": 1.2,
    "HackerNews": 1.3,
    "Reddit": 1.4,
    "News": 1.1,
}

# Platforms that are always included in queries regardless of user filters
ALWAYS_INCLUDED_PLATFORMS: list[str] = [
    "Google Interest",
    "Google Regions",
    "Google Related Queries",
    "Google Related Topics",
]

# ---------------------------------------------------------------------------
# Dashboard / UI
# ---------------------------------------------------------------------------
COUNTRIES: dict[str, str] = {
    "United States": "US", "Global": "Global", "United Kingdom": "GB",
    "Canada": "CA", "Australia": "AU", "Germany": "DE", "France": "FR",
    "Italy": "IT", "Spain": "ES", "Brazil": "BR", "India": "IN",
    "Japan": "JP", "Romania": "RO", "Netherlands": "NL", "Sweden": "SE",
    "Switzerland": "CH", "Mexico": "MX", "Argentina": "AR",
    "Singapore": "SG", "South Korea": "KR", "China": "CN", "Russia": "RU",
    "South Africa": "ZA", "Turkey": "TR", "United Arab Emirates": "AE",
    "Poland": "PL", "Belgium": "BE", "Austria": "AT", "Denmark": "DK",
    "Norway": "NO", "Finland": "FI", "Portugal": "PT", "Greece": "GR",
    "Czech Republic": "CZ", "Hungary": "HU",
}

TIMEFRAMES: dict[str, str] = {
    "Last 12 Months": "today 12-m", "Last hour": "now 1-H",
    "Last 4 hours": "now 4-H", "Last day": "now 1-d",
    "Last 7 days": "now 7-d", "Last 30 days": "today 1-m",
    "Last 90 days": "today 3-m", "Last 5 years": "today 5-y",
    "All (since 2004)": "all",
}

CATEGORIES: dict[str, int] = {
    "All Categories": 0, "Arts & Entertainment": 3, "Autos & Vehicles": 47,
    "Beauty & Fitness": 44, "Books & Literature": 22, "Business & Industrial": 12,
    "Computers & Electronics": 5, "Finance": 7, "Food & Drink": 71, "Games": 8,
    "Health": 45, "Hobbies & Leisure": 65, "Home & Garden": 11,
    "Internet & Telecom": 13, "Jobs & Education": 958, "Law & Government": 19,
    "News": 16, "Online Communities": 299, "People & Society": 14,
    "Pets & Animals": 66, "Real Estate": 29, "Reference": 533, "Science": 174,
    "Shopping": 18, "Sports": 20, "Travel": 67,
}

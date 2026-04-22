"""Shared singletons and helpers for the FastAPI routers.

This module centralises the pieces that used to live at module scope in
``src/api/main.py`` so individual routers can import them without creating
import cycles.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from src.config import CACHE_TTL_SECONDS, PROJECT_ROOT
from src.collector.trend_collector import TrendCollector
from src.analytics.analytics_engine import AnalyticsEngine
from src.niche.niche_discovery import NicheDiscovery
from src.db.connection import get_engine, get_session, session_scope
from src.db.models import Niche, TokenUsage

logger = logging.getLogger("src.api")

# ---------------------------------------------------------------------------
# GetHookdAI ads scraper — only imported when a token is configured.
# ---------------------------------------------------------------------------
GETHOOKEDAI_TOKEN = os.getenv("GETHOOKEDAI_TOKEN", "").strip()
if GETHOOKEDAI_TOKEN:
    _gha_dir = os.path.join(PROJECT_ROOT, "src", "scrapers", "gethookedai")
    if _gha_dir not in sys.path:
        sys.path.insert(0, _gha_dir)
    from src.scrapers.gethookedai import ads_insight  # noqa: F401
    from ads_insight import (
        scrape_ads as gethookd_scrape_ads,
        scrape_brand_ads as gethookd_scrape_brand_ads,
        search_brands as gethookd_search_brands,
    )
    HAS_GETHOOKEDAI = True
else:
    ads_insight = None
    gethookd_scrape_ads = None
    gethookd_scrape_brand_ads = None
    gethookd_search_brands = None
    HAS_GETHOOKEDAI = False
    logger.info(
        "GETHOOKEDAI_TOKEN not set — /scrape_ads and /ads_insight will return empty responses."
    )

# ---------------------------------------------------------------------------
# Engine init — never crashes; DB endpoints will fail if DB is unreachable.
# ---------------------------------------------------------------------------
try:
    engine = get_engine()
except Exception as _eng_err:  # pragma: no cover - defensive
    logging.basicConfig(level=logging.INFO)
    logger.warning(
        "Could not create database engine on startup: %s. "
        "The app will start, but DB-dependent endpoints will fail until "
        "Azure SQL becomes reachable.",
        _eng_err,
    )
    engine = None

SessionFactory = get_session  # backward-compat alias

# ---------------------------------------------------------------------------
# Resend API config
# ---------------------------------------------------------------------------
import resend  # noqa: E402

resend.api_key = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "noreply@yourdomain.com")

# Test account that bypasses OTP (for development/testing).
TEST_ACCOUNT_EMAIL = os.getenv("TEST_ACCOUNT_EMAIL", "").strip()
TEST_ACCOUNT_OTP = os.getenv("TEST_ACCOUNT_OTP", "000000").strip()

# ---------------------------------------------------------------------------
# Shared singleton instances
# ---------------------------------------------------------------------------
collector = TrendCollector()
analytics = AnalyticsEngine()
niche = NicheDiscovery()


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

class _JSONEncoder(json.JSONEncoder):
    """Handle numpy, pandas, datetime, and set types.

    Each branch logs a warning so we can track where non-Pydantic data is
    still flowing through Starlette's default encoder. Pydantic models on
    every endpoint should have already serialised these types — anything
    landing here means a route bypassed its ``response_model``.
    """

    def default(self, obj):
        if hasattr(obj, "tolist"):
            logger.warning(
                "_JSONEncoder fallback: numpy/pandas array-like %s slipped past response_model",
                type(obj).__name__,
            )
            return obj.tolist()
        if isinstance(obj, (datetime, pd.Timestamp)):
            logger.warning(
                "_JSONEncoder fallback: datetime/Timestamp slipped past response_model",
            )
            return obj.isoformat()
        if isinstance(obj, set):
            logger.warning("_JSONEncoder fallback: set slipped past response_model")
            return list(obj)
        try:
            return super().default(obj)
        except TypeError:
            logger.warning(
                "_JSONEncoder fallback: unknown type %s coerced via str()",
                type(obj).__name__,
            )
            return str(obj)


def _sanitize(df: pd.DataFrame) -> list[dict]:
    """Replace NaN/Inf and serialize a DataFrame to JSON-safe records."""
    df = df.copy()
    df = df.fillna("")
    df = df.replace([float("inf"), float("-inf")], None)
    records = df.to_dict(orient="records")
    return json.loads(json.dumps(records, cls=_JSONEncoder))


# ---------------------------------------------------------------------------
# In-memory cache (single shared singleton)
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, fn, ttl: int = CACHE_TTL_SECONDS):
    """Return cached result if fresh, otherwise compute, cache, and return."""
    now = time.time()
    if key in _cache:
        ts, data = _cache[key]
        if now - ts < ttl:
            logger.debug("Cache hit: %s", key)
            return data
    result = fn()
    _cache[key] = (now, result)
    return result


# ---------------------------------------------------------------------------
# Misc shared helpers
# ---------------------------------------------------------------------------

def _get_niche_keywords_from_db(niche_name: str) -> list:
    """Fetch keywords for a niche from the DB, falling back to NicheDiscovery."""
    try:
        with session_scope() as session:
            rows = session.query(Niche.keyword).filter(Niche.niche_name == niche_name).all()
        keywords = [r.keyword for r in rows]
        if keywords:
            return keywords
    except Exception:
        pass
    return niche.get_niche_keywords(niche_name)


def _log_token_usage(platform: str, keyword: str = None, units: float = 1.0, geo: str = None):
    """Record an API / scrape usage entry."""
    try:
        with session_scope() as session:
            session.add(TokenUsage(platform=platform, keyword=keyword, units_charged=units, geo=geo))
    except Exception as e:
        logger.error(f"Failed to log token usage: {e}")


def _run_and_log(func, log_platform, log_keywords, log_geo, **kwargs):
    """Wrapper: runs a scraper function then logs one usage row per keyword."""
    try:
        result = func(**kwargs)
    except Exception as e:
        logger.error(f"Scraper {log_platform} failed: {e}")
        result = None
    if isinstance(log_keywords, list):
        for kw in log_keywords:
            _log_token_usage(log_platform, keyword=kw, units=1.0, geo=log_geo)
    else:
        _log_token_usage(log_platform, keyword=log_keywords, units=1.0, geo=log_geo)
    return result


__all__ = [
    "logger",
    "engine",
    "SessionFactory",
    "session_scope",
    "collector",
    "analytics",
    "niche",
    "_JSONEncoder",
    "_sanitize",
    "_cache",
    "_cached",
    "_get_niche_keywords_from_db",
    "_log_token_usage",
    "_run_and_log",
    "HAS_GETHOOKEDAI",
    "gethookd_scrape_ads",
    "gethookd_scrape_brand_ads",
    "gethookd_search_brands",
    "RESEND_FROM_EMAIL",
    "TEST_ACCOUNT_EMAIL",
    "TEST_ACCOUNT_OTP",
    "PROJECT_ROOT",
]


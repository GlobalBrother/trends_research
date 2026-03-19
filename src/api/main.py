"""
FastAPI backend for the Trends Research System.

Provides REST endpoints consumed by the Streamlit dashboard and external clients.
"""

import json
import hashlib
import logging
import time
import traceback
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import CORS_ORIGINS, CACHE_TTL_SECONDS
from src.collector.trend_collector import TrendCollector
from src.analytics.analytics_engine import AnalyticsEngine
from src.niche.niche_discovery import NicheDiscovery

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App & middleware
# ---------------------------------------------------------------------------
app = FastAPI(title="Trends Research API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Shared instances
# ---------------------------------------------------------------------------
collector = TrendCollector()
analytics = AnalyticsEngine()
niche = NicheDiscovery()

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ScrapeRequest(BaseModel):
    niche: str
    geo: str = "US"
    timeframe: str = "today 12-m"
    category: int = 0

# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

class _JSONEncoder(json.JSONEncoder):
    """Handle numpy, pandas, datetime, and set types."""
    def default(self, obj):
        if hasattr(obj, "tolist"):
            return obj.tolist()
        if isinstance(obj, (datetime, pd.Timestamp)):
            return obj.isoformat()
        if isinstance(obj, set):
            return list(obj)
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


def _sanitize(df: pd.DataFrame) -> list[dict]:
    """Replace NaN/Inf and serialize a DataFrame to JSON-safe records."""
    df = df.copy()
    df = df.fillna("")
    df = df.replace([float("inf"), float("-inf")], None)
    records = df.to_dict(orient="records")
    return json.loads(json.dumps(records, cls=_JSONEncoder))

# ---------------------------------------------------------------------------
# In-memory cache
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
# Freshness check helper
# ---------------------------------------------------------------------------

def _needs_scrape(df: pd.DataFrame, platform_col_value: str, hours: int = 24,
                  niche_name: Optional[str] = None) -> bool:
    """Return True if the data for *platform_col_value* is stale or missing."""
    if df.empty or "platform" not in df.columns:
        return True
    subset = df[df["platform"] == platform_col_value]
    if niche_name:
        kws = niche.get_niche_keywords(niche_name)
        if "keyword" in subset.columns:
            subset = subset[subset["keyword"].isin(kws)]
    if subset.empty:
        return True
    last = pd.to_datetime(subset["extracted_at"]).max()
    return datetime.now() - last.to_pydatetime() > timedelta(hours=hours)

# ---------------------------------------------------------------------------
# Platform endpoint helper (reduces massive duplication)
# ---------------------------------------------------------------------------

def _platform_endpoint(
    platform_db_name: str,
    collect_kwargs: dict,
    niche_name: Optional[str],
    geo: Optional[str],
    scrape_fn=None,
    freshness_hours: int = 24,
) -> dict:
    """Generic handler: check freshness -> optionally scrape -> filter -> process -> return."""
    raw = collector.collect_all(geo=geo, **collect_kwargs)

    if scrape_fn and _needs_scrape(raw, platform_db_name, freshness_hours, niche_name):
        if scrape_fn():
            raw = collector.collect_all(geo=geo, **collect_kwargs)

    if raw.empty:
        return {"data": []}

    subset = raw[raw["platform"] == platform_db_name].copy()
    if subset.empty:
        return {"data": []}

    if niche_name:
        subset = niche.filter_by_niche(subset, niche_name)
    if subset.empty:
        return {"data": []}

    processed = analytics.process_trends(subset)
    return {"data": _sanitize(processed)}

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"message": "Trends Research API v2.0 is running"}


@app.get("/niches")
def get_niches():
    return niche.get_available_niches()


@app.get("/niche_keywords/{niche_name}")
def get_niche_keywords(niche_name: str):
    return {"niche": niche_name, "keywords": niche.get_niche_keywords(niche_name)}


@app.post("/scrape")
def scrape_niche(request: ScrapeRequest, background_tasks: BackgroundTasks):
    kws = niche.get_niche_keywords(request.niche)
    background_tasks.add_task(
        collector.run_niche_comprehensive_scrape,
        niche_name=request.niche,
        keywords=kws,
        geo=request.geo,
        timeframe=request.timeframe,
        category=request.category,
    )
    return {"message": f"Comprehensive scraping for {request.niche} started in background."}


@app.get("/trends")
def get_trends(geo: Optional[str] = Query(None), niche_name: Optional[str] = Query(None)):
    try:
        if geo in ("", "None"):
            geo = ""
        cache_key = f"trends_{geo}_{niche_name}"

        def _compute():
            raw = collector.collect_all(
                geo=geo,
                include_trending_now=not bool(niche_name),
                include_youtube=True,
                include_social=True,
                include_hackernews=True,
                include_reddit=True,
                include_news=True,
            )
            if raw.empty:
                return []
            processed = analytics.process_trends(raw)
            if niche_name:
                processed = niche.filter_by_niche(processed, niche_name)
            if len(processed) >= 5 and "topic" in processed.columns:
                processed = niche.discover_micro_niches(processed)
            processed = processed.copy()
            if "niche_cluster" in processed.columns:
                processed["niche_cluster"] = (
                    pd.array(processed["niche_cluster"].fillna(-1).astype(int), dtype=pd.Int64Dtype())
                )
            return _sanitize(processed)

        return {"data": _cached(cache_key, _compute)}
    except Exception as e:
        logger.error("Error in /trends: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trending_now")
def get_trending_now(geo: str = Query("US"), trend_type: str = Query("daily")):
    if geo in ("None", "", "Global") or geo is None:
        geo = "US"

    raw = collector.collect_all(geo=geo, include_trending_now=True)

    if _needs_scrape(raw, "Google Trends", hours=12):
        if collector.run_trending_now_scraper(geo=geo, trend_type=trend_type):
            raw = collector.collect_all(geo=geo, include_trending_now=True)

    if raw.empty:
        return {"data": []}

    try:
        subset = raw[raw["platform"] == "Google Trends"].copy()
        if subset.empty:
            return {"data": []}
        processed = analytics.process_trends(subset)
        return {"data": _sanitize(processed)}
    except Exception as e:
        logger.error("Error in /trending_now: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/youtube_trends")
def get_youtube_trends(niche_name: str = Query(...), geo: Optional[str] = Query(None)):
    kws = niche.get_niche_keywords(niche_name)
    return _platform_endpoint(
        "YouTube",
        {"include_youtube": True},
        niche_name, geo,
        scrape_fn=lambda: collector.run_youtube_trends_scraper(keywords=kws[:5]),
    )


@app.get("/social_trends")
def get_social_trends(platform: str = Query(...), niche_name: str = Query(...), geo: Optional[str] = Query(None)):
    platform_map = {"X": "X (Twitter)", "Threads": "Threads", "Instagram": "Instagram"}
    target = platform_map.get(platform)
    if not target:
        raise HTTPException(status_code=400, detail="Invalid platform")
    kws = niche.get_niche_keywords(niche_name)
    return _platform_endpoint(
        target,
        {"include_social": True},
        niche_name, geo,
        scrape_fn=lambda: collector.run_social_trends_scraper(platform=platform, keywords=kws[:3]),
    )


@app.get("/hackernews_trends")
def get_hackernews_trends(niche_name: Optional[str] = Query(None), geo: Optional[str] = Query(None)):
    kws = niche.get_niche_keywords(niche_name) if niche_name else None
    return _platform_endpoint(
        "HackerNews",
        {"include_hackernews": True},
        niche_name, geo,
        scrape_fn=lambda: collector.run_hackernews_scraper(keywords=kws),
        freshness_hours=1 if not niche_name else 24,
    )


@app.get("/reddit_trends")
def get_reddit_trends(
    subreddit: str = Query("all"),
    trend_type: str = Query("hot"),
    niche_name: Optional[str] = Query(None),
    geo: Optional[str] = Query(None),
):
    kws = niche.get_niche_keywords(niche_name) if niche_name else None
    return _platform_endpoint(
        "Reddit",
        {"include_reddit": True},
        niche_name, geo,
        scrape_fn=lambda: collector.run_reddit_scraper(subreddit=subreddit, trend_type=trend_type, keywords=kws),
        freshness_hours=1 if not niche_name else 24,
    )


@app.get("/news_trends")
def get_news_trends(query: str = Query("niche"), niche_name: Optional[str] = Query(None), geo: Optional[str] = Query(None)):
    target_query = niche_name or query
    return _platform_endpoint(
        "News",
        {"include_news": True},
        niche_name, geo,
        scrape_fn=lambda: collector.run_news_scraper(query=target_query),
    )


@app.get("/all_trends")
def get_all_trends():
    raw = collector.collect_all(
        include_trending_now=True, include_youtube=True,
        include_social=True, include_hackernews=True,
        include_reddit=True, include_news=True,
    )
    if raw.empty:
        return {"data": []}
    processed = analytics.process_trends(raw)
    return {"data": _sanitize(processed)}


@app.get("/scrape_errors")
def get_scrape_errors(platform: Optional[str] = Query(None)):
    df = collector.get_scrape_errors(platform=platform)
    if df.empty:
        return {"data": []}
    return {"data": _sanitize(df)}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    from src.config import BACKEND_HOST, BACKEND_PORT
    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT)

import logging
import threading
from typing import Optional

from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel

from src.api.instances import collector, analytics, niche_discovery
from src.api.utils import sanitize_dataframe, needs_scrape
from src.api.deps import get_current_user
from src.db.models import User

router = APIRouter(tags=["trends"])
logger = logging.getLogger(__name__)

_scrape_locks: dict[str, threading.Lock] = {}
_scrape_locks_guard = threading.Lock()


def _trigger_background_scrape(platform_key: str, scrape_fn):
    """Run *scrape_fn* in a daemon thread if one isn't already running."""
    with _scrape_locks_guard:
        if platform_key not in _scrape_locks:
            _scrape_locks[platform_key] = threading.Lock()
        lock = _scrape_locks[platform_key]

    if not lock.acquire(blocking=False):
        logger.debug("Scrape already running for %s — skipping", platform_key)
        return

    def _run():
        try:
            scrape_fn()
        except Exception:
            logger.error("Background scrape failed for %s", platform_key, exc_info=True)
        finally:
            lock.release()

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _platform_endpoint_handler(
    platform_db_name: str,
    collect_kwargs: dict,
    niche_name: Optional[str],
    geo: Optional[str],
    scrape_fn=None,
    freshness_hours: int = 24,
) -> dict:
    """Generic handler for trend endpoints."""
    raw = collector.collect_all(geo=geo, **collect_kwargs)

    if scrape_fn and needs_scrape(raw, platform_db_name, freshness_hours):
        _trigger_background_scrape(platform_db_name, scrape_fn)

    if raw.empty:
        return {"data": []}

    subset = raw[raw["platform"] == platform_db_name].copy()
    if subset.empty:
        return {"data": []}

    if niche_name:
        subset = niche_discovery.filter_by_niche(subset, niche_name)
    
    if subset.empty:
        return {"data": []}

    processed = analytics.process_trends(subset)
    return {"data": sanitize_dataframe(processed)}


class ScrapeRequest(BaseModel):
    niche: str
    geo: str = "US"
    timeframe: str = "today 12-m"
    category: int = 0
    scraper_type: str = "all"


@router.post("/scrape")
def trigger_scrape(body: ScrapeRequest, user: User = Depends(get_current_user)):
    """Trigger a comprehensive niche scrape across all platforms."""
    keywords = niche_discovery.get_niche_keywords(body.niche)
    
    _trigger_background_scrape(
        f"niche_{body.niche}",
        lambda: collector.run_niche_comprehensive_scrape(
            body.niche, keywords, geo=body.geo, timeframe=body.timeframe, category=body.category
        )
    )
    return {"message": f"Scrape triggered for {body.niche}", "keywords": keywords}


@router.get("/trends")
def get_trends(niche_name: str = Query(None), geo: str = Query("US")):
    """Get processed trends (all sources)."""
    raw = collector.collect_all(geo=geo, include_trending_now=True, include_youtube=True, include_social=True, include_news=True)
    if niche_name:
        raw = niche_discovery.filter_by_niche(raw, niche_name)
    processed = analytics.process_trends(raw)
    return {"data": sanitize_dataframe(processed)}


@router.get("/trending_now")
def get_trending_now(niche_name: str = Query(None), geo: str = Query("US")):
    """Get Google Trending Now data."""
    return _platform_endpoint_handler(
        "Trending Now",
        {"include_trending_now": True},
        niche_name,
        geo,
        scrape_fn=lambda: collector.run_trending_now_scraper(geo=geo)
    )


@router.get("/youtube_trends")
def get_youtube_trends(niche_name: str = Query(None), geo: str = Query("US")):
    """Get YouTube trending topics."""
    keywords = niche_discovery.get_niche_keywords(niche_name) if niche_name else None
    return _platform_endpoint_handler(
        "YouTube",
        {"include_youtube": True},
        niche_name,
        geo,
        scrape_fn=lambda: collector.run_youtube_trends_scraper(keywords or ["trends"], geo=geo)
    )


@router.get("/reddit_trends")
def get_reddit_trends(niche_name: str = Query(None), geo: str = Query("US")):
    """Get Reddit trending topics."""
    return _platform_endpoint_handler(
        "Reddit",
        {"include_reddit": True},
        niche_name,
        geo,
        scrape_fn=lambda: collector.run_reddit_scraper(keywords=niche_name, geo=geo)
    )


@router.get("/news_trends")
def get_news_trends(niche_name: str = Query(None), geo: str = Query("US")):
    """Get NewsAPI trending topics."""
    return _platform_endpoint_handler(
        "News",
        {"include_news": True},
        niche_name,
        geo,
        scrape_fn=lambda: collector.run_news_scraper(query=niche_name or "news", geo=geo)
    )


@router.get("/all_trends")
def get_all_raw_trends(geo: str = Query("US")):
    """Return raw trend data without virality processing."""
    raw = collector.collect_all(geo=geo, include_trending_now=True, include_social=True, include_youtube=True, include_news=True)
    return {"data": sanitize_dataframe(raw)}

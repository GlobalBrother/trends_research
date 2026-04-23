"""Trend aggregation endpoints."""

import traceback
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from src.api.dependencies import (
    _cached,
    _get_niche_keywords_from_db,
    _sanitize,
    analytics,
    collector,
    logger,
    niche,
)
from src.api.schemas import TrendsResponse

router = APIRouter(tags=["trends"])


# ---------------------------------------------------------------------------
# Helpers used only by this router
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

    filtered = subset
    if niche_name:
        filtered = niche.filter_by_niche(subset, niche_name)
        # Graceful fallback: if the niche filter strips everything (common for
        # narrow niches against broad sources like HackerNews / News), fall
        # back to the unfiltered platform subset so the tab still shows data.
        if filtered.empty:
            filtered = subset

    if filtered.empty:
        return {"data": []}

    processed = analytics.process_trends(filtered)
    return {"data": _sanitize(processed)}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/trends", response_model=TrendsResponse)
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


@router.get("/trending_now", response_model=TrendsResponse)
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


@router.get("/youtube_trends", response_model=TrendsResponse)
def get_youtube_trends(niche_name: str = Query(...), geo: Optional[str] = Query(None)):
    # YouTube trends are always niche-specific in our implementation
    raw_data = collector.collect_all(geo=geo, include_youtube=True)

    needs_scrape = True
    if not raw_data.empty and 'platform' in raw_data.columns:
        yt_data = raw_data[raw_data['platform'] == "YouTube"]
        if not yt_data.empty:
            # Check if we have data for this niche (based on keywords)
            niche_keywords = _get_niche_keywords_from_db(niche_name)
            # Find if any keyword from this niche was recently scraped for YouTube
            # This is a bit loose but works for our purposes
            niche_yt_data = yt_data[yt_data['keyword'].isin(niche_keywords)]

            if not niche_yt_data.empty:
                last_extracted = pd.to_datetime(niche_yt_data['extracted_at']).max()
                if datetime.now() - last_extracted.to_pydatetime() < timedelta(hours=24):
                    needs_scrape = False

    if needs_scrape:
        niche_keywords = _get_niche_keywords_from_db(niche_name)
        # Use top 5 keywords to avoid too many requests
        success = collector.run_youtube_trends_scraper(keywords=niche_keywords[:5])
        if success:
            raw_data = collector.collect_all(include_youtube=True)

    if not raw_data.empty:
        yt_data = raw_data[raw_data['platform'] == "YouTube"].copy()
        if not yt_data.empty:
            # Re-filter for current niche to ensure relevance
            # We use niche_discovery to be robust
            processed_data = niche.filter_by_niche(yt_data, niche_name)
            if not processed_data.empty:
                processed_data = analytics.process_trends(processed_data)
                return {"data": _sanitize(processed_data)}

    return {"data": []}


@router.get("/hackernews_trends", response_model=TrendsResponse)
def get_hackernews_trends(niche_name: Optional[str] = Query(None), geo: Optional[str] = Query(None)):
    return _platform_endpoint(
        "HackerNews",
        {"include_hackernews": True},
        niche_name, geo,
        scrape_fn=lambda: collector.run_hackernews_scraper(
            keywords=_get_niche_keywords_from_db(niche_name) if niche_name else None,
        ),
    )


@router.get("/reddit_trends", response_model=TrendsResponse)
def get_reddit_trends(
    subreddit: str = Query("all"),
    trend_type: str = Query("hot"),
    niche_name: Optional[str] = Query(None),
    geo: Optional[str] = Query(None),
):
    return _platform_endpoint(
        "Reddit",
        {"include_reddit": True},
        niche_name, geo,
        scrape_fn=lambda: collector.run_reddit_scraper(
            subreddit=subreddit, trend_type=trend_type,
            keywords=_get_niche_keywords_from_db(niche_name) if niche_name else None,
        ),
    )


@router.get("/news_trends", response_model=TrendsResponse)
def get_news_trends(query: str = Query("niche"), niche_name: Optional[str] = Query(None), geo: Optional[str] = Query(None)):
    target_query = niche_name or query
    return _platform_endpoint(
        "News",
        {"include_news": True},
        niche_name, geo,
        scrape_fn=lambda: collector.run_news_scraper(query=target_query),
    )


@router.get("/all_trends", response_model=TrendsResponse)
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


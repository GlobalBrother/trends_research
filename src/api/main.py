from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import pandas as pd
import os
import sys

import logging
import traceback

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure the project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.collector.trend_collector import TrendCollector
from src.analytics.analytics_engine import AnalyticsEngine
from src.niche.niche_discovery import NicheDiscovery

app = FastAPI(title="Trends Research API")

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the Streamlit origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize modules
collector = TrendCollector()
analytics = AnalyticsEngine()
niche = NicheDiscovery()

class ScrapeRequest(BaseModel):
    niche: str
    geo: str = "US"
    timeframe: str = "today 12-m"
    category: int = 0

class TrendItem(BaseModel):
    platform: str
    topic: str
    growth: float
    sentiment: float
    virality_score: float
    niche_cluster: Optional[int] = None

@app.get("/")
def read_root():
    return {"message": "Trends Research API is running"}

@app.get("/niches", response_model=List[str])
def get_niches():
    return niche.get_available_niches()

@app.get("/niche_keywords/{niche_name}")
def get_niche_keywords(niche_name: str):
    keywords = niche.get_niche_keywords(niche_name)
    return {"niche": niche_name, "keywords": keywords}

@app.post("/scrape")
def scrape_niche(request: ScrapeRequest, background_tasks: BackgroundTasks):
    niche_keywords = niche.get_niche_keywords(request.niche)
    
    # Run comprehensive scrape in background to avoid timeouts
    background_tasks.add_task(
        collector.run_niche_comprehensive_scrape,
        niche_name=request.niche,
        keywords=niche_keywords,
        geo=request.geo,
        timeframe=request.timeframe,
        category=request.category
    )
    
    return {"message": f"Comprehensive scraping for {request.niche} started in background. Results will be available soon."}

import json
import time
import hashlib

# Simple in-memory cache for processed trends
_trends_cache = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes

def _get_cached_or_compute(cache_key, compute_fn):
    """Returns cached result if fresh, otherwise computes and caches."""
    now = time.time()
    if cache_key in _trends_cache:
        cached_time, cached_data = _trends_cache[cache_key]
        if now - cached_time < _CACHE_TTL_SECONDS:
            logger.info(f"Cache hit for {cache_key}")
            return cached_data
    result = compute_fn()
    _trends_cache[cache_key] = (now, result)
    return result

class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'tolist'):
            return obj.tolist()
        if isinstance(obj, (datetime, pd.Timestamp)):
            return obj.isoformat()
        if isinstance(obj, set):
            return list(obj)
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

def _sanitize_and_serialize(processed_data):
    """Replace NaN/Inf values and serialize DataFrame to JSON-compatible records."""
    processed_data = processed_data.copy()
    processed_data = processed_data.fillna("")
    processed_data = processed_data.replace([float('inf'), float('-inf')], None)
    records = processed_data.to_dict(orient="records")
    return json.loads(json.dumps(records, cls=JSONEncoder))

@app.get("/trends")
def get_trends(geo: Optional[str] = Query(None), niche_name: Optional[str] = Query(None)):
    try:
        # Normalize geo
        if geo == "" or geo == "None":
            geo = ""
        
        cache_key = f"trends_{geo}_{niche_name}"
        
        def _compute_trends():
            raw_data = collector.collect_all(
                geo=geo,
                include_trending_now=False if niche_name else True,
                include_youtube=True,
                include_social=True,
                include_hackernews=True,
                include_reddit=True,
                include_news=True
            )
            if raw_data.empty:
                return []
            
            processed_data = analytics.process_trends(raw_data)
            
            if niche_name:
                processed_data = niche.filter_by_niche(processed_data, niche_name)
            
            if len(processed_data) >= 5 and 'topic' in processed_data.columns:
                processed_data = niche.discover_micro_niches(processed_data)
                
            processed_data = processed_data.copy()
            
            if 'niche_cluster' in processed_data.columns:
                processed_data.loc[:, 'niche_cluster'] = processed_data['niche_cluster'].fillna(-1).astype(int)

            # Replace all remaining NaN/Inf values to ensure JSON compatibility
            processed_data = processed_data.fillna("")
            processed_data = processed_data.replace([float('inf'), float('-inf')], None)

            records = processed_data.to_dict(orient="records")
            return json.loads(json.dumps(records, cls=JSONEncoder))
        
        return {"data": _get_cached_or_compute(cache_key, _compute_trends)}
    except Exception as e:
        logger.error(f"Error in get_trends: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trending_now")
def get_trending_now(geo: str = Query("US"), trend_type: str = Query("daily")):
    # Normalize geo: Daily trends should never be "Global" for scraping
    # Default to "US" if "Global" or None is provided
    if geo == "None" or geo is None or geo == "Global" or geo == "":
        geo = "US"
        
    # Check if we have recent data (within 12 hours)
    raw_data = collector.collect_all(geo=geo, include_trending_now=True)
    
    needs_scrape = True
    if not raw_data.empty and 'extracted_at' in raw_data.columns:
        # Filter for trending_searches only
        trending_data = raw_data[raw_data['platform'] == "Google Trends"]
        if not trending_data.empty:
            last_extracted = pd.to_datetime(trending_data['extracted_at']).max()
            if datetime.now() - last_extracted.to_pydatetime() < timedelta(hours=12):
                needs_scrape = False
    
    if needs_scrape:
        success = collector.run_trending_now_scraper(geo=geo, trend_type=trend_type)
        if success:
            raw_data = collector.collect_all(geo=geo, include_trending_now=True)
        else:
            # Fallback if scraper fails - return empty data or existing data if any
            pass

    # Filter for trending searches specifically
    if not raw_data.empty:
        try:
            # Use .copy() to ensure we're not working on a slice
            trending_data = raw_data[raw_data['platform'] == "Google Trends"].copy()
            if not trending_data.empty:
                processed_data = analytics.process_trends(trending_data)
                
                # Replace NaN/Inf values to ensure JSON compatibility
                processed_data = processed_data.copy()
                processed_data = processed_data.fillna("")
                processed_data = processed_data.replace([float('inf'), float('-inf')], None)
                
                # Convert to records and handle non-serializable types
                records = processed_data.to_dict(orient="records")
                json_compatible_records = json.loads(json.dumps(records, cls=JSONEncoder))
                
                return {"data": json_compatible_records}
        except Exception as e:
            logger.error(f"Error in processing trending_now: {e}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e))
            
    return {"data": []}

@app.get("/youtube_trends")
def get_youtube_trends(niche_name: str = Query(...), geo: Optional[str] = Query(None)):
    # YouTube trends are always niche-specific in our implementation
    raw_data = collector.collect_all(geo=geo, include_youtube=True)
    
    needs_scrape = True
    if not raw_data.empty and 'platform' in raw_data.columns:
        yt_data = raw_data[raw_data['platform'] == "YouTube"]
        if not yt_data.empty:
            # Check if we have data for this niche (based on keywords)
            niche_keywords = niche.get_niche_keywords(niche_name)
            # Find if any keyword from this niche was recently scraped for YouTube
            # This is a bit loose but works for our purposes
            niche_yt_data = yt_data[yt_data['keyword'].isin(niche_keywords)]
            
            if not niche_yt_data.empty:
                last_extracted = pd.to_datetime(niche_yt_data['extracted_at']).max()
                if datetime.now() - last_extracted.to_pydatetime() < timedelta(hours=24):
                    needs_scrape = False
    
    if needs_scrape:
        niche_keywords = niche.get_niche_keywords(niche_name)
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
                return {"data": _sanitize_and_serialize(processed_data)}
                
    return {"data": []}

@app.get("/social_trends")
def get_social_trends(platform: str = Query(...), niche_name: str = Query(...), geo: Optional[str] = Query(None)):
    # platform: "X", "Threads", "Instagram"
    platform_map = {
        "X": "X (Twitter)",
        "Threads": "Threads",
        "Instagram": "Instagram"
    }
    target_platform = platform_map.get(platform)
    if not target_platform:
        raise HTTPException(status_code=400, detail="Invalid platform")

    raw_data = collector.collect_all(geo=geo, include_social=True)
    
    needs_scrape = True
    if not raw_data.empty and 'platform' in raw_data.columns:
        social_data = raw_data[raw_data['platform'] == target_platform]
        if not social_data.empty:
            niche_keywords = niche.get_niche_keywords(niche_name)
            niche_social_data = social_data[social_data['keyword'].isin(niche_keywords)]
            
            if not niche_social_data.empty:
                last_extracted = pd.to_datetime(niche_social_data['extracted_at']).max()
                if datetime.now() - last_extracted.to_pydatetime() < timedelta(hours=24):
                    needs_scrape = False
    
    if needs_scrape:
        niche_keywords = niche.get_niche_keywords(niche_name)
        success = collector.run_social_trends_scraper(platform=platform, keywords=niche_keywords[:3])
        if success:
            raw_data = collector.collect_all(include_social=True)

    if not raw_data.empty:
        social_data = raw_data[raw_data['platform'] == target_platform].copy()
        if not social_data.empty:
            processed_data = niche.filter_by_niche(social_data, niche_name)
            if not processed_data.empty:
                processed_data = analytics.process_trends(processed_data)
                return {"data": _sanitize_and_serialize(processed_data)}
                
    return {"data": []}

@app.get("/hackernews_trends")
def get_hackernews_trends(niche_name: Optional[str] = Query(None), geo: Optional[str] = Query(None)):
    # Check if we have recent data
    raw_data = collector.collect_all(geo=geo, include_hackernews=True)
    
    needs_scrape = True
    if not raw_data.empty and 'platform' in raw_data.columns:
        hn_data = raw_data[raw_data['platform'] == "HackerNews"]
        if not hn_data.empty:
            if niche_name:
                niche_keywords = niche.get_niche_keywords(niche_name)
                niche_hn_data = hn_data[hn_data['keyword'].isin(niche_keywords)]
                if not niche_hn_data.empty:
                    last_extracted = pd.to_datetime(niche_hn_data['extracted_at']).max()
                    if datetime.now() - last_extracted.to_pydatetime() < timedelta(hours=24):
                        needs_scrape = False
            else:
                last_extracted = pd.to_datetime(hn_data['extracted_at']).max()
                if datetime.now() - last_extracted.to_pydatetime() < timedelta(hours=1):
                    needs_scrape = False
    
    if needs_scrape:
        keywords = niche.get_niche_keywords(niche_name) if niche_name else None
        success = collector.run_hackernews_scraper(keywords=keywords)
        if success:
            raw_data = collector.collect_all(include_hackernews=True)

    if not raw_data.empty:
        hn_data = raw_data[raw_data['platform'] == "HackerNews"].copy()
        if not hn_data.empty:
            if niche_name:
                hn_data = niche.filter_by_niche(hn_data, niche_name)
            if not hn_data.empty:
                processed_data = analytics.process_trends(hn_data)
                return {"data": _sanitize_and_serialize(processed_data)}
                
    return {"data": []}

@app.get("/reddit_trends")
def get_reddit_trends(subreddit: str = Query("all"), trend_type: str = Query("hot"), niche_name: Optional[str] = Query(None), geo: Optional[str] = Query(None)):
    # Check if we have recent data
    raw_data = collector.collect_all(geo=geo, include_reddit=True)
    
    needs_scrape = True
    if not raw_data.empty and 'platform' in raw_data.columns:
        reddit_data = raw_data[raw_data['platform'] == "Reddit"]
        if not reddit_data.empty:
            if niche_name:
                niche_keywords = niche.get_niche_keywords(niche_name)
                niche_reddit_data = reddit_data[reddit_data['keyword'].isin(niche_keywords)]
                if not niche_reddit_data.empty:
                    last_extracted = pd.to_datetime(niche_reddit_data['extracted_at']).max()
                    if datetime.now() - last_extracted.to_pydatetime() < timedelta(hours=24):
                        needs_scrape = False
            else:
                last_extracted = pd.to_datetime(reddit_data['extracted_at']).max()
                if datetime.now() - last_extracted.to_pydatetime() < timedelta(hours=1):
                    needs_scrape = False
    
    if needs_scrape:
        keywords = niche.get_niche_keywords(niche_name) if niche_name else None
        success = collector.run_reddit_scraper(subreddit=subreddit, trend_type=trend_type, keywords=keywords)
        if success:
            raw_data = collector.collect_all(include_reddit=True)

    if not raw_data.empty:
        reddit_data = raw_data[raw_data['platform'] == "Reddit"].copy()
        if not reddit_data.empty:
            if niche_name:
                reddit_data = niche.filter_by_niche(reddit_data, niche_name)
            if not reddit_data.empty:
                processed_data = analytics.process_trends(reddit_data)
                return {"data": _sanitize_and_serialize(processed_data)}
                
    return {"data": []}

@app.get("/news_trends")
def get_news_trends(query: str = Query("niche"), niche_name: Optional[str] = Query(None), geo: Optional[str] = Query(None)):
    target_query = niche_name if niche_name else query
    raw_data = collector.collect_all(geo=geo, include_news=True)
    
    needs_scrape = True
    if not raw_data.empty and 'platform' in raw_data.columns:
        news_data = raw_data[raw_data['platform'] == "News"]
        if not news_data.empty:
            niche_news_data = news_data[news_data['keyword'].str.contains(target_query, case=False, na=False)]
            if not niche_news_data.empty:
                last_extracted = pd.to_datetime(niche_news_data['extracted_at']).max()
                if datetime.now() - last_extracted.to_pydatetime() < timedelta(hours=24):
                    needs_scrape = False

    if needs_scrape:
        success = collector.run_news_scraper(query=target_query)
        if success:
            raw_data = collector.collect_all(include_news=True)

    if not raw_data.empty:
        news_data = raw_data[raw_data['platform'] == "News"].copy()
        if not news_data.empty:
            if niche_name:
                news_data = niche.filter_by_niche(news_data, niche_name)
            if not news_data.empty:
                processed_data = analytics.process_trends(news_data)
                return {"data": _sanitize_and_serialize(processed_data)}
                
    return {"data": []}

@app.get("/all_trends")
def get_all_trends():
    raw_data = collector.collect_all(
        include_trending_now=True, 
        include_youtube=True, 
        include_social=True, 
        include_hackernews=True, 
        include_reddit=True,
        include_news=True
    )
    
    if not raw_data.empty:
        processed_data = analytics.process_trends(raw_data)
        return {"data": _sanitize_and_serialize(processed_data)}
    return {"data": []}

@app.get("/scrape_errors")
def get_scrape_errors(platform: Optional[str] = Query(None)):
    df = collector.get_scrape_errors(platform=platform)
    if not df.empty:
        return {"data": _sanitize_and_serialize(df)}
    return {"data": []}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

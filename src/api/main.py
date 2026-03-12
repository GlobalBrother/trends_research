from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import pandas as pd
import os
import sys

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
    return ["Survival", "Health", "Preppers", "Sustainability", "Homesteading"]

@app.get("/niche_keywords/{niche_name}")
def get_niche_keywords(niche_name: str):
    keywords = niche.get_niche_keywords(niche_name)
    return {"niche": niche_name, "keywords": keywords}

@app.post("/scrape")
def scrape_niche(request: ScrapeRequest):
    niche_keywords = niche.get_niche_keywords(request.niche)
    success = collector.run_google_trends_scraper(
        keywords=niche_keywords,
        geo=request.geo,
        timeframe=request.timeframe,
        category=request.category
    )
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to scrape {request.niche}")
    return {"message": f"Successfully scraped {request.niche}"}

@app.get("/trends")
def get_trends(geo: Optional[str] = Query(None), niche_name: Optional[str] = Query(None)):
    # Normalize geo: empty string or "None" string from frontend means we want specifically Global data ("")
    # if geo is literal None (not provided), we return everything.
    if geo == "" or geo == "None":
        geo = ""
        
    raw_data = collector.collect_all(
        geo=geo,
        include_trending_now=True,
        include_youtube=True,
        include_social=True,
        include_hackernews=True,
        include_reddit=True,
        include_news=True,
        include_stackexchange=True
    )
    if raw_data.empty:
        return {"data": []}
    
    processed_data = analytics.process_trends(raw_data)
    
    if niche_name:
        processed_data = niche.filter_by_niche(processed_data, niche_name)
    
    # Discover micro-niches if enough data
    if len(processed_data) >= 5:
        processed_data = niche.discover_micro_niches(processed_data)
        
    # Replace NaN values with appropriate defaults before JSON serialization
    # Pydantic/FastAPI don't handle 'NaN' (Not a Number) well in JSON response.
    # Use .loc to avoid SettingWithCopyWarning
    processed_data = processed_data.copy()
    processed_data = processed_data.fillna(0)
    
    # Explicitly ensure integers for clustering if it exists
    if 'niche_cluster' in processed_data.columns:
        processed_data.loc[:, 'niche_cluster'] = processed_data['niche_cluster'].astype(int)
        
    return {"data": processed_data.to_dict(orient="records")}

@app.get("/trending_now")
def get_trending_now(geo: str = Query("US"), trend_type: str = Query("daily")):
    # Normalize geo: "None" or "" means Global for Google RSS
    if geo == "None" or geo is None:
        geo = ""
        
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
        # Use .copy() to ensure we're not working on a slice
        trending_data = raw_data[raw_data['platform'] == "Google Trends"].copy()
        if not trending_data.empty:
            processed_data = analytics.process_trends(trending_data)
            processed_data = processed_data.fillna(0)
            return {"data": processed_data.to_dict(orient="records")}
            
    return {"data": []}

@app.get("/youtube_trends")
def get_youtube_trends(niche_name: str = Query(...)):
    # YouTube trends are always niche-specific in our implementation
    raw_data = collector.collect_all(include_youtube=True)
    
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
                processed_data = processed_data.fillna(0)
                # Ensure URL and published date are in the response
                return {"data": processed_data.to_dict(orient="records")}
                
    return {"data": []}

@app.get("/social_trends")
def get_social_trends(platform: str = Query(...), niche_name: str = Query(...)):
    # platform: "X", "Threads", "Instagram"
    platform_map = {
        "X": "X (Twitter)",
        "Threads": "Threads",
        "Instagram": "Instagram"
    }
    target_platform = platform_map.get(platform)
    if not target_platform:
        raise HTTPException(status_code=400, detail="Invalid platform")

    raw_data = collector.collect_all(include_social=True)
    
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
                processed_data = processed_data.fillna(0)
                return {"data": processed_data.to_dict(orient="records")}
                
    return {"data": []}

@app.get("/hackernews_trends")
def get_hackernews_trends():
    # Check if we have recent data (within 1 hour)
    raw_data = collector.collect_all(include_hackernews=True)
    
    needs_scrape = True
    if not raw_data.empty and 'platform' in raw_data.columns:
        hn_data = raw_data[raw_data['platform'] == "HackerNews"]
        if not hn_data.empty:
            last_extracted = pd.to_datetime(hn_data['extracted_at']).max()
            if datetime.now() - last_extracted.to_pydatetime() < timedelta(hours=1):
                needs_scrape = False
    
    if needs_scrape:
        success = collector.run_hackernews_scraper()
        if success:
            raw_data = collector.collect_all(include_hackernews=True)

    if not raw_data.empty:
        hn_data = raw_data[raw_data['platform'] == "HackerNews"].copy()
        if not hn_data.empty:
            processed_data = analytics.process_trends(hn_data)
            processed_data = processed_data.fillna(0)
            return {"data": processed_data.to_dict(orient="records")}
                
    return {"data": []}

@app.get("/reddit_trends")
def get_reddit_trends(subreddit: str = Query("all"), trend_type: str = Query("hot")):
    # Check if we have recent data (within 1 hour)
    raw_data = collector.collect_all(include_reddit=True)
    
    needs_scrape = True
    if not raw_data.empty and 'platform' in raw_data.columns:
        reddit_data = raw_data[raw_data['platform'] == "Reddit"]
        if not reddit_data.empty:
            # Check if we have data for this specific subreddit/trend_type if possible,
            # but for now just check if we have any Reddit data recently.
            last_extracted = pd.to_datetime(reddit_data['extracted_at']).max()
            if datetime.now() - last_extracted.to_pydatetime() < timedelta(hours=1):
                needs_scrape = False
    
    if needs_scrape:
        success = collector.run_reddit_scraper(subreddit=subreddit, trend_type=trend_type)
        if success:
            raw_data = collector.collect_all(include_reddit=True)

    if not raw_data.empty:
        reddit_data = raw_data[raw_data['platform'] == "Reddit"].copy()
        if not reddit_data.empty:
            processed_data = analytics.process_trends(reddit_data)
            processed_data = processed_data.fillna(0)
            return {"data": processed_data.to_dict(orient="records")}
                
    return {"data": []}

@app.get("/news_trends")
def get_news_trends(query: str = Query("niche")):
    raw_data = collector.collect_all(include_news=True)
    
    # Always scrape news for the specific query for now, or check cache
    success = collector.run_news_scraper(query=query)
    if success:
        raw_data = collector.collect_all(include_news=True)

    if not raw_data.empty:
        news_data = raw_data[raw_data['platform'] == "News"].copy()
        if not news_data.empty:
            processed_data = analytics.process_trends(news_data)
            processed_data = processed_data.fillna(0)
            return {"data": processed_data.to_dict(orient="records")}
                
    return {"data": []}

@app.get("/stackexchange_trends")
def get_stackexchange_trends(site: str = Query("stackoverflow"), sort: str = Query("hot")):
    raw_data = collector.collect_all(include_stackexchange=True)
    
    success = collector.run_stackexchange_scraper(site=site, sort=sort)
    if success:
        raw_data = collector.collect_all(include_stackexchange=True)

    if not raw_data.empty:
        se_data = raw_data[raw_data['platform'] == "StackExchange"].copy()
        if not se_data.empty:
            processed_data = analytics.process_trends(se_data)
            processed_data = processed_data.fillna(0)
            return {"data": processed_data.to_dict(orient="records")}
                
    return {"data": []}

@app.get("/all_trends")
def get_all_trends():
    raw_data = collector.collect_all(
        include_trending_now=True, 
        include_youtube=True, 
        include_social=True, 
        include_hackernews=True, 
        include_reddit=True,
        include_news=True,
        include_stackexchange=True
    )
    
    if not raw_data.empty:
        processed_data = analytics.process_trends(raw_data)
        processed_data = processed_data.fillna(0)
        return {"data": processed_data.to_dict(orient="records")}
                
    return {"data": []}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

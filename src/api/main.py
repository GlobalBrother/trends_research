from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
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
def get_trends(geo: str = "US", niche_name: Optional[str] = None):
    raw_data = collector.collect_all(geo=geo)
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
    processed_data = processed_data.copy()
    processed_data = processed_data.fillna(0)
    
    # Explicitly ensure integers for clustering if it exists
    if 'niche_cluster' in processed_data.columns:
        processed_data['niche_cluster'] = processed_data['niche_cluster'].astype(int)
        
    return {"data": processed_data.to_dict(orient="records")}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

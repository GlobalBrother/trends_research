from fastapi import FastAPI, File, HTTPException, Query, BackgroundTasks, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import pandas as pd
import os
import sys
import sqlite3
import secrets

import logging
import traceback
import resend
from dotenv import load_dotenv

load_dotenv()

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

# Try to import GetHookdAI ads scraper
try:
    _gha_dir = os.path.join(project_root, "src", "scrapers", "gethookedai")
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

DB_PATH = os.path.join(project_root, "src", "collector", "trends.db")

# Resend API config
resend.api_key = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "noreply@yourdomain.com")

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

# ---------------------------------------------------------------------------
# Auth: users & OTP tables
# ---------------------------------------------------------------------------

def _init_auth_tables():
    """Create auth tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            role TEXT NOT NULL DEFAULT 'trends',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS otp_codes (
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            used INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS auth_tokens (
            token TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

_init_auth_tables()


def _init_token_usage_table():
    """Create token_usage table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS token_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            keyword TEXT,
            units_charged REAL NOT NULL DEFAULT 0,
            geo TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

_init_token_usage_table()


class ScrapeRequest(BaseModel):
    niche: str
    geo: str = "US"
    timeframe: str = "today 12-m"
    category: int = 0
    scraper_type: str = "all"

class TrendItem(BaseModel):
    platform: str
    topic: str
    growth: float
    sentiment: float
    virality_score: float
    niche_cluster: Optional[int] = None

class UserCreate(BaseModel):
    email: str
    role: str = "trends"  # "admin" or "trends"


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/auth/request_otp")
def request_otp(email: str = Query(...)):
    """Send an OTP code to a whitelisted email via Resend."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT email, role FROM users WHERE email = ?", (email,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=403, detail="Email not whitelisted")

    code = secrets.token_hex(3).upper()  # 6-char hex code
    conn.execute("INSERT INTO otp_codes (email, code) VALUES (?, ?)", (email, code))
    conn.commit()
    conn.close()

    try:
        resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": [email],
            "subject": "Your Trends Research login code",
            "html": f"<p>Your one-time login code is: <strong>{code}</strong></p>"
                   f"<p>This code expires in 10 minutes.</p>",
        })
    except Exception as e:
        logger.error(f"Failed to send OTP email to {email}: {e}")
        raise HTTPException(status_code=500, detail="Failed to send OTP email")

    return {"message": "OTP sent", "email": email}


@app.post("/auth/verify_otp")
def verify_otp(email: str = Query(...), code: str = Query(...)):
    """Verify an OTP code and return the user's role."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT rowid, code FROM otp_codes WHERE email = ? AND code = ? AND used = 0 "
        "AND datetime(created_at, '+10 minutes') > datetime('now') "
        "ORDER BY created_at DESC LIMIT 1",
        (email, code.upper()),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid or expired OTP")

    conn.execute("UPDATE otp_codes SET used = 1 WHERE rowid = ?", (row[0],))
    user = conn.execute("SELECT role FROM users WHERE email = ?", (email,)).fetchone()
    conn.commit()
    conn.close()

    # Generate auth token valid for 12 hours
    token = secrets.token_hex(32)
    expires_at = (datetime.utcnow() + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
    conn2 = sqlite3.connect(DB_PATH)
    conn2.execute(
        "INSERT INTO auth_tokens (token, email, role, expires_at) VALUES (?, ?, ?, ?)",
        (token, email, user[0], expires_at),
    )
    conn2.commit()
    conn2.close()

    return {"message": "Authenticated", "email": email, "role": user[0], "token": token}


@app.get("/auth/validate_token")
def validate_token(token: str = Query(...)):
    """Validate an auth token and return user info if still valid."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT email, role FROM auth_tokens "
        "WHERE token = ? AND datetime(expires_at) > datetime('now')",
        (token,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"email": row[0], "role": row[1]}


@app.get("/auth/users")
def list_users():
    """List all whitelisted users."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT email, role, created_at FROM users ORDER BY created_at").fetchall()
    conn.close()
    return [{"email": r[0], "role": r[1], "created_at": r[2]} for r in rows]


@app.post("/auth/users")
def add_user(user: UserCreate):
    """Add a whitelisted user."""
    if user.role not in ("admin", "trends"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'trends'")
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO users (email, role) VALUES (?, ?)", (user.email, user.role))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="User already exists")
    conn.close()
    return {"message": "User added", "email": user.email, "role": user.role}


@app.put("/auth/users")
def update_user_role(email: str = Query(...), role: str = Query(...)):
    """Update a user's role."""
    if role not in ("admin", "trends"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'trends'")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("UPDATE users SET role = ? WHERE email = ?", (role, email))
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    conn.close()
    return {"message": "Role updated", "email": email, "role": role}


@app.delete("/auth/users")
def delete_user(email: str = Query(...)):
    """Remove a whitelisted user."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("DELETE FROM users WHERE email = ?", (email,))
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    conn.close()
    return {"message": "User removed", "email": email}


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
    scraper = request.scraper_type

    if scraper == "all":
        background_tasks.add_task(
            collector.run_niche_comprehensive_scrape,
            niche_name=request.niche,
            keywords=niche_keywords,
            geo=request.geo,
            timeframe=request.timeframe,
            category=request.category
        )
    elif scraper == "google_trends":
        background_tasks.add_task(
            collector.run_google_trends_scraper,
            niche_keywords, geo=request.geo,
            timeframe=request.timeframe, category=request.category
        )
    elif scraper == "daily":
        background_tasks.add_task(
            collector.run_trending_now_scraper,
            geo=request.geo
        )
    elif scraper == "youtube":
        background_tasks.add_task(
            collector.run_youtube_trends_scraper,
            niche_keywords, geo=request.geo
        )
    elif scraper in ("Threads", "Instagram", "TikTok"):
        background_tasks.add_task(
            collector.run_social_trends_scraper,
            scraper, niche_keywords, geo=request.geo
        )
    elif scraper == "hackernews":
        background_tasks.add_task(
            collector.run_hackernews_scraper,
            keywords=niche_keywords, geo=request.geo
        )
    elif scraper == "reddit":
        background_tasks.add_task(
            collector.run_reddit_scraper,
            keywords=niche_keywords, geo=request.geo
        )
    elif scraper == "news":
        background_tasks.add_task(
            collector.run_news_scraper,
            query=request.niche, geo=request.geo
        )
    else:
        background_tasks.add_task(
            collector.run_niche_comprehensive_scrape,
            niche_name=request.niche,
            keywords=niche_keywords,
            geo=request.geo,
            timeframe=request.timeframe,
            category=request.category
        )

    return {"message": f"Scraping ({scraper}) for {request.niche} started in background. Results will be available soon."}


@app.post("/import_tokens")
async def import_tokens(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    geo: str = Query("US"),
):
    """
    Import a Google Trends JSON file downloaded manually when the API returns 429.
    Parses widget tokens and fetches data using those tokens directly.
    """
    try:
        content = await file.read()
        text = content.decode("utf-8")

        # Strip Google's XSSI prefix which can appear in various forms:
        # )]}'\n{...}  or  )\n]\n}'\n{...}  or  )]}',\n{...}
        # Find the first '{' which starts the actual JSON object
        brace_idx = text.find("{")
        if brace_idx > 0:
            text = text[brace_idx:]

        data = json.loads(text)
        widgets = data.get("widgets", [])
        if not widgets:
            raise HTTPException(status_code=400, detail="No widgets found in the uploaded JSON file.")

        # Extract keyword from the JSON
        keywords_info = data.get("keywords", [])
        keyword = keywords_info[0].get("keyword", "Unknown") if keywords_info else "Unknown"

        # Extract geo from widget requests if not provided
        for w in widgets:
            req = w.get("request", {})
            widget_geo = req.get("geo", {}).get("country") or req.get("restriction", {}).get("geo", {}).get("country")
            if widget_geo:
                geo = widget_geo
                break

        widgets_json = json.dumps(widgets)

        background_tasks.add_task(
            collector.run_token_import,
            widgets_json=widgets_json,
            geo=geo,
            keyword=keyword,
        )

        return {
            "message": f"Token import started for keyword '{keyword}' (geo={geo}). "
                       f"Found {len(widgets)} widget(s). Data will be available soon."
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
                processed_data['niche_cluster'] = pd.array(processed_data['niche_cluster'].fillna(-1).astype(int), dtype=pd.Int64Dtype())

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

# ---------------------------------------------------------------------------
# Helper: run a query against a dedicated platform table
# ---------------------------------------------------------------------------

def _query_platform_table(query: str, params: list):
    """Execute a SELECT query against the DB and return JSON-safe records."""
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return _sanitize_and_serialize(df) if not df.empty else []
    except Exception as e:
        logger.error(f"DB query error: {e}")
        return []


def _geo_clause(col: str = "geo"):
    return f" AND (UPPER({col}) = UPPER(?) OR {col} = '' OR UPPER({col}) = 'GLOBAL' OR {col} IS NULL)"


def _keyword_clause(keywords: list, col: str = "search_keyword"):
    if not keywords:
        return "", []
    placeholders = ", ".join(["?"] * len(keywords))
    return f" AND {col} IN ({placeholders})", list(keywords)


# ---------------------------------------------------------------------------
# Table filters (dynamic dropdowns)
# ---------------------------------------------------------------------------

@app.get("/table_filters")
def get_table_filters(
    table_name: str = Query(...),
    geo_col: str = Query("geo"),
    keyword_col: str = Query("search_keyword"),
):
    """Return distinct geo and keyword values from a given DB table."""
    geos, keywords = ["Global"], ["All"]
    if not os.path.exists(DB_PATH):
        return {"geos": geos, "keywords": keywords}
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Sanitise column/table names (allow only alphanumeric + underscore)
        import re
        _safe = re.compile(r"^\w+$")
        if not _safe.match(table_name) or not _safe.match(geo_col) or not _safe.match(keyword_col):
            raise HTTPException(status_code=400, detail="Invalid table/column name")

        cursor.execute(f"SELECT DISTINCT {geo_col} FROM {table_name} WHERE {geo_col} IS NOT NULL AND {geo_col} != ''")
        geos_raw = sorted(set(r[0] for r in cursor.fetchall() if r[0]))
        if geos_raw:
            geos = ["All"] + geos_raw

        cursor.execute(f"SELECT DISTINCT {keyword_col} FROM {table_name} WHERE {keyword_col} IS NOT NULL AND {keyword_col} != ''")
        kw_raw = sorted(set(r[0] for r in cursor.fetchall() if r[0]))
        if kw_raw:
            keywords = ["All"] + kw_raw
        conn.close()
    except HTTPException:
        raise
    except Exception:
        pass
    return {"geos": geos, "keywords": keywords}


# ---------------------------------------------------------------------------
# YouTube videos (dedicated table)
# ---------------------------------------------------------------------------

@app.get("/youtube_videos")
def get_youtube_videos(
    niche_name: Optional[str] = Query(None),
    geo: Optional[str] = Query(None),
    limit: int = Query(500),
):
    query = """
        SELECT video_id, title, description, search_keyword, geo,
               channel_title, channel_id, published, duration, url,
               thumbnail_url, tags, language,
               view_count, like_count, dislike_count, comment_count,
               favorite_count, engagement_total,
               extracted_at
        FROM youtube_videos WHERE 1=1
    """
    params = []
    if geo and geo != "Global":
        query += _geo_clause()
        params.append(geo)
    if niche_name:
        kws = niche.get_niche_keywords(niche_name)
        clause, kw_params = _keyword_clause(kws)
        query += clause
        params.extend(kw_params)
    query += f" ORDER BY view_count DESC LIMIT {limit}"
    data = _query_platform_table(query, params)
    # Post-process tags
    for row in data:
        tags = row.get("tags")
        if tags and isinstance(tags, str) and tags.startswith("["):
            try:
                row["tags"] = ", ".join(json.loads(tags))
            except Exception:
                pass
    return {"data": data}


# ---------------------------------------------------------------------------
# TikTok videos (dedicated table)
# ---------------------------------------------------------------------------

@app.get("/tiktok_videos")
def get_tiktok_videos(
    niche_name: Optional[str] = Query(None),
    geo: Optional[str] = Query(None),
    limit: int = Query(500),
):
    query = """
        SELECT aweme_id, description, search_keyword, geo, region,
               create_time, duration, share_url,
               digg_count, comment_count, share_count, play_count,
               download_count, collect_count, engagement_total,
               author_unique_id, author_nickname, author_follower_count,
               author_verified,
               music_title, music_author,
               hashtags, video_ratio,
               extracted_at
        FROM tiktok_videos WHERE 1=1
    """
    params = []
    if geo and geo != "Global":
        query += _geo_clause()
        params.append(geo)
    if niche_name:
        kws = niche.get_niche_keywords(niche_name)
        clause, kw_params = _keyword_clause(kws)
        query += clause
        params.extend(kw_params)
    query += f" ORDER BY play_count DESC LIMIT {limit}"
    data = _query_platform_table(query, params)
    for row in data:
        ht = row.get("hashtags")
        if ht and isinstance(ht, str):
            try:
                row["hashtags"] = ", ".join(json.loads(ht))
            except Exception:
                pass
        ct = row.get("create_time")
        if ct:
            try:
                row["created"] = datetime.utcfromtimestamp(int(ct)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
    return {"data": data}


# ---------------------------------------------------------------------------
# Instagram posts (dedicated table)
# ---------------------------------------------------------------------------

@app.get("/instagram_posts")
def get_instagram_posts(
    niche_name: Optional[str] = Query(None),
    geo: Optional[str] = Query(None),
    limit: int = Query(500),
):
    query = """
        SELECT post_pk, shortcode, search_keyword, geo,
               caption, media_type, url, thumbnail_url, taken_at,
               location_name,
               username, full_name, follower_count, is_verified,
               like_count, comment_count, share_count, save_count,
               video_view_count, video_play_count,
               engagement_total, hashtags,
               extracted_at
        FROM instagram_posts WHERE 1=1
    """
    params = []
    if geo and geo != "Global":
        query += _geo_clause()
        params.append(geo)
    if niche_name:
        kws = niche.get_niche_keywords(niche_name)
        clause, kw_params = _keyword_clause(kws)
        query += clause
        params.extend(kw_params)
    query += f" ORDER BY like_count DESC LIMIT {limit}"
    data = _query_platform_table(query, params)
    for row in data:
        ta = row.get("taken_at")
        if ta:
            try:
                row["posted"] = datetime.utcfromtimestamp(int(ta)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        ht = row.get("hashtags")
        if ht and isinstance(ht, str) and ht.startswith("["):
            try:
                row["hashtags"] = ", ".join(json.loads(ht))
            except Exception:
                pass
    return {"data": data}


# ---------------------------------------------------------------------------
# Reddit posts (dedicated table)
# ---------------------------------------------------------------------------

@app.get("/reddit_posts")
def get_reddit_posts(
    niche_name: Optional[str] = Query(None),
    geo: Optional[str] = Query(None),
    limit: int = Query(500),
):
    query = """
        SELECT post_id, title, selftext, search_keyword, geo,
               url, permalink, domain,
               subreddit, author,
               score, upvote_ratio, num_comments, num_crossposts, total_awards,
               engagement_total, link_flair_text,
               created_utc, extracted_at
        FROM reddit_posts WHERE 1=1
    """
    params = []
    if geo and geo != "Global":
        query += _geo_clause()
        params.append(geo)
    if niche_name:
        kws = niche.get_niche_keywords(niche_name)
        clause, kw_params = _keyword_clause(kws)
        query += clause
        params.extend(kw_params)
    query += f" ORDER BY score DESC LIMIT {limit}"
    data = _query_platform_table(query, params)
    for row in data:
        cu = row.get("created_utc")
        if cu:
            try:
                row["posted"] = datetime.utcfromtimestamp(int(cu)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
    return {"data": data}


# ---------------------------------------------------------------------------
# Threads posts (dedicated table)
# ---------------------------------------------------------------------------

@app.get("/threads_posts")
def get_threads_posts(
    niche_name: Optional[str] = Query(None),
    geo: Optional[str] = Query(None),
    limit: int = Query(500),
):
    query = """
        SELECT post_code, search_keyword, geo,
               caption, url, taken_at, media_type,
               username, full_name, follower_count, is_verified,
               like_count, reply_count, repost_count, quote_count, share_count,
               engagement_total,
               extracted_at
        FROM threads_posts WHERE 1=1
    """
    params = []
    if geo and geo != "Global":
        query += _geo_clause()
        params.append(geo)
    if niche_name:
        kws = niche.get_niche_keywords(niche_name)
        clause, kw_params = _keyword_clause(kws)
        query += clause
        params.extend(kw_params)
    query += f" ORDER BY like_count DESC LIMIT {limit}"
    data = _query_platform_table(query, params)
    for row in data:
        ta = row.get("taken_at")
        if ta:
            try:
                row["posted"] = datetime.utcfromtimestamp(int(ta)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
    return {"data": data}


# ---------------------------------------------------------------------------
# Ads insight (dedicated table)
# ---------------------------------------------------------------------------

@app.get("/ads_insight")
def get_ads_insight(
    niche_name: Optional[str] = Query(None),
    geo: Optional[str] = Query(None),
    limit: int = Query(500),
):
    query = """
        SELECT hookd_id, external_id, search_keyword,
               platform, display_format, title, body,
               landing_page, link_description, cta_type, cta_text,
               start_date, end_date, days_active, active_in_library,
               performance_score, performance_score_title, used_count,
               age_audience_min, age_audience_max, gender_audience, eu_total_reach,
               ad_spend_range_score, ad_spend_range_score_title,
               brand_name, brand_logo_url, brand_active_ads,
               media, ad_cards, share_url,
               extracted_at
        FROM ads_insight WHERE 1=1
    """
    params = []
    if niche_name:
        kws = niche.get_niche_keywords(niche_name)
        clause, kw_params = _keyword_clause(kws)
        query += clause
        params.extend(kw_params)
    query += " ORDER BY extracted_at DESC LIMIT ?"
    params.append(limit)
    return {"data": _query_platform_table(query, params)}


# ---------------------------------------------------------------------------
# Ads scraping endpoints
# ---------------------------------------------------------------------------

@app.post("/scrape_ads")
def scrape_ads_endpoint(
    background_tasks: BackgroundTasks,
    keywords: str = Query(..., description="Comma-separated keywords"),
    max_pages: int = Query(3),
):
    if not HAS_GETHOOKEDAI:
        raise HTTPException(status_code=501, detail="GetHookdAI scraper not available")
    kws = [k.strip() for k in keywords.split(",") if k.strip()]
    if not kws:
        raise HTTPException(status_code=400, detail="No keywords provided")
    background_tasks.add_task(gethookd_scrape_ads, kws, max_pages=max_pages)
    return {"message": f"Ads scrape started for: {', '.join(kws)}"}


@app.get("/search_brands")
def search_brands_endpoint(query: str = Query(..., description="Brand name to search")):
    if not HAS_GETHOOKEDAI:
        raise HTTPException(status_code=501, detail="GetHookdAI scraper not available")
    try:
        brands = gethookd_search_brands(query)
        return {"data": brands}
    except Exception as e:
        logger.error(f"Brand search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scrape_brand_ads")
def scrape_brand_ads_endpoint(
    background_tasks: BackgroundTasks,
    brand_id: int = Query(...),
):
    if not HAS_GETHOOKEDAI:
        raise HTTPException(status_code=501, detail="GetHookdAI scraper not available")
    background_tasks.add_task(gethookd_scrape_brand_ads, brand_id)
    return {"message": f"Brand spy started for brand {brand_id}"}


# ---------------------------------------------------------------------------
# Clear scrape errors
# ---------------------------------------------------------------------------

@app.delete("/scrape_errors")
def clear_scrape_errors():
    if not os.path.exists(DB_PATH):
        return {"ok": True}
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM scrape_errors")
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to clear scrape_errors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Token usage (EnsembleData units consumed)
# ---------------------------------------------------------------------------

@app.get("/admin/token_usage")
def get_token_usage():
    """Return token/units consumption grouped by platform."""
    if not os.path.exists(DB_PATH):
        return {"data": [], "summary": []}
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # Detailed rows
        rows = conn.execute(
            "SELECT platform, keyword, units_charged, geo, created_at "
            "FROM token_usage ORDER BY created_at DESC LIMIT 1000"
        ).fetchall()
        data = [dict(r) for r in rows]

        # Summary per platform
        summary = conn.execute(
            "SELECT platform, SUM(units_charged) as total_units, COUNT(*) as request_count "
            "FROM token_usage GROUP BY platform ORDER BY total_units DESC"
        ).fetchall()
        summary_data = [dict(r) for r in summary]

        conn.close()
        return {"data": data, "summary": summary_data}
    except Exception as e:
        logger.error(f"Failed to fetch token usage: {e}")
        return {"data": [], "summary": []}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

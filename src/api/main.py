from fastapi import FastAPI, File, HTTPException, Query, BackgroundTasks, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import pandas as pd
import os
import sys
import secrets

import logging
import traceback
import resend
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

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
from src.db.connection import get_engine, is_sqlite
from src.db.sql_compat import otp_verify_sql, expires_check, insert_if_not_exists_niches, limit_clause, tbl

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

engine = get_engine()

# Resend API config
resend.api_key = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "noreply@yourdomain.com")

# Test account that bypasses OTP (for development/testing)
TEST_ACCOUNT_EMAIL = os.getenv("TEST_ACCOUNT_EMAIL", "").strip()
TEST_ACCOUNT_OTP = os.getenv("TEST_ACCOUNT_OTP", "000000").strip()

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
    """Ensure auth tables exist.

    SQLite  – run the full schema file (all CREATE IF NOT EXISTS).
    Azure SQL – tables are pre-created via the migration schema.
    """
    if not is_sqlite():
        return
    schema_file = os.path.join(project_root, "src", "db", "sqlite_schema.sql")
    if os.path.exists(schema_file):
        with open(schema_file, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        raw_url = str(engine.url)
        # Extract path from sqlite:///path
        db_path = raw_url.replace("sqlite:///", "")
        import sqlite3
        _conn = sqlite3.connect(db_path)
        _conn.executescript(schema_sql)
        _conn.close()
        logger.info("SQLite schema applied from %s", schema_file)

_init_auth_tables()


def _init_token_usage_table():
    """Ensure token_usage table exists (Azure SQL – tables created via migration schema)."""
    pass

_init_token_usage_table()


def _init_niches_table():
    """Seed niches table with defaults if empty."""
    try:
        with engine.connect() as conn:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {tbl('niches')}")).scalar()
            if count == 0:
                _nd = NicheDiscovery()
                for niche_name, keywords in _nd.niche_map.items():
                    for kw in keywords:
                        conn.execute(
                            text(insert_if_not_exists_niches()),
                            {"niche_name": niche_name, "kw": kw},
                        )
                conn.commit()
    except Exception as e:
        logger.warning(f"Could not seed niches table: {e}")

_init_niches_table()


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
    # Test account bypass: auto-create user and skip email
    if TEST_ACCOUNT_EMAIL and email == TEST_ACCOUNT_EMAIL:
        with engine.connect() as conn:
            row = conn.execute(text(f"SELECT email FROM {tbl('users')} WHERE email = :email"), {"email": email}).fetchone()
            if not row:
                conn.execute(text(f"INSERT INTO {tbl('users')} (email, role) VALUES (:email, :role)"), {"email": email, "role": "admin"})
            conn.execute(text(f"INSERT INTO {tbl('otp_codes')} (email, code) VALUES (:email, :code)"), {"email": email, "code": TEST_ACCOUNT_OTP})
            conn.commit()
        return {"message": "OTP sent", "email": email}

    with engine.connect() as conn:
        row = conn.execute(text(f"SELECT email, role FROM {tbl('users')} WHERE email = :email"), {"email": email}).fetchone()
        if not row:
            raise HTTPException(status_code=403, detail="Email not whitelisted")

        code = secrets.token_hex(3).upper()  # 6-char hex code
        conn.execute(text(f"INSERT INTO {tbl('otp_codes')} (email, code) VALUES (:email, :code)"), {"email": email, "code": code})
        conn.commit()

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
    with engine.connect() as conn:
        row = conn.execute(
            text(otp_verify_sql()),
            {"email": email, "code": code.upper()},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid or expired OTP")

        conn.execute(text(f"UPDATE {tbl('otp_codes')} SET used = 1 WHERE id = :id"), {"id": row[0]})
        user = conn.execute(text(f"SELECT role FROM {tbl('users')} WHERE email = :email"), {"email": email}).fetchone()
        conn.commit()

    # Generate auth token valid for 12 hours
    token = secrets.token_hex(32)
    expires_at = (datetime.utcnow() + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
    with engine.connect() as conn:
        conn.execute(
            text(f"INSERT INTO {tbl('auth_tokens')} (token, email, role, expires_at) VALUES (:token, :email, :role, :expires_at)"),
            {"token": token, "email": email, "role": user[0], "expires_at": expires_at},
        )
        conn.commit()

    return {"message": "Authenticated", "email": email, "role": user[0], "token": token}


@app.get("/auth/validate_token")
def validate_token(token: str = Query(...)):
    """Validate an auth token and return user info if still valid."""
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT email, role FROM {tbl('auth_tokens')} WHERE token = :token AND {expires_check('expires_at')}"),
            {"token": token},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"email": row[0], "role": row[1]}


@app.get("/auth/users")
def list_users():
    """List all whitelisted users."""
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT email, role, created_at FROM {tbl('users')} ORDER BY created_at")).fetchall()
    return [{"email": r[0], "role": r[1], "created_at": r[2]} for r in rows]


@app.post("/auth/users")
def add_user(user: UserCreate):
    """Add a whitelisted user."""
    if user.role not in ("admin", "trends"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'trends'")
    try:
        with engine.connect() as conn:
            conn.execute(text(f"INSERT INTO {tbl('users')} (email, role) VALUES (:email, :role)"), {"email": user.email, "role": user.role})
            conn.commit()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="User already exists")
    return {"message": "User added", "email": user.email, "role": user.role}


@app.put("/auth/users")
def update_user_role(email: str = Query(...), role: str = Query(...)):
    """Update a user's role."""
    if role not in ("admin", "trends"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'trends'")
    with engine.connect() as conn:
        cur = conn.execute(text(f"UPDATE {tbl('users')} SET role = :role WHERE email = :email"), {"role": role, "email": email})
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Role updated", "email": email, "role": role}


@app.delete("/auth/users")
def delete_user(email: str = Query(...)):
    """Remove a whitelisted user."""
    with engine.connect() as conn:
        cur = conn.execute(text(f"DELETE FROM {tbl('users')} WHERE email = :email"), {"email": email})
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User removed", "email": email}


@app.get("/")
def read_root():
    return {"message": "Trends Research API is running"}

@app.get("/niches", response_model=List[str])
def get_niches():
    """Return distinct niche names from the DB."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT DISTINCT niche_name FROM {tbl('niches')} ORDER BY niche_name")).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return niche.get_available_niches()

@app.get("/niche_keywords/{niche_name}")
def get_niche_keywords(niche_name: str):
    """Return keywords for a niche from the DB."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT keyword FROM {tbl('niches')} WHERE niche_name = :niche_name ORDER BY keyword"),
                {"niche_name": niche_name},
            ).fetchall()
        keywords = [r[0] for r in rows]
        return {"niche": niche_name, "keywords": keywords if keywords else [niche_name]}
    except Exception:
        keywords = niche.get_niche_keywords(niche_name)
        return {"niche": niche_name, "keywords": keywords}


class NicheCreate(BaseModel):
    niche_name: str
    keywords: List[str] = []


class KeywordAdd(BaseModel):
    keywords: List[str]


@app.post("/niches")
def create_niche(body: NicheCreate):
    """Create a new niche with optional keywords."""
    if not body.niche_name.strip():
        raise HTTPException(status_code=400, detail="Niche name cannot be empty")
    keywords = body.keywords if body.keywords else [body.niche_name.strip()]
    added = 0
    with engine.connect() as conn:
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            try:
                conn.execute(
                    text(f"INSERT INTO {tbl('niches')} (niche_name, keyword) VALUES (:niche_name, :kw)"),
                    {"niche_name": body.niche_name.strip(), "kw": kw},
                )
                added += 1
            except IntegrityError:
                pass
        conn.commit()
    return {"message": f"Niche '{body.niche_name}' created with {added} keyword(s)"}


@app.post("/niches/{niche_name}/keywords")
def add_keywords(niche_name: str, body: KeywordAdd):
    """Add keywords to an existing niche."""
    added = 0
    with engine.connect() as conn:
        for kw in body.keywords:
            kw = kw.strip()
            if not kw:
                continue
            try:
                conn.execute(
                    text(f"INSERT INTO {tbl('niches')} (niche_name, keyword) VALUES (:niche_name, :kw)"),
                    {"niche_name": niche_name, "kw": kw},
                )
                added += 1
            except IntegrityError:
                pass
        conn.commit()
    return {"message": f"Added {added} keyword(s) to '{niche_name}'"}


@app.delete("/niches/{niche_name}")
def delete_niche(niche_name: str):
    """Delete an entire niche and all its keywords."""
    with engine.connect() as conn:
        cur = conn.execute(text(f"DELETE FROM {tbl('niches')} WHERE niche_name = :niche_name"), {"niche_name": niche_name})
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Niche not found")
    return {"message": f"Niche '{niche_name}' deleted"}


@app.delete("/niches/{niche_name}/keywords/{keyword}")
def delete_keyword(niche_name: str, keyword: str):
    """Remove a single keyword from a niche."""
    with engine.connect() as conn:
        cur = conn.execute(
            text(f"DELETE FROM {tbl('niches')} WHERE niche_name = :niche_name AND keyword = :keyword"),
            {"niche_name": niche_name, "keyword": keyword},
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Keyword not found")
    return {"message": f"Keyword '{keyword}' removed from '{niche_name}'"}

def _log_token_usage(platform: str, keyword: str = None, units: float = 1.0, geo: str = None):
    """Record an API / scrape usage entry."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(f"INSERT INTO {tbl('token_usage')} (platform, keyword, units_charged, geo) VALUES (:platform, :keyword, :units, :geo)"),
                {"platform": platform, "keyword": keyword, "units": units, "geo": geo},
            )
            conn.commit()
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


def _get_niche_keywords_from_db(niche_name: str) -> list:
    """Fetch keywords for a niche from the DB, falling back to NicheDiscovery."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT keyword FROM {tbl('niches')} WHERE niche_name = :niche_name"), {"niche_name": niche_name}
            ).fetchall()
        keywords = [r[0] for r in rows]
        if keywords:
            return keywords
    except Exception:
        pass
    return niche.get_niche_keywords(niche_name)


@app.post("/scrape")
def scrape_niche(request: ScrapeRequest, background_tasks: BackgroundTasks):
    niche_keywords = _get_niche_keywords_from_db(request.niche)
    scraper = request.scraper_type

    if scraper == "all":
        background_tasks.add_task(
            _run_and_log, collector.run_niche_comprehensive_scrape,
            "all", niche_keywords, request.geo,
            niche_name=request.niche,
            keywords=niche_keywords,
            geo=request.geo,
            timeframe=request.timeframe,
            category=request.category
        )
    elif scraper == "google_trends":
        background_tasks.add_task(
            _run_and_log, collector.run_google_trends_scraper,
            "google_trends", niche_keywords, request.geo,
            keywords=niche_keywords, geo=request.geo,
            timeframe=request.timeframe, category=request.category
        )
    elif scraper == "daily":
        background_tasks.add_task(
            _run_and_log, collector.run_trending_now_scraper,
            "daily", request.niche, request.geo,
            geo=request.geo
        )
    elif scraper == "youtube":
        background_tasks.add_task(
            _run_and_log, collector.run_youtube_trends_scraper,
            "youtube", niche_keywords, request.geo,
            keywords=niche_keywords, geo=request.geo
        )
    elif scraper in ("Threads", "Instagram", "TikTok"):
        background_tasks.add_task(
            _run_and_log, collector.run_social_trends_scraper,
            scraper, niche_keywords, request.geo,
            platform=scraper, keywords=niche_keywords, geo=request.geo
        )
    elif scraper == "hackernews":
        background_tasks.add_task(
            _run_and_log, collector.run_hackernews_scraper,
            "hackernews", niche_keywords, request.geo,
            keywords=niche_keywords, geo=request.geo
        )
    elif scraper == "reddit":
        background_tasks.add_task(
            _run_and_log, collector.run_reddit_scraper,
            "reddit", niche_keywords, request.geo,
            keywords=niche_keywords, geo=request.geo
        )
    elif scraper == "news":
        background_tasks.add_task(
            _run_and_log, collector.run_news_scraper,
            "news", request.niche, request.geo,
            query=request.niche, geo=request.geo
        )
    else:
        background_tasks.add_task(
            _run_and_log, collector.run_niche_comprehensive_scrape,
            "all", niche_keywords, request.geo,
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
            _run_and_log, collector.run_token_import,
            "import_tokens", keyword, geo,
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
                niche_keywords = _get_niche_keywords_from_db(niche_name)
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
        keywords = _get_niche_keywords_from_db(niche_name) if niche_name else None
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
                niche_keywords = _get_niche_keywords_from_db(niche_name)
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
        keywords = _get_niche_keywords_from_db(niche_name) if niche_name else None
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

def _query_platform_table(query: str, params: dict):
    """Execute a SELECT query against the DB and return JSON-safe records."""
    try:
        with engine.connect() as conn:
            df = pd.read_sql_query(text(query), conn, params=params)
        return _sanitize_and_serialize(df) if not df.empty else []
    except Exception as e:
        logger.error(f"DB query error: {e}")
        return []


def _geo_clause(col: str = "geo"):
    return f" AND (UPPER({col}) = UPPER(:geo_param) OR {col} = '' OR UPPER({col}) = 'GLOBAL' OR {col} IS NULL)"


def _keyword_clause(keywords: list, col: str = "search_keyword"):
    if not keywords:
        return "", {}
    placeholders = ", ".join([f":kw_{i}" for i in range(len(keywords))])
    kw_params = {f"kw_{i}": kw for i, kw in enumerate(keywords)}
    return f" AND {col} IN ({placeholders})", kw_params


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
    try:
        # Sanitise column/table names (allow only alphanumeric + underscore)
        import re
        _safe = re.compile(r"^\w+$")
        if not _safe.match(table_name) or not _safe.match(geo_col) or not _safe.match(keyword_col):
            raise HTTPException(status_code=400, detail="Invalid table/column name")

        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT DISTINCT {geo_col} FROM {tbl(table_name)} WHERE {geo_col} IS NOT NULL AND {geo_col} != ''")).fetchall()
            geos_raw = sorted(set(r[0] for r in rows if r[0]))
            if geos_raw:
                geos = ["All"] + geos_raw

            rows = conn.execute(text(f"SELECT DISTINCT {keyword_col} FROM {tbl(table_name)} WHERE {keyword_col} IS NOT NULL AND {keyword_col} != ''")).fetchall()
            kw_raw = sorted(set(r[0] for r in rows if r[0]))
            if kw_raw:
                keywords = ["All"] + kw_raw
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
    query = f"""
        SELECT video_id, title, description, search_keyword, geo,
               channel_title, channel_id, published, duration, url,
               thumbnail_url, tags, language,
               view_count, like_count, comment_count,
               engagement_total,
               extracted_at
        FROM {tbl('youtube_videos')} WHERE 1=1
    """
    params = {}
    if geo and geo != "Global":
        query += _geo_clause()
        params["geo_param"] = geo
    if niche_name:
        kws = _get_niche_keywords_from_db(niche_name)
        clause, kw_params = _keyword_clause(kws)
        query += clause
        params.update(kw_params)
    query += limit_clause("view_count DESC", limit)
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
    query = f"""
        SELECT aweme_id, description, search_keyword, geo, region,
               create_time, duration, share_url,
               digg_count, comment_count, share_count, play_count,
               download_count, collect_count, engagement_total,
               author_unique_id, author_nickname, author_follower_count,
               author_verified,
               music_title, music_author,
               hashtags, video_ratio,
               extracted_at
        FROM {tbl('tiktok_videos')} WHERE 1=1
    """
    params = {}
    if geo and geo != "Global":
        query += _geo_clause()
        params["geo_param"] = geo
    if niche_name:
        kws = _get_niche_keywords_from_db(niche_name)
        clause, kw_params = _keyword_clause(kws)
        query += clause
        params.update(kw_params)
    query += limit_clause("play_count DESC", limit)
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
    query = f"""
        SELECT post_pk, shortcode, search_keyword, geo,
               caption, media_type, url, thumbnail_url, taken_at,
               location_name,
               username, full_name, follower_count, is_verified,
               like_count, comment_count, share_count, save_count,
               video_view_count, video_play_count,
               engagement_total, hashtags,
               extracted_at
        FROM {tbl('instagram_posts')} WHERE 1=1
    """
    params = {}
    if geo and geo != "Global":
        query += _geo_clause()
        params["geo_param"] = geo
    if niche_name:
        kws = _get_niche_keywords_from_db(niche_name)
        clause, kw_params = _keyword_clause(kws)
        query += clause
        params.update(kw_params)
    query += limit_clause("like_count DESC", limit)
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
    query = f"""
        SELECT post_id, title, selftext, search_keyword, geo,
               url, permalink, domain,
               subreddit, author,
               score, upvote_ratio, num_comments, total_awards,
               engagement_total, link_flair_text,
               created_utc, extracted_at
        FROM {tbl('reddit_posts')} WHERE 1=1
    """
    params = {}
    if geo and geo != "Global":
        query += _geo_clause()
        params["geo_param"] = geo
    if niche_name:
        kws = _get_niche_keywords_from_db(niche_name)
        clause, kw_params = _keyword_clause(kws)
        query += clause
        params.update(kw_params)
    query += limit_clause("score DESC", limit)
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
    query = f"""
        SELECT post_code, search_keyword, geo,
               caption, url, taken_at, media_type,
               username, full_name, follower_count, is_verified,
               like_count, reply_count, repost_count, quote_count, share_count,
               engagement_total,
               extracted_at
        FROM {tbl('threads_posts')} WHERE 1=1
    """
    params = {}
    if geo and geo != "Global":
        query += _geo_clause()
        params["geo_param"] = geo
    if niche_name:
        kws = _get_niche_keywords_from_db(niche_name)
        clause, kw_params = _keyword_clause(kws)
        query += clause
        params.update(kw_params)
    query += limit_clause("like_count DESC", limit)
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
    query = f"""
        SELECT hookd_id, external_id, search_keyword,
               platform, display_format, title, body,
               landing_page, cta_type, cta_text,
               start_date, end_date, days_active, active_in_library,
               performance_score, performance_score_title, used_count,
               age_audience_min, age_audience_max, gender_audience, eu_total_reach,
               brand_name, brand_logo_url, brand_active_ads,
               media, share_url,
               extracted_at
        FROM {tbl('ads_insight')} WHERE 1=1
    """
    params = {}
    if niche_name:
        kws = _get_niche_keywords_from_db(niche_name)
        clause, kw_params = _keyword_clause(kws)
        query += clause
        params.update(kw_params)
    query += limit_clause("extracted_at DESC", limit)
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
    background_tasks.add_task(
        _run_and_log, gethookd_scrape_ads,
        "ads_insight", kws, None,
        keywords=kws, max_pages=max_pages,
    )
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
    background_tasks.add_task(
        _run_and_log, gethookd_scrape_brand_ads,
        "ads_brand_spy", str(brand_id), None,
        brand_id=brand_id,
    )
    return {"message": f"Brand spy started for brand {brand_id}"}


# ---------------------------------------------------------------------------
# Clear scrape errors
# ---------------------------------------------------------------------------

@app.delete("/scrape_errors")
def clear_scrape_errors():
    try:
        with engine.connect() as conn:
            conn.execute(text(f"DELETE FROM {tbl('scrape_errors')}"))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to clear scrape_errors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Token usage (EnsembleData units consumed)
# ---------------------------------------------------------------------------

_ENSEMBLEDATA_PLATFORMS = {"Instagram", "TikTok", "Threads", "YouTube", "Reddit",
                           "instagram", "tiktok", "threads", "youtube", "reddit"}
_GETHOOKEDAI_PLATFORMS = {"ads_insight", "ads_brand_spy"}
_TRACKED_PLATFORMS = _ENSEMBLEDATA_PLATFORMS | _GETHOOKEDAI_PLATFORMS


def _provider_label(platform: str) -> str:
    if platform in _ENSEMBLEDATA_PLATFORMS or platform.lower() in {p.lower() for p in _ENSEMBLEDATA_PLATFORMS}:
        return "ensembledata"
    if platform in _GETHOOKEDAI_PLATFORMS:
        return "gethookedai"
    return "other"


@app.get("/admin/token_usage")
def get_token_usage():
    """Return token/units consumption for ensembledata and gethookedai only."""
    try:
        # Build named params for IN clause
        plat_params = {f"p_{i}": p for i, p in enumerate(_TRACKED_PLATFORMS)}
        placeholders = ", ".join([f":p_{i}" for i in range(len(_TRACKED_PLATFORMS))])

        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT TOP 1000 platform, keyword, units_charged, geo, created_at "
                    f"FROM {tbl('token_usage')} WHERE platform IN ({placeholders}) "
                    f"ORDER BY created_at DESC"
                ),
                plat_params,
            ).fetchall()
            data = []
            for r in rows:
                d = dict(r._mapping)
                d["provider"] = _provider_label(d["platform"])
                data.append(d)

            summary = conn.execute(
                text(
                    f"SELECT platform, SUM(units_charged) as total_units, COUNT(*) as request_count "
                    f"FROM {tbl('token_usage')} WHERE platform IN ({placeholders}) "
                    f"GROUP BY platform ORDER BY total_units DESC"
                ),
                plat_params,
            ).fetchall()
            summary_data = []
            for r in summary:
                d = dict(r._mapping)
                d["provider"] = _provider_label(d["platform"])
                summary_data.append(d)

            provider_rows = conn.execute(
                text(
                    f"SELECT CASE "
                    f"  WHEN platform IN ('ads_insight','ads_brand_spy') THEN 'gethookedai' "
                    f"  ELSE 'ensembledata' END as provider, "
                    f"  SUM(units_charged) as total_units, COUNT(*) as request_count "
                    f"FROM {tbl('token_usage')} WHERE platform IN ({placeholders}) "
                    f"GROUP BY CASE "
                    f"  WHEN platform IN ('ads_insight','ads_brand_spy') THEN 'gethookedai' "
                    f"  ELSE 'ensembledata' END "
                    f"ORDER BY total_units DESC"
                ),
                plat_params,
            ).fetchall()
            provider_data = [dict(r._mapping) for r in provider_rows]

        return {"data": data, "summary": summary_data, "provider_summary": provider_data}
    except Exception as e:
        logger.error(f"Failed to fetch token usage: {e}")
        return {"data": [], "summary": [], "provider_summary": []}


# ---------------------------------------------------------------------------
# Azure DB: schema setup & data population
# ---------------------------------------------------------------------------

_SQLITE_TO_AZURE_TABLES = [
    "trends", "scrape_errors", "scrape_log", "users", "otp_codes",
    "auth_tokens", "token_usage", "niches", "raw_data_archive",
    "tiktok_videos", "instagram_posts", "youtube_videos",
    "reddit_posts", "threads_posts", "ads_insight",
]


@app.post("/admin/azure/setup_schema")
def setup_azure_schema(background_tasks: BackgroundTasks):
    """Run the Azure SQL schema setup (create tables & indexes)."""
    try:
        from src.db.setup_azure import run_schema
        background_tasks.add_task(run_schema)
        return {"message": "Azure schema setup started in background"}
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"setup_azure module not found: {e}")


@app.post("/admin/azure/populate")
def populate_azure_db(background_tasks: BackgroundTasks):
    """Copy all data from local SQLite to Azure SQL Server."""
    background_tasks.add_task(_populate_azure_task)
    return {"message": "Azure DB population started in background"}


@app.get("/admin/azure/status")
def azure_status():
    """Check Azure SQL connectivity and return table row counts."""
    import importlib
    try:
        # Build a temporary mssql engine
        azure_engine = _get_azure_engine()
        with azure_engine.connect() as conn:
            conn.execute(text("SELECT 1")).scalar()
        # Get row counts
        counts = {}
        with azure_engine.connect() as conn:
            for t in _SQLITE_TO_AZURE_TABLES:
                try:
                    n = conn.execute(text(f"SELECT COUNT(*) FROM dbo.{t}")).scalar()
                    counts[t] = n
                except Exception:
                    counts[t] = "N/A"
        return {"connected": True, "tables": counts}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def _get_azure_engine():
    """Create a separate mssql engine for Azure (regardless of current DB_BACKEND)."""
    from urllib.parse import quote_plus as _qp
    conn_str = os.getenv("AZURE_SQL_CONNECTIONSTRING")
    if not conn_str:
        server = os.getenv("AZURE_SQL_SERVER")
        db = os.getenv("AZURE_SQL_DB", os.getenv("AZURE_SQL_DATABASE"))
        user = os.getenv("AZURE_SQL_USER")
        pwd = os.getenv("AZURE_SQL_PASS")
        driver = os.getenv("AZURE_SQL_DRIVER", "ODBC Driver 18 for SQL Server")
        conn_str = (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={db};"
            f"UID={user};PWD={pwd};Encrypt=yes;TrustServerCertificate=no;"
        )
    from sqlalchemy import create_engine as _ce
    return _ce(f"mssql+pyodbc:///?odbc_connect={_qp(conn_str)}", pool_pre_ping=True)


def _populate_azure_task():
    """Background task: read each table from SQLite and bulk-insert into Azure."""
    import sqlite3
    sqlite_path = os.getenv("DB_PATH", os.path.join(project_root, "src", "collector", "trends.db"))
    try:
        azure_engine = _get_azure_engine()
    except Exception as e:
        logger.error("Cannot create Azure engine: %s", e)
        return

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row

    for table in _SQLITE_TO_AZURE_TABLES:
        try:
            rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                logger.info("Table %s is empty in SQLite — skipping.", table)
                continue

            cols = rows[0].keys()
            # Skip auto-increment 'id' column for tables that have it
            insert_cols = [c for c in cols if c != "id"]
            col_list = ", ".join(insert_cols)
            val_list = ", ".join(f":{c}" for c in insert_cols)

            with azure_engine.connect() as az_conn:
                batch_size = 500
                inserted = 0
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    params_list = [{c: row[c] for c in insert_cols} for row in batch]
                    try:
                        az_conn.execute(
                            text(f"INSERT INTO dbo.{table} ({col_list}) VALUES ({val_list})"),
                            params_list,
                        )
                        az_conn.commit()
                        inserted += len(batch)
                    except Exception as e:
                        logger.warning("Batch insert into %s failed (batch %d): %s", table, i // batch_size, e)
                        az_conn.rollback()
                        # Try row-by-row for this batch
                        for params in params_list:
                            try:
                                az_conn.execute(
                                    text(f"INSERT INTO dbo.{table} ({col_list}) VALUES ({val_list})"),
                                    params,
                                )
                                az_conn.commit()
                                inserted += 1
                            except Exception:
                                az_conn.rollback()
                logger.info("Populated dbo.%s: %d rows inserted.", table, inserted)
        except Exception as e:
            logger.error("Failed to populate table %s: %s", table, e)

    sqlite_conn.close()
    logger.info("Azure DB population complete.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

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
from sqlalchemy import text, func
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
from src.db.connection import get_engine, get_session, is_sqlite
from src.db.sql_compat import get_platform_id, get_platform_name, insert_niche_if_not_exists, verify_otp
from src.db.models import (
    Base, User, OtpCode, AuthToken, Niche, TokenUsage, ScrapeError as ScrapeErrorModel,
    AdsInsight, Content, ContentMetric, Author, Platform, Trend,
)

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
SessionFactory = get_session

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
    """Ensure all tables exist using ORM metadata."""
    try:
        Base.metadata.create_all(engine)
        logger.info("Database tables verified via ORM metadata.")
    except Exception as e:
        logger.warning("Could not create tables via ORM: %s", e)

_init_auth_tables()


def _init_token_usage_table():
    """Ensure token_usage table exists (Azure SQL – tables created via migration schema)."""
    pass

_init_token_usage_table()


def _init_niches_table():
    """Seed niches table with defaults if empty."""
    try:
        session = SessionFactory()
        try:
            count = session.query(Niche).count()
            if count == 0:
                _nd = NicheDiscovery()
                for niche_name, keywords in _nd.niche_map.items():
                    for kw in keywords:
                        insert_niche_if_not_exists(session, niche_name, kw)
                session.commit()
        finally:
            session.close()
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
        session = SessionFactory()
        try:
            user = session.query(User).filter(User.email == email).first()
            if not user:
                user = User(email=email, role="admin")
                session.add(user)
                session.flush()
            session.add(OtpCode(user_id=user.id, code=TEST_ACCOUNT_OTP))
            session.commit()
        finally:
            session.close()
        return {"message": "OTP sent", "email": email}

    session = SessionFactory()
    try:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=403, detail="Email not whitelisted")

        user_id = user.id
        code = secrets.token_hex(3).upper()  # 6-char hex code
        session.add(OtpCode(user_id=user_id, code=code))
        session.commit()
    finally:
        session.close()

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
def verify_otp_endpoint(email: str = Query(...), code: str = Query(...)):
    """Verify an OTP code and return the user's role."""
    session = SessionFactory()
    try:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired OTP")
        user_id = user.id
        user_role = user.role

        otp = verify_otp(session, user_id, code.upper())
        if not otp:
            raise HTTPException(status_code=401, detail="Invalid or expired OTP")

        otp.used = 1

        # Generate auth token valid for 12 hours
        token = secrets.token_hex(32)
        expires_at = datetime.utcnow() + timedelta(hours=12)
        session.add(AuthToken(token=token, user_id=user_id, expires_at=expires_at))
        session.commit()
    finally:
        session.close()

    return {"message": "Authenticated", "email": email, "role": user_role, "token": token}


@app.get("/auth/validate_token")
def validate_token(token: str = Query(...)):
    """Validate an auth token and return user info if still valid."""
    session = SessionFactory()
    try:
        row = session.query(User.email, User.role).join(
            AuthToken, AuthToken.user_id == User.id
        ).filter(
            AuthToken.token == token,
            AuthToken.expires_at > datetime.utcnow(),
        ).first()
    finally:
        session.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"email": row.email, "role": row.role}


@app.get("/auth/users")
def list_users():
    """List all whitelisted users."""
    session = SessionFactory()
    try:
        rows = session.query(User.email, User.role, User.created_at).order_by(User.created_at).all()
    finally:
        session.close()
    return [{"email": r.email, "role": r.role, "created_at": r.created_at} for r in rows]


@app.post("/auth/users")
def add_user(user: UserCreate):
    """Add a whitelisted user."""
    if user.role not in ("admin", "trends"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'trends'")
    session = SessionFactory()
    try:
        session.add(User(email=user.email, role=user.role))
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="User already exists")
    finally:
        session.close()
    return {"message": "User added", "email": user.email, "role": user.role}


@app.put("/auth/users")
def update_user_role(email: str = Query(...), role: str = Query(...)):
    """Update a user's role."""
    if role not in ("admin", "trends"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'trends'")
    session = SessionFactory()
    try:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.role = role
        session.commit()
    finally:
        session.close()
    return {"message": "Role updated", "email": email, "role": role}


@app.delete("/auth/users")
def delete_user(email: str = Query(...)):
    """Remove a whitelisted user."""
    session = SessionFactory()
    try:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        session.delete(user)
        session.commit()
    finally:
        session.close()
    return {"message": "User removed", "email": email}


@app.get("/")
def read_root():
    return {"message": "Trends Research API is running"}

@app.get("/niches", response_model=List[str])
def get_niches():
    """Return distinct niche names from the DB."""
    try:
        session = SessionFactory()
        try:
            rows = session.query(Niche.niche_name).distinct().order_by(Niche.niche_name).all()
        finally:
            session.close()
        return [r.niche_name for r in rows]
    except Exception:
        return niche.get_available_niches()

@app.get("/niche_keywords/{niche_name}")
def get_niche_keywords(niche_name: str):
    """Return keywords for a niche from the DB."""
    try:
        session = SessionFactory()
        try:
            rows = session.query(Niche.keyword).filter(
                Niche.niche_name == niche_name
            ).order_by(Niche.keyword).all()
        finally:
            session.close()
        keywords = [r.keyword for r in rows]
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
    session = SessionFactory()
    try:
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            existing = session.query(Niche).filter(
                Niche.niche_name == body.niche_name.strip(),
                Niche.keyword == kw,
            ).first()
            if not existing:
                session.add(Niche(niche_name=body.niche_name.strip(), keyword=kw))
                added += 1
        session.commit()
    finally:
        session.close()
    return {"message": f"Niche '{body.niche_name}' created with {added} keyword(s)"}


@app.post("/niches/{niche_name}/keywords")
def add_keywords(niche_name: str, body: KeywordAdd):
    """Add keywords to an existing niche."""
    added = 0
    session = SessionFactory()
    try:
        for kw in body.keywords:
            kw = kw.strip()
            if not kw:
                continue
            existing = session.query(Niche).filter(
                Niche.niche_name == niche_name,
                Niche.keyword == kw,
            ).first()
            if not existing:
                session.add(Niche(niche_name=niche_name, keyword=kw))
                added += 1
        session.commit()
    finally:
        session.close()
    return {"message": f"Added {added} keyword(s) to '{niche_name}'"}


@app.delete("/niches/{niche_name}")
def delete_niche(niche_name: str):
    """Delete an entire niche and all its keywords."""
    session = SessionFactory()
    try:
        count = session.query(Niche).filter(Niche.niche_name == niche_name).delete()
        session.commit()
        if count == 0:
            raise HTTPException(status_code=404, detail="Niche not found")
    finally:
        session.close()
    return {"message": f"Niche '{niche_name}' deleted"}


@app.delete("/niches/{niche_name}/keywords/{keyword}")
def delete_keyword(niche_name: str, keyword: str):
    """Remove a single keyword from a niche."""
    session = SessionFactory()
    try:
        count = session.query(Niche).filter(
            Niche.niche_name == niche_name,
            Niche.keyword == keyword,
        ).delete()
        session.commit()
        if count == 0:
            raise HTTPException(status_code=404, detail="Keyword not found")
    finally:
        session.close()
    return {"message": f"Keyword '{keyword}' removed from '{niche_name}'"}

def _log_token_usage(platform: str, keyword: str = None, units: float = 1.0, geo: str = None):
    """Record an API / scrape usage entry."""
    try:
        session = SessionFactory()
        try:
            session.add(TokenUsage(platform=platform, keyword=keyword, units_charged=units, geo=geo))
            session.commit()
        finally:
            session.close()
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
        session = SessionFactory()
        try:
            rows = session.query(Niche.keyword).filter(Niche.niche_name == niche_name).all()
        finally:
            session.close()
        keywords = [r.keyword for r in rows]
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
# Table filters (dynamic dropdowns) — ORM
# ---------------------------------------------------------------------------

# Map of table names to ORM model classes for safe dynamic access
_TABLE_MODEL_MAP = {
    "content": Content,
    "trends": Trend,
    "ads_insight": AdsInsight,
    "scrape_errors": ScrapeErrorModel,
}


@app.get("/table_filters")
def get_table_filters(
    table_name: str = Query(...),
    geo_col: str = Query("geo"),
    keyword_col: str = Query("search_keyword"),
):
    """Return distinct geo and keyword values from a given DB table."""
    import re
    _safe = re.compile(r"^\w+$")
    if not _safe.match(table_name) or not _safe.match(geo_col) or not _safe.match(keyword_col):
        raise HTTPException(status_code=400, detail="Invalid table/column name")

    geos, keywords = ["Global"], ["All"]
    try:
        model = _TABLE_MODEL_MAP.get(table_name)
        if not model:
            # Fallback: try to find model by tablename
            for m in Base.registry.mappers:
                if m.class_.__tablename__ == table_name:
                    model = m.class_
                    break
        if not model:
            return {"geos": geos, "keywords": keywords}

        geo_attr = getattr(model, geo_col, None)
        kw_attr = getattr(model, keyword_col, None)

        session = SessionFactory()
        try:
            if geo_attr is not None:
                rows = session.query(geo_attr).filter(
                    geo_attr.isnot(None), geo_attr != ""
                ).distinct().all()
                geos_raw = sorted(set(r[0] for r in rows if r[0]))
                if geos_raw:
                    geos = ["All"] + geos_raw

            if kw_attr is not None:
                rows = session.query(kw_attr).filter(
                    kw_attr.isnot(None), kw_attr != ""
                ).distinct().all()
                kw_raw = sorted(set(r[0] for r in rows if r[0]))
                if kw_raw:
                    keywords = ["All"] + kw_raw
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception:
        pass
    return {"geos": geos, "keywords": keywords}


# ---------------------------------------------------------------------------
# Normalized content query helper — ORM
# ---------------------------------------------------------------------------

def _content_query(platform_name: str, niche_name, geo, limit, order_attr=None):
    """Query the normalized content/authors/metrics tables via ORM."""
    session = SessionFactory()
    try:
        query = session.query(
            Content.external_id, Content.text_content, Content.keyword, Content.geo,
            Content.media_type, Content.url, Content.created_at,
            Author.username, Author.full_name, Author.follower_count,
            Author.is_verified, Author.profile_pic_url,
            ContentMetric.likes, ContentMetric.comments, ContentMetric.shares,
            ContentMetric.views, ContentMetric.saves,
            Platform.name.label("platform"),
        ).join(
            Platform, Platform.id == Content.platform_id
        ).outerjoin(
            Author, Author.id == Content.author_id
        ).outerjoin(
            ContentMetric, ContentMetric.content_id == Content.id
        ).filter(
            Platform.name == platform_name
        )

        if geo and geo != "Global":
            query = query.filter(
                (func.upper(Content.geo) == func.upper(geo)) |
                (Content.geo == "") |
                (func.upper(Content.geo) == "GLOBAL") |
                (Content.geo.is_(None))
            )
        if niche_name:
            kws = _get_niche_keywords_from_db(niche_name)
            if kws:
                query = query.filter(Content.keyword.in_(kws))

        if order_attr is not None:
            query = query.order_by(order_attr)
        else:
            query = query.order_by(ContentMetric.likes.desc())

        query = query.limit(limit)
        rows = query.all()
    finally:
        session.close()

    columns = [
        "external_id", "text_content", "keyword", "geo",
        "media_type", "url", "created_at",
        "username", "full_name", "follower_count",
        "is_verified", "profile_pic_url",
        "likes", "comments", "shares", "views", "saves", "platform",
    ]
    if not rows:
        return []
    df = pd.DataFrame(rows, columns=columns)
    return _sanitize_and_serialize(df)


# ---------------------------------------------------------------------------
# YouTube videos (normalized content table)
# ---------------------------------------------------------------------------

@app.get("/youtube_videos")
def get_youtube_videos(
    niche_name: Optional[str] = Query(None),
    geo: Optional[str] = Query(None),
    limit: int = Query(500),
):
    data = _content_query("YouTube", niche_name, geo, limit, order_attr=ContentMetric.views.desc())
    return {"data": data}


# ---------------------------------------------------------------------------
# TikTok videos (normalized content table)
# ---------------------------------------------------------------------------

@app.get("/tiktok_videos")
def get_tiktok_videos(
    niche_name: Optional[str] = Query(None),
    geo: Optional[str] = Query(None),
    limit: int = Query(500),
):
    data = _content_query("TikTok", niche_name, geo, limit, order_attr=ContentMetric.views.desc())
    for row in data:
        ca = row.get("created_at")
        if ca:
            try:
                row["created"] = str(ca)[:16]
            except Exception:
                pass
    return {"data": data}


# ---------------------------------------------------------------------------
# Instagram posts (normalized content table)
# ---------------------------------------------------------------------------

@app.get("/instagram_posts")
def get_instagram_posts(
    niche_name: Optional[str] = Query(None),
    geo: Optional[str] = Query(None),
    limit: int = Query(500),
):
    data = _content_query("Instagram", niche_name, geo, limit, order_attr=ContentMetric.likes.desc())
    for row in data:
        ca = row.get("created_at")
        if ca:
            try:
                row["posted"] = str(ca)[:16]
            except Exception:
                pass
    return {"data": data}


# ---------------------------------------------------------------------------
# Reddit posts (normalized content table)
# ---------------------------------------------------------------------------

@app.get("/reddit_posts")
def get_reddit_posts(
    niche_name: Optional[str] = Query(None),
    geo: Optional[str] = Query(None),
    limit: int = Query(500),
):
    data = _content_query("Reddit", niche_name, geo, limit, order_attr=ContentMetric.likes.desc())
    for row in data:
        ca = row.get("created_at")
        if ca:
            try:
                row["posted"] = str(ca)[:16]
            except Exception:
                pass
    return {"data": data}


# ---------------------------------------------------------------------------
# Threads posts (normalized content table)
# ---------------------------------------------------------------------------

@app.get("/threads_posts")
def get_threads_posts(
    niche_name: Optional[str] = Query(None),
    geo: Optional[str] = Query(None),
    limit: int = Query(500),
):
    data = _content_query("Threads", niche_name, geo, limit, order_attr=ContentMetric.likes.desc())
    for row in data:
        ca = row.get("created_at")
        if ca:
            try:
                row["posted"] = str(ca)[:16]
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
    session = SessionFactory()
    try:
        q = session.query(
            AdsInsight.hookd_id, AdsInsight.external_id, AdsInsight.search_keyword,
            AdsInsight.platform, AdsInsight.display_format, AdsInsight.title, AdsInsight.body,
            AdsInsight.landing_page, AdsInsight.cta_type, AdsInsight.cta_text,
            AdsInsight.start_date, AdsInsight.end_date, AdsInsight.days_active, AdsInsight.active_in_library,
            AdsInsight.performance_score, AdsInsight.performance_score_title, AdsInsight.used_count,
            AdsInsight.age_audience_min, AdsInsight.age_audience_max, AdsInsight.gender_audience, AdsInsight.eu_total_reach,
            AdsInsight.brand_name, AdsInsight.brand_logo_url, AdsInsight.brand_active_ads,
            AdsInsight.media, AdsInsight.share_url,
            AdsInsight.extracted_at,
        )
        if niche_name:
            kws = _get_niche_keywords_from_db(niche_name)
            if kws:
                q = q.filter(AdsInsight.search_keyword.in_(kws))
        q = q.order_by(AdsInsight.extracted_at.desc()).limit(limit)
        rows = q.all()
    finally:
        session.close()

    columns = [
        "hookd_id", "external_id", "search_keyword",
        "platform", "display_format", "title", "body",
        "landing_page", "cta_type", "cta_text",
        "start_date", "end_date", "days_active", "active_in_library",
        "performance_score", "performance_score_title", "used_count",
        "age_audience_min", "age_audience_max", "gender_audience", "eu_total_reach",
        "brand_name", "brand_logo_url", "brand_active_ads",
        "media", "share_url", "extracted_at",
    ]
    if not rows:
        return {"data": []}
    df = pd.DataFrame(rows, columns=columns)
    return {"data": _sanitize_and_serialize(df)}


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
        session = SessionFactory()
        try:
            session.query(ScrapeErrorModel).delete()
            session.commit()
        finally:
            session.close()
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
        session = SessionFactory()
        try:
            # Recent usage rows (limit 1000)
            rows = session.query(
                TokenUsage.platform, TokenUsage.keyword,
                TokenUsage.units_charged, TokenUsage.geo, TokenUsage.created_at,
            ).filter(
                TokenUsage.platform.in_(_TRACKED_PLATFORMS),
            ).order_by(TokenUsage.created_at.desc()).limit(1000).all()

            data = []
            for r in rows:
                data.append({
                    "platform": r.platform, "keyword": r.keyword,
                    "units_charged": r.units_charged, "geo": r.geo,
                    "created_at": r.created_at,
                    "provider": _provider_label(r.platform),
                })

            # Summary by platform
            summary_rows = session.query(
                TokenUsage.platform,
                func.sum(TokenUsage.units_charged).label("total_units"),
                func.count().label("request_count"),
            ).filter(
                TokenUsage.platform.in_(_TRACKED_PLATFORMS),
            ).group_by(TokenUsage.platform).order_by(func.sum(TokenUsage.units_charged).desc()).all()

            summary_data = []
            for r in summary_rows:
                summary_data.append({
                    "platform": r.platform, "total_units": r.total_units,
                    "request_count": r.request_count,
                    "provider": _provider_label(r.platform),
                })

            # Provider-level summary (computed in Python from summary_data)
            provider_agg = {}
            for s in summary_data:
                prov = s["provider"]
                if prov not in provider_agg:
                    provider_agg[prov] = {"provider": prov, "total_units": 0, "request_count": 0}
                provider_agg[prov]["total_units"] += s["total_units"] or 0
                provider_agg[prov]["request_count"] += s["request_count"] or 0
            provider_data = sorted(provider_agg.values(), key=lambda x: x["total_units"], reverse=True)
        finally:
            session.close()

        return {"data": data, "summary": summary_data, "provider_summary": provider_data}
    except Exception as e:
        logger.error(f"Failed to fetch token usage: {e}")
        return {"data": [], "summary": [], "provider_summary": []}


# ---------------------------------------------------------------------------
# Azure DB: schema setup & data population
# ---------------------------------------------------------------------------



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
    try:
        azure_engine = _get_azure_engine()
        with azure_engine.connect() as conn:
            conn.execute(text("SELECT 1")).scalar()
        # Get row counts via ORM metadata inspection
        from sqlalchemy.orm import Session as _Ses
        counts = {}
        with _Ses(bind=azure_engine) as az_session:
            for mapper in Base.registry.mappers:
                tname = mapper.class_.__tablename__
                try:
                    n = az_session.query(func.count()).select_from(mapper.class_).scalar()
                    counts[tname] = n
                except Exception:
                    counts[tname] = "N/A"
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
    """Background task: read each table from SQLite and bulk-insert into Azure via ORM."""
    from sqlalchemy.orm import Session as _Ses
    try:
        azure_engine = _get_azure_engine()
    except Exception as e:
        logger.error("Cannot create Azure engine: %s", e)
        return

    # Build a local SQLite session
    sqlite_engine = get_engine()  # current engine (should be sqlite)
    local_session = _Ses(bind=sqlite_engine)
    az_session = _Ses(bind=azure_engine)

    try:
        for mapper in Base.registry.mappers:
            model = mapper.class_
            tname = model.__tablename__
            try:
                rows = local_session.query(model).all()
                if not rows:
                    logger.info("Table %s is empty in SQLite — skipping.", tname)
                    continue

                inserted = 0
                for row in rows:
                    # Create a detached copy for the Azure session
                    data = {c.key: getattr(row, c.key) for c in mapper.column_attrs if c.key != "id"}
                    az_session.add(model(**data))
                    inserted += 1
                    if inserted % 500 == 0:
                        try:
                            az_session.commit()
                        except Exception as e:
                            logger.warning("Batch commit for %s failed: %s", tname, e)
                            az_session.rollback()
                try:
                    az_session.commit()
                except Exception as e:
                    logger.warning("Final commit for %s failed: %s", tname, e)
                    az_session.rollback()
                logger.info("Populated %s: %d rows inserted.", tname, inserted)
            except Exception as e:
                logger.error("Failed to populate table %s: %s", tname, e)
                az_session.rollback()
    finally:
        local_session.close()
        az_session.close()
    logger.info("Azure DB population complete.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

import hashlib
import json
import logging
import os
import secrets
import sys
import time
import traceback
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import resend
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, BackgroundTasks, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text, func
from sqlalchemy.exc import IntegrityError

load_dotenv()

# Ensure project root is on sys.path so `src.*` imports work in any environment (e.g. WSL).
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config import CORS_ORIGINS, CACHE_TTL_SECONDS, PROJECT_ROOT
from src.collector.trend_collector import TrendCollector
from src.analytics.analytics_engine import AnalyticsEngine
from src.niche.niche_discovery import NicheDiscovery
from src.db.connection import get_engine, get_session, session_scope, get_session_factory, get_last_diagnostic, diagnose as run_connection_diagnose
from src.db.sql_compat import get_platform_id, get_platform_name, insert_niche_if_not_exists, verify_otp
from src.db.models import (
    Base, User, OtpCode, AuthToken, Niche, TokenUsage, ScrapeError as ScrapeErrorModel,
    AdsInsight, Content, ContentMetric, Author, Platform, Trend,
)

# Try to import GetHookdAI ads scraper
try:
    _gha_dir = os.path.join(PROJECT_ROOT, "src", "scrapers", "gethookedai")
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

# Engine initialization — get_engine() now retries and never crashes,
# but we still wrap in try/except for extra safety.
try:
    engine = get_engine()
except Exception as _eng_err:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger(__name__).warning(
        "Could not create database engine on startup: %s. "
        "The app will start, but DB-dependent endpoints will fail until "
        "Azure SQL becomes reachable.",
        _eng_err,
    )
    engine = None

SessionFactory = get_session  # backward-compat alias

# Resend API config
resend.api_key = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "noreply@yourdomain.com")

# Test account that bypasses OTP (for development/testing).
TEST_ACCOUNT_EMAIL = os.getenv("TEST_ACCOUNT_EMAIL", "").strip()
TEST_ACCOUNT_OTP = os.getenv("TEST_ACCOUNT_OTP", "000000").strip()

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
# Auth: users & OTP tables
# ---------------------------------------------------------------------------

def _init_schema():
    """Ensure all tables and indexes exist on startup.

    Runs the idempotent migration which creates any missing tables
    and adds any missing indexes without touching existing data.
    Skips gracefully if the database is unreachable.
    """
    if engine is None:
        logger.warning("Skipping startup migration — no database engine available.")
        return
    try:
        from src.db.migrate import run_migration
        result = run_migration(dry_run=False)
        s = result.summary()
        if s["tables_created_count"] or s["indexes_created_count"]:
            logger.info(
                "Startup migration: %d tables created, %d indexes created.",
                s["tables_created_count"], s["indexes_created_count"],
            )
        else:
            logger.info("Startup migration: schema is up to date.")
        if s["error_count"]:
            logger.warning("Startup migration had %d errors: %s", s["error_count"], s["errors"])
    except Exception as e:
        # Fallback: at minimum create tables via ORM metadata
        logger.warning("Migration failed, falling back to create_all: %s", e)
        try:
            Base.metadata.create_all(engine)
        except Exception as e2:
            logger.warning("Could not create tables via ORM: %s", e2)

_init_schema()




def _init_niches_table():
    """Seed niches table with defaults if empty."""
    try:
        with session_scope() as session:
            count = session.query(Niche).count()
            if count == 0:
                _nd = NicheDiscovery()
                for niche_name, keywords in _nd.niche_map.items():
                    for kw in keywords:
                        insert_niche_if_not_exists(session, niche_name, kw)
    except Exception as e:
        logger.warning(f"Could not seed niches table: {e}")

_init_niches_table()


class ScrapeRequest(BaseModel):
    niche: str
    geo: str = "US"
    timeframe: str = "today 12-m"
    category: int = 0
    scraper_type: str = "all"

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
        with session_scope() as session:
            user = session.query(User).filter(User.email == email).first()
            if not user:
                user = User(email=email, role="admin")
                session.add(user)
                session.flush()
            session.add(OtpCode(user_id=user.id, code=TEST_ACCOUNT_OTP))
        return {"message": "OTP sent", "email": email}

    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=403, detail="Email not whitelisted")

        user_id = user.id
        code = secrets.token_hex(3).upper()  # 6-char hex code
        session.add(OtpCode(user_id=user_id, code=code))

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
    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired OTP")
        user_id = user.id
        user_role = user.role

        # Test account bypass: accept the fixed OTP without DB lookup
        if TEST_ACCOUNT_EMAIL and email == TEST_ACCOUNT_EMAIL and code == TEST_ACCOUNT_OTP:
            token = secrets.token_hex(32)
            expires_at = datetime.utcnow() + timedelta(hours=12)
            session.add(AuthToken(token=token, user_id=user_id, expires_at=expires_at))
            return {"message": "Authenticated", "email": email, "role": user_role, "token": token}

        otp = verify_otp(session, user_id, code.upper())
        if not otp:
            raise HTTPException(status_code=401, detail="Invalid or expired OTP")

        otp.used = 1

        # Generate auth token valid for 12 hours
        token = secrets.token_hex(32)
        expires_at = datetime.utcnow() + timedelta(hours=12)
        session.add(AuthToken(token=token, user_id=user_id, expires_at=expires_at))

    return {"message": "Authenticated", "email": email, "role": user_role, "token": token}


@app.get("/auth/validate_token")
def validate_token(token: str = Query(...)):
    """Validate an auth token and return user info if still valid."""
    with session_scope() as session:
        row = session.query(User.email, User.role).join(
            AuthToken, AuthToken.user_id == User.id
        ).filter(
            AuthToken.token == token,
            AuthToken.expires_at > datetime.utcnow(),
        ).first()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"email": row.email, "role": row.role}


@app.get("/auth/users")
def list_users():
    """List all whitelisted users."""
    with session_scope() as session:
        rows = session.query(User.email, User.role, User.created_at).order_by(User.created_at).all()
    return [{"email": r.email, "role": r.role, "created_at": r.created_at} for r in rows]


@app.post("/auth/users")
def add_user(user: UserCreate):
    """Add a whitelisted user."""
    if user.role not in ("admin", "trends"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'trends'")
    try:
        with session_scope() as session:
            session.add(User(email=user.email, role=user.role))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="User already exists")
    return {"message": "User added", "email": user.email, "role": user.role}


@app.put("/auth/users")
def update_user_role(email: str = Query(...), role: str = Query(...)):
    """Update a user's role."""
    if role not in ("admin", "trends"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'trends'")
    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.role = role
    return {"message": "Role updated", "email": email, "role": role}


@app.delete("/auth/users")
def delete_user(email: str = Query(...)):
    """Remove a whitelisted user."""
    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        session.delete(user)
    return {"message": "User removed", "email": email}


@app.get("/")
def root():
    return {"message": "Trends Research API v2.0 is running"}


@app.get("/niches", response_model=list[str])
def get_niches():
    """Return distinct niche names from the DB."""
    try:
        with session_scope() as session:
            rows = session.query(Niche.niche_name).distinct().order_by(Niche.niche_name).all()
        return [r.niche_name for r in rows]
    except Exception:
        return niche.get_available_niches()


@app.get("/niche_keywords/{niche_name}")
def get_niche_keywords(niche_name: str):
    """Return keywords for a niche from the DB."""
    try:
        with session_scope() as session:
            rows = session.query(Niche.keyword).filter(
                Niche.niche_name == niche_name
            ).order_by(Niche.keyword).all()
        keywords = [r.keyword for r in rows]
        return {"niche": niche_name, "keywords": keywords if keywords else [niche_name]}
    except Exception:
        keywords = niche.get_niche_keywords(niche_name)
        return {"niche": niche_name, "keywords": keywords}


class NicheCreate(BaseModel):
    niche_name: str
    keywords: list[str] = []


class KeywordAdd(BaseModel):
    keywords: list[str]


@app.post("/niches")
def create_niche(body: NicheCreate):
    """Create a new niche with optional keywords."""
    if not body.niche_name.strip():
        raise HTTPException(status_code=400, detail="Niche name cannot be empty")
    keywords = body.keywords if body.keywords else [body.niche_name.strip()]
    added = 0
    with session_scope() as session:
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            insert_niche_if_not_exists(session, body.niche_name.strip(), kw)
            added += 1
    return {"message": f"Niche '{body.niche_name}' created with {added} keyword(s)"}


@app.post("/niches/{niche_name}/keywords")
def add_keywords(niche_name: str, body: KeywordAdd):
    """Add keywords to an existing niche."""
    added = 0
    with session_scope() as session:
        for kw in body.keywords:
            kw = kw.strip()
            if not kw:
                continue
            insert_niche_if_not_exists(session, niche_name, kw)
            added += 1
    return {"message": f"Added {added} keyword(s) to '{niche_name}'"}


@app.delete("/niches/{niche_name}")
def delete_niche(niche_name: str):
    """Delete an entire niche and all its keywords."""
    with session_scope() as session:
        count = session.query(Niche).filter(Niche.niche_name == niche_name).delete()
        if count == 0:
            raise HTTPException(status_code=404, detail="Niche not found")
    return {"message": f"Niche '{niche_name}' deleted"}


@app.delete("/niches/{niche_name}/keywords/{keyword}")
def delete_keyword(niche_name: str, keyword: str):
    """Remove a single keyword from a niche."""
    with session_scope() as session:
        count = session.query(Niche).filter(
            Niche.niche_name == niche_name,
            Niche.keyword == keyword,
        ).delete()
        if count == 0:
            raise HTTPException(status_code=404, detail="Keyword not found")
    return {"message": f"Keyword '{keyword}' removed from '{niche_name}'"}

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


@app.get("/hackernews_trends")
def get_hackernews_trends(niche_name: Optional[str] = Query(None), geo: Optional[str] = Query(None)):
    return _platform_endpoint(
        "HackerNews",
        {"include_hackernews": True},
        niche_name, geo,
        scrape_fn=lambda: collector.run_hackernews_scraper(
            keywords=_get_niche_keywords_from_db(niche_name) if niche_name else None,
        ),
    )


@app.get("/reddit_trends")
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
    import re as _re
    _safe = _re.compile(r"^\w+$")
    if not _safe.match(table_name) or not _safe.match(geo_col) or not _safe.match(keyword_col):
        raise HTTPException(status_code=400, detail="Invalid table/column name")

    geos, keywords = ["Global"], ["All"]
    try:
        model = _TABLE_MODEL_MAP.get(table_name)
        if not model:
            for m in Base.registry.mappers:
                if m.class_.__tablename__ == table_name:
                    model = m.class_
                    break
        if not model:
            return {"geos": geos, "keywords": keywords}

        geo_attr = getattr(model, geo_col, None)
        kw_attr = getattr(model, keyword_col, None)

        with session_scope() as session:
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
    with session_scope() as session:
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
            geo_upper = geo.strip().upper()
            query = query.filter(
                (func.upper(Content.geo) == geo_upper) |
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
    return _sanitize(df)


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
    rename_map = {
        "text_content": "title",
        "username": "channel_title",
        "views": "view_count",
        "likes": "like_count",
        "comments": "comment_count",
    }
    for row in data:
        for old_key, new_key in rename_map.items():
            if old_key in row:
                row[new_key] = row.pop(old_key)
        row["engagement_total"] = (
            (row.get("view_count") or 0) +
            (row.get("like_count") or 0) +
            (row.get("comment_count") or 0)
        )
        ca = row.get("created_at")
        if ca:
            try:
                row["published"] = str(ca)[:16]
            except Exception:
                pass
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
    # Map generic normalized column names to TikTok-specific names expected by the dashboard
    rename_map = {
        "text_content": "description",
        "username": "author_unique_id",
        "views": "play_count",
        "likes": "digg_count",
        "comments": "comment_count",
        "shares": "share_count",
        "saves": "collect_count",
        "url": "share_url",
    }
    for row in data:
        for old_key, new_key in rename_map.items():
            if old_key in row:
                row[new_key] = row.pop(old_key)
        # Compute engagement_total
        row["engagement_total"] = (
            (row.get("digg_count") or 0) +
            (row.get("comment_count") or 0) +
            (row.get("share_count") or 0) +
            (row.get("collect_count") or 0)
        )
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
    rename_map = {
        "text_content": "caption",
        "likes": "like_count",
        "comments": "comment_count",
        "shares": "share_count",
        "saves": "save_count",
    }
    for row in data:
        for old_key, new_key in rename_map.items():
            if old_key in row:
                row[new_key] = row.pop(old_key)
        row["engagement_total"] = (
            (row.get("like_count") or 0) +
            (row.get("comment_count") or 0) +
            (row.get("share_count") or 0) +
            (row.get("save_count") or 0)
        )
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
    rename_map = {
        "text_content": "title",
        "likes": "score",
        "comments": "num_comments",
        "username": "author",
        "keyword": "subreddit",
    }
    for row in data:
        for old_key, new_key in rename_map.items():
            if old_key in row:
                row[new_key] = row.pop(old_key)
        row["engagement_total"] = (
            (row.get("score") or 0) +
            (row.get("num_comments") or 0)
        )
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
    rename_map = {
        "text_content": "caption",
        "likes": "like_count",
        "comments": "reply_count",
        "shares": "repost_count",
        "saves": "quote_count",
    }
    for row in data:
        for old_key, new_key in rename_map.items():
            if old_key in row:
                row[new_key] = row.pop(old_key)
        row["engagement_total"] = (
            (row.get("like_count") or 0) +
            (row.get("reply_count") or 0) +
            (row.get("repost_count") or 0) +
            (row.get("quote_count") or 0)
        )
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
    with session_scope() as session:
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
    return {"data": _sanitize(df)}


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
        with session_scope() as session:
            session.query(ScrapeErrorModel).delete()
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
        with session_scope() as session:
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


@app.post("/admin/azure/migrate")
def run_azure_migration(
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(False, description="Preview changes without executing"),
):
    """Run the database migration to sync Azure SQL with the latest models.

    This is **idempotent** — it only creates tables and indexes that do not
    already exist.  Safe to run multiple times.

    Set ``dry_run=true`` to preview the SQL without executing.
    """
    try:
        from src.db.migrate import run_migration

        if dry_run:
            # Dry run is fast — execute synchronously and return the preview
            result = run_migration(dry_run=True)
            return {"mode": "dry_run", **result.summary()}

        # Real migration runs in background to avoid HTTP timeout
        def _run():
            res = run_migration(dry_run=False)
            s = res.summary()
            logger.info(
                "Migration finished: %d tables, %d indexes, %d errors",
                s["tables_created_count"], s["indexes_created_count"], s["error_count"],
            )

        background_tasks.add_task(_run)
        return {"message": "Migration started in background. Check /admin/azure/status for results."}
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"migrate module not found: {e}")
    except Exception as e:
        logger.error("Migration failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/azure/status")
def azure_status():
    """Check Azure SQL connectivity and return table row counts."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1")).scalar()
        counts = {}
        with session_scope() as session:
            for mapper in Base.registry.mappers:
                tname = mapper.class_.__tablename__
                try:
                    n = session.query(func.count()).select_from(mapper.class_).scalar()
                    counts[tname] = n
                except Exception:
                    counts[tname] = "N/A"

        # Include last diagnostic info if available
        diag = get_last_diagnostic()
        diag_info = diag.summary_dict() if diag else None
        return {"connected": True, "tables": counts, "diagnostic": diag_info}
    except Exception as e:
        diag = get_last_diagnostic()
        diag_info = diag.summary_dict() if diag else None
        return {"connected": False, "error": str(e), "diagnostic": diag_info}


@app.get("/admin/azure/diagnose")
def azure_diagnose():
    """Run a full connection diagnostic (resets engine and retests everything)."""
    try:
        diag = run_connection_diagnose()
        return diag.summary_dict()
    except Exception as e:
        return {"connected": False, "error": str(e), "strategy": "unknown"}




if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Trends Research API")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    args = parser.parse_args()

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)

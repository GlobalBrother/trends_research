import hashlib
import json
import logging
import os
import secrets
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, Query, BackgroundTasks, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text, func
from sqlalchemy.exc import IntegrityError

# ---------------------------------------------------------------------------
# Secret loading: Key Vault (production) → .env (local development)
# ---------------------------------------------------------------------------
def _init_secrets():
    """Load secrets from Azure Key Vault if KEY_VAULT_NAME is set,
    otherwise fall back to the local .env file."""
    kv_name = os.environ.get("KEY_VAULT_NAME")
    if kv_name:
        try:
            from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
            from azure.keyvault.secrets import SecretClient

            mi_client_id = os.environ.get("MANAGED_IDENTITY_CLIENT_ID")
            credential = (
                ManagedIdentityCredential(client_id=mi_client_id)
                if mi_client_id
                else DefaultAzureCredential()
            )
            client = SecretClient(
                vault_url=f"https://{kv_name}.vault.azure.net",
                credential=credential,
            )
            for prop in client.list_properties_of_secrets():
                secret = client.get_secret(prop.name)
                # Key Vault names use hyphens; env vars use underscores
                os.environ[secret.name.replace("-", "_")] = secret.value
            print(f"Loaded secrets from Key Vault: {kv_name}")
        except Exception as exc:
            print(f"Key Vault load failed ({exc}), falling back to .env")
            load_dotenv()
    else:
        load_dotenv()

_init_secrets()

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
    AdsInsight, Content, ContentMetric, Author, Platform, Trend, MyBrand,
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

# ---------------------------------------------------------------------------
# Email provider: Azure Communication Services (production) or Resend (fallback)
# ---------------------------------------------------------------------------
_acs_conn_str = os.getenv("ACS_CONNECTION_STRING", "")
_acs_sender = os.getenv("ACS_SENDER_ADDRESS", "")
_email_client = None

if _acs_conn_str:
    try:
        from azure.communication.email import EmailClient
        _email_client = EmailClient.from_connection_string(_acs_conn_str)
        print(f"Email provider: Azure Communication Services (sender: {_acs_sender})")
    except Exception as _acs_err:
        print(f"ACS Email init failed ({_acs_err}), falling back to Resend")

# Resend fallback (for local dev or if ACS is not configured)
if not _email_client:
    import resend
    resend.api_key = os.getenv("RESEND_API_KEY", "")
    print("Email provider: Resend")

EMAIL_FROM = _acs_sender or os.getenv("RESEND_FROM_EMAIL", "noreply@yourdomain.com")


def _send_email(to_email: str, subject: str, html_body: str):
    """Send an email via ACS or Resend, depending on what's configured."""
    if _email_client:
        # Azure Communication Services
        message = {
            "content": {"subject": subject, "html": html_body},
            "recipients": {"to": [{"address": to_email}]},
            "senderAddress": EMAIL_FROM,
        }
        poller = _email_client.begin_send(message)
        poller.result()  # wait for completion
    else:
        # Resend fallback
        resend.Emails.send({
            "from": EMAIL_FROM,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        })

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
# Serve React frontend (production build)
# ---------------------------------------------------------------------------
_frontend_dist = os.path.join(PROJECT_ROOT, "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="static-assets")

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


# ---------------------------------------------------------------------------
# Role-based access control helpers
# ---------------------------------------------------------------------------

def _get_current_user(authorization: str) -> User:
    """Validate the Bearer token and return the User object.
    Raises 401 if the token is missing, invalid, or expired."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    with session_scope() as session:
        row = session.query(User.id, User.email, User.role).join(
            AuthToken, AuthToken.user_id == User.id
        ).filter(
            AuthToken.token == token,
            AuthToken.expires_at > datetime.utcnow(),
        ).first()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return row


def _require_admin(authorization: str) -> None:
    """Verify the request comes from an admin user.
    Raises 401 if unauthenticated, 403 if not admin."""
    user = _get_current_user(authorization)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


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
# Background scrape helper — fire-and-forget refresh without blocking the
# HTTP response.  A lock per platform prevents duplicate concurrent scrapes.
# ---------------------------------------------------------------------------
_scrape_locks: dict[str, threading.Lock] = {}
_scrape_locks_guard = threading.Lock()


def _trigger_background_scrape(platform_key: str, scrape_fn):
    """Run *scrape_fn* in a daemon thread if one isn't already running for
    *platform_key*.  Returns immediately."""
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
    """Generic handler: return existing data immediately; if stale, trigger a
    background scrape so the *next* request gets fresh data."""
    raw = collector.collect_all(geo=geo, **collect_kwargs)

    if scrape_fn and _needs_scrape(raw, platform_db_name, freshness_hours, niche_name):
        _trigger_background_scrape(platform_db_name, scrape_fn)

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
            existing_otp = session.query(OtpCode).filter(OtpCode.user_id == user.id, OtpCode.used == 0).first()
            if existing_otp:
                existing_otp.code = TEST_ACCOUNT_OTP
                existing_otp.created_at = datetime.utcnow()
            else:
                session.add(OtpCode(user_id=user.id, code=TEST_ACCOUNT_OTP))
        return {"message": "OTP sent", "email": email}

    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=403, detail="Email not whitelisted")

        user_id = user.id
        code = secrets.token_hex(3).upper()  # 6-char hex code
        existing_otp = session.query(OtpCode).filter(OtpCode.user_id == user_id, OtpCode.used == 0).first()
        if existing_otp:
            existing_otp.code = code
            existing_otp.created_at = datetime.utcnow()
        else:
            session.add(OtpCode(user_id=user_id, code=code))

    try:
        _send_email(
            to_email=email,
            subject="Your Trends Research login code",
            html_body=f"<p>Your one-time login code is: <strong>{code}</strong></p>"
                      f"<p>This code expires in 10 minutes.</p>",
        )
    except Exception as e:
        logger.error(f"Failed to send OTP email to {email}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send OTP email: {type(e).__name__}: {e}")

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
def list_users(authorization: str = Header(None)):
    """List all whitelisted users. Admin only."""
    _require_admin(authorization)
    with session_scope() as session:
        rows = session.query(User.email, User.role, User.created_at).order_by(User.created_at).all()
    return [{"email": r.email, "role": r.role, "created_at": r.created_at} for r in rows]


@app.post("/auth/users")
def add_user(user: UserCreate, authorization: str = Header(None)):
    """Add a whitelisted user. Admin only."""
    _require_admin(authorization)
    if user.role not in ("admin", "trends"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'trends'")
    try:
        with session_scope() as session:
            session.add(User(email=user.email, role=user.role))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="User already exists")
    return {"message": "User added", "email": user.email, "role": user.role}


@app.put("/auth/users")
def update_user_role(email: str = Query(...), role: str = Query(...), authorization: str = Header(None)):
    """Update a user's role. Admin only."""
    _require_admin(authorization)
    if role not in ("admin", "trends"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'trends'")
    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.role = role
    return {"message": "Role updated", "email": email, "role": role}


@app.delete("/auth/users")
def delete_user(email: str = Query(...), authorization: str = Header(None)):
    """Remove a whitelisted user. Admin only."""
    _require_admin(authorization)
    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        session.delete(user)
    return {"message": "User removed", "email": email}


@app.get("/", include_in_schema=False)
async def root():
    """Serve the React SPA at the root URL."""
    _index = os.path.join(_frontend_dist, "index.html")
    if os.path.isdir(_frontend_dist) and os.path.isfile(_index):
        return FileResponse(_index)
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
    authorization: str = Header(None),
):
    """Import a Google Trends JSON file. Admin only."""
    _require_admin(authorization)
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
        _trigger_background_scrape(
            f"trending_now_{geo}",
            lambda: collector.run_trending_now_scraper(geo=geo, trend_type=trend_type),
        )

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
    raw_data = collector.collect_all(geo=geo, include_youtube=True)

    needs_scrape = True
    if not raw_data.empty and 'platform' in raw_data.columns:
        yt_data = raw_data[raw_data['platform'] == "YouTube"]
        if not yt_data.empty:
            niche_keywords = _get_niche_keywords_from_db(niche_name)
            niche_yt_data = yt_data[yt_data['keyword'].isin(niche_keywords)]
            if not niche_yt_data.empty:
                last_extracted = pd.to_datetime(niche_yt_data['extracted_at']).max()
                if datetime.now() - last_extracted.to_pydatetime() < timedelta(hours=24):
                    needs_scrape = False

    if needs_scrape:
        niche_keywords = _get_niche_keywords_from_db(niche_name)
        _trigger_background_scrape(
            f"youtube_{niche_name}",
            lambda: collector.run_youtube_trends_scraper(keywords=niche_keywords[:5]),
        )

    if not raw_data.empty:
        yt_data = raw_data[raw_data['platform'] == "YouTube"].copy()
        if not yt_data.empty:
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
# Test scraper connectivity — per-platform health check
# ---------------------------------------------------------------------------

@app.get("/test_scraper/{platform}")
def test_scraper(platform: str, authorization: str = Header(None)):
    """Test whether a specific scraper platform is reachable and properly configured.

    Returns ``{"ok": true/false, "message": "..."}`` with a normalized
    human-readable explanation when something is wrong.
    """
    _require_admin(authorization)
    platform_lower = platform.lower()

    try:
        if platform_lower == "google_trends":
            # Google Trends uses Scrapy — just verify the spider module is importable
            try:
                spider_dir = os.path.join(PROJECT_ROOT, "src", "scrapers", "google_trends_scraper")
                if spider_dir not in sys.path:
                    sys.path.insert(0, spider_dir)
                from google_trends.spiders.trends_spider import TrendsSpider  # noqa: F401
                return {"ok": True, "message": "Google Trends spider is available."}
            except ImportError as e:
                return {"ok": False, "message": f"Google Trends spider not installed: {e}"}

        elif platform_lower == "reddit":
            token = os.getenv("ENSEMBLEDATA_TOKEN", "")
            if not token:
                return {"ok": False, "message": "ENSEMBLEDATA_TOKEN is not set. Configure it in the .env file."}
            from ensembledata.api import EDClient
            client = EDClient(token=token)
            result = client.reddit.search_subreddits(query="test", limit=1)
            _ = result.data
            return {"ok": True, "message": f"Reddit API is reachable. Units charged: {result.units_charged}"}

        elif platform_lower == "hackernews":
            import urllib.request
            req = urllib.request.Request(
                "https://hacker-news.firebaseio.com/v0/topstories.json",
                headers={"User-Agent": "TrendsResearch/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if isinstance(data, list) and len(data) > 0:
                return {"ok": True, "message": f"Hacker News API is reachable. {len(data)} top stories available."}
            return {"ok": False, "message": "Hacker News API returned unexpected data."}

        elif platform_lower == "youtube":
            token = os.getenv("ENSEMBLEDATA_TOKEN", "")
            if not token:
                return {"ok": False, "message": "ENSEMBLEDATA_TOKEN is not set. Configure it in the .env file."}
            from ensembledata.api import EDClient
            client = EDClient(token=token)
            result = client.youtube.search(query="test", max_results=1)
            _ = result.data
            return {"ok": True, "message": f"YouTube API is reachable. Units charged: {result.units_charged}"}

        elif platform_lower == "news":
            api_key = os.getenv("NEWS_API_KEY", "")
            if not api_key or api_key == "YOUR_NEWSAPI_KEY":
                return {"ok": False, "message": "NEWS_API_KEY is not set. Get a key from newsapi.org and add it to .env."}
            import urllib.request
            url = f"https://newsapi.org/v2/everything?q=test&pageSize=1&apiKey={api_key}"
            req = urllib.request.Request(url, headers={"User-Agent": "TrendsResearch/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if data.get("status") == "ok":
                return {"ok": True, "message": f"NewsAPI is reachable. {data.get('totalResults', 0)} results available."}
            return {"ok": False, "message": f"NewsAPI error: {data.get('message', 'Unknown error')}"}

        elif platform_lower == "tiktok":
            token = os.getenv("ENSEMBLEDATA_TOKEN", "")
            if not token:
                return {"ok": False, "message": "ENSEMBLEDATA_TOKEN is not set. Configure it in the .env file."}
            from ensembledata.api import EDClient
            client = EDClient(token=token)
            result = client.tiktok.keyword.search(keyword="test", period=7, max_cursor=0)
            _ = result.data
            return {"ok": True, "message": f"TikTok API is reachable. Units charged: {result.units_charged}"}

        elif platform_lower == "instagram":
            token = os.getenv("ENSEMBLEDATA_TOKEN", "")
            if not token:
                return {"ok": False, "message": "ENSEMBLEDATA_TOKEN is not set. Configure it in the .env file."}
            from ensembledata.api import EDClient
            client = EDClient(token=token)
            result = client.instagram.search(query="test")
            _ = result.data
            return {"ok": True, "message": f"Instagram API is reachable. Units charged: {result.units_charged}"}

        elif platform_lower == "threads":
            token = os.getenv("ENSEMBLEDATA_TOKEN", "")
            if not token:
                return {"ok": False, "message": "ENSEMBLEDATA_TOKEN is not set. Configure it in the .env file."}
            from ensembledata.api import EDClient
            client = EDClient(token=token)
            result = client.threads.search(query="test")
            _ = result.data
            return {"ok": True, "message": f"Threads API is reachable. Units charged: {result.units_charged}"}

        else:
            return {"ok": False, "message": f"Unknown platform: {platform}"}

    except Exception as exc:
        # Normalize common error patterns
        err = str(exc)
        if "401" in err or "Unauthorized" in err or "Invalid token" in err.lower():
            return {"ok": False, "message": f"Authentication failed for {platform}. Check your API key/token."}
        if "403" in err or "Forbidden" in err:
            return {"ok": False, "message": f"Access denied for {platform}. Your API key may lack permissions or be expired."}
        if "429" in err or "rate limit" in err.lower():
            return {"ok": False, "message": f"Rate limit exceeded for {platform}. Try again later."}
        if "timeout" in err.lower() or "timed out" in err.lower():
            return {"ok": False, "message": f"{platform} API timed out. The service may be temporarily unavailable."}
        if "connection" in err.lower() or "unreachable" in err.lower() or "dns" in err.lower():
            return {"ok": False, "message": f"Cannot connect to {platform} API. Check your network connection."}
        return {"ok": False, "message": f"{platform} error: {err}"}


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
    limit: int = Query(500, description="Max rows to return. Use 0 for all."),
    offset: int = Query(0, description="Number of rows to skip (for pagination)."),
    date_from: Optional[str] = Query(None, description="Filter ads with start_date >= this (YYYY-MM-DD)."),
    date_to: Optional[str] = Query(None, description="Filter ads with start_date <= this (YYYY-MM-DD)."),
    platform_filter: Optional[str] = Query(None, description="Filter by platform substring (e.g. FACEBOOK)."),
    format_filter: Optional[str] = Query(None, description="Filter by display_format (e.g. VIDEO, IMAGE)."),
    keyword_filter: Optional[str] = Query(None, description="Filter by search_keyword (exact match)."),
    brand_filter: Optional[str] = Query(None, description="Filter by brand_name substring."),
    perf_filter: Optional[str] = Query(None, description="Filter by performance_score_title (e.g. Winning)."),
    sort_by: str = Query("extracted_at", description="Column to sort by."),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc."),
):
    _SORTABLE = {
        "extracted_at": AdsInsight.extracted_at,
        "start_date": AdsInsight.start_date,
        "end_date": AdsInsight.end_date,
        "days_active": AdsInsight.days_active,
        "performance_score": AdsInsight.performance_score,
        "used_count": AdsInsight.used_count,
        "brand_name": AdsInsight.brand_name,
        "brand_active_ads": AdsInsight.brand_active_ads,
    }
    with session_scope() as session:
        q = session.query(
            AdsInsight.hookd_id, AdsInsight.external_id, AdsInsight.search_keyword,
            AdsInsight.platform, AdsInsight.display_format, AdsInsight.title, AdsInsight.body,
            AdsInsight.landing_page, AdsInsight.cta_type, AdsInsight.cta_text,
            AdsInsight.start_date, AdsInsight.end_date, AdsInsight.days_active, AdsInsight.active_in_library,
            AdsInsight.performance_score, AdsInsight.performance_score_title, AdsInsight.used_count,
            AdsInsight.age_audience_min, AdsInsight.age_audience_max, AdsInsight.gender_audience, AdsInsight.eu_total_reach,
            AdsInsight.ad_spend_range_score, AdsInsight.ad_spend_range_score_title,
            AdsInsight.brand_name, AdsInsight.brand_logo_url, AdsInsight.brand_active_ads,
            AdsInsight.media, AdsInsight.ad_cards, AdsInsight.share_url,
            AdsInsight.extracted_at,
        )
        # --- Filters ---
        if niche_name:
            kws = _get_niche_keywords_from_db(niche_name)
            if kws:
                q = q.filter(AdsInsight.search_keyword.in_(kws))
        if date_from:
            q = q.filter(AdsInsight.start_date >= date_from)
        if date_to:
            q = q.filter(AdsInsight.start_date <= date_to)
        if platform_filter:
            q = q.filter(AdsInsight.platform.contains(platform_filter))
        if format_filter:
            q = q.filter(AdsInsight.display_format == format_filter)
        if keyword_filter:
            q = q.filter(AdsInsight.search_keyword == keyword_filter)
        if brand_filter:
            q = q.filter(AdsInsight.brand_name.contains(brand_filter))
        if perf_filter:
            q = q.filter(AdsInsight.performance_score_title == perf_filter)

        # --- Total count (before pagination) ---
        total_count = q.count()

        # --- Sorting ---
        sort_col = _SORTABLE.get(sort_by, AdsInsight.extracted_at)
        if sort_dir.lower() == "asc":
            q = q.order_by(sort_col.asc())
        else:
            q = q.order_by(sort_col.desc())

        # --- Pagination ---
        if offset > 0:
            q = q.offset(offset)
        if limit > 0:
            q = q.limit(limit)
        # limit=0 means return all rows (no limit applied)

        rows = q.all()

    columns = [
        "hookd_id", "external_id", "search_keyword",
        "platform", "display_format", "title", "body",
        "landing_page", "cta_type", "cta_text",
        "start_date", "end_date", "days_active", "active_in_library",
        "performance_score", "performance_score_title", "used_count",
        "age_audience_min", "age_audience_max", "gender_audience", "eu_total_reach",
        "ad_spend_range_score", "ad_spend_range_score_title",
        "brand_name", "brand_logo_url", "brand_active_ads",
        "media", "ad_cards", "share_url", "extracted_at",
    ]
    if not rows:
        return {"data": [], "total": total_count}
    df = pd.DataFrame(rows, columns=columns)
    return {"data": _sanitize(df), "total": total_count}


@app.get("/ads_insight/filters")
def get_ads_insight_filters():
    """Return distinct filter values for the ads_insight table."""
    result = {}
    with session_scope() as session:
        # Distinct platforms
        rows = session.query(AdsInsight.platform).distinct().all()
        all_platforms = set()
        for (p,) in rows:
            if p:
                for part in p.split(", "):
                    all_platforms.add(part.strip())
        result["platforms"] = sorted(all_platforms)

    with session_scope() as session:
        # Distinct formats
        rows = session.query(AdsInsight.display_format).distinct().all()
        result["formats"] = sorted([r[0] for r in rows if r[0]])

    with session_scope() as session:
        # Distinct keywords
        rows = session.query(AdsInsight.search_keyword).distinct().all()
        result["keywords"] = sorted([r[0] for r in rows if r[0]])

    with session_scope() as session:
        # Distinct performance tiers
        rows = session.query(AdsInsight.performance_score_title).distinct().all()
        result["performance_tiers"] = sorted([r[0] for r in rows if r[0]])

    with session_scope() as session:
        # Distinct brands
        rows = session.query(AdsInsight.brand_name).distinct().all()
        result["brands"] = sorted([r[0] for r in rows if r[0]])

    with session_scope() as session:
        # Date range
        row = session.execute(
            text("SELECT MIN(start_date), MAX(start_date) FROM ads_insight")
        ).fetchone()
        result["date_range"] = {"min": row[0], "max": row[1]} if row else {"min": None, "max": None}

    return result


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
# My Brands — track your own brands
# ---------------------------------------------------------------------------

class MyBrandRequest(BaseModel):
    brand_name: str
    brand_external_id: str | None = None
    brand_logo_url: str | None = None
    brand_active_ads: int = 0


@app.get("/my_brands")
def list_my_brands():
    """Return all tracked brands."""
    with session_scope() as session:
        rows = session.query(MyBrand).order_by(MyBrand.added_at.desc()).all()
        return {
            "data": [
                {
                    "id": r.id,
                    "brand_name": r.brand_name,
                    "brand_external_id": r.brand_external_id,
                    "brand_logo_url": r.brand_logo_url,
                    "brand_active_ads": r.brand_active_ads,
                    "added_at": str(r.added_at) if r.added_at else None,
                }
                for r in rows
            ]
        }


@app.post("/my_brands")
def add_my_brand(body: MyBrandRequest, background_tasks: BackgroundTasks):
    """Add a brand to track and optionally trigger a brand spy scrape."""
    with session_scope() as session:
        # Check if already tracked
        existing = session.query(MyBrand).filter(
            MyBrand.brand_name == body.brand_name
        ).first()
        if existing:
            return {"message": "Brand already tracked", "id": existing.id}

        brand = MyBrand(
            brand_name=body.brand_name,
            brand_external_id=body.brand_external_id,
            brand_logo_url=body.brand_logo_url,
            brand_active_ads=body.brand_active_ads,
        )
        session.add(brand)
        session.flush()
        brand_id = brand.id

    # Trigger brand spy scrape in background if external_id is available
    if body.brand_external_id and HAS_GETHOOKEDAI:
        # Search for the brand's ads by brand name to populate ads_insight
        background_tasks.add_task(
            _run_and_log, gethookd_scrape_ads,
            "ads_insight", [body.brand_name], None,
            keywords=[body.brand_name], max_pages=5,
        )

    return {"message": f"Brand '{body.brand_name}' added to tracking", "id": brand_id}


@app.delete("/my_brands/{brand_id}")
def remove_my_brand(brand_id: int):
    """Remove a tracked brand."""
    with session_scope() as session:
        brand = session.query(MyBrand).filter(MyBrand.id == brand_id).first()
        if not brand:
            raise HTTPException(status_code=404, detail="Brand not found")
        session.delete(brand)
    return {"ok": True}


@app.get("/my_brands/ads")
def get_my_brand_ads(
    limit: int = Query(500, description="Max rows. 0 for all."),
    offset: int = Query(0),
    brand_name: Optional[str] = Query(None, description="Filter by specific tracked brand."),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    platform_filter: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("start_date"),
    sort_dir: Optional[str] = Query("desc"),
):
    """Return ads from the ads_insight table that belong to tracked brands."""
    with session_scope() as session:
        # Get all tracked brand names
        tracked = session.query(MyBrand.brand_name).all()
        tracked_names = [r[0] for r in tracked if r[0]]

    if not tracked_names:
        return {"data": [], "total": 0, "tracked_brands": []}

    with session_scope() as session:
        q = session.query(AdsInsight).filter(AdsInsight.brand_name.in_(tracked_names))

        if brand_name:
            q = q.filter(AdsInsight.brand_name == brand_name)
        if date_from:
            q = q.filter(AdsInsight.start_date >= date_from)
        if date_to:
            q = q.filter(AdsInsight.start_date <= date_to)
        if platform_filter:
            q = q.filter(AdsInsight.platform.contains(platform_filter))

        total = q.count()

        # Sorting
        sort_col = getattr(AdsInsight, sort_by, AdsInsight.start_date)
        q = q.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())

        if limit > 0:
            q = q.offset(offset).limit(limit)
        elif offset > 0:
            q = q.offset(offset)

        rows = q.all()

        cols = [
            "id", "hookd_id", "external_id", "search_keyword", "platform",
            "display_format", "title", "body", "landing_page", "cta_type", "cta_text",
            "start_date", "end_date", "days_active", "active_in_library",
            "performance_score", "performance_score_title", "used_count",
            "age_audience_min", "age_audience_max", "gender_audience",
            "eu_total_reach", "ad_spend_range_score", "ad_spend_range_score_title",
            "brand_name", "brand_logo_url", "brand_active_ads",
            "media", "ad_cards", "share_url", "extracted_at",
        ]
        data = [{c: getattr(r, c, None) for c in cols} for r in rows]

    return {"data": data, "total": total, "tracked_brands": tracked_names}


@app.post("/my_brands/refresh")
def refresh_my_brand_ads(background_tasks: BackgroundTasks):
    """Re-scrape ads for all tracked brands."""
    if not HAS_GETHOOKEDAI:
        raise HTTPException(status_code=501, detail="GetHookdAI scraper not available")

    with session_scope() as session:
        brands = session.query(MyBrand).all()
        brand_names = [b.brand_name for b in brands if b.brand_name]

    if not brand_names:
        return {"message": "No tracked brands to refresh"}

    background_tasks.add_task(
        _run_and_log, gethookd_scrape_ads,
        "ads_insight", brand_names, None,
        keywords=brand_names, max_pages=5,
    )
    return {"message": f"Refreshing ads for {len(brand_names)} tracked brands"}


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
def get_token_usage(authorization: str = Header(None)):
    """Return token/units consumption. Admin only."""
    _require_admin(authorization)
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
def setup_azure_schema(background_tasks: BackgroundTasks, authorization: str = Header(None)):
    """Run the Azure SQL schema setup. Admin only."""
    _require_admin(authorization)
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
    authorization: str = Header(None),
):
    """Run the database migration. Admin only."""
    _require_admin(authorization)
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
def azure_status(authorization: str = Header(None)):
    """Check Azure SQL connectivity. Admin only."""
    _require_admin(authorization)
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
def azure_diagnose(authorization: str = Header(None)):
    """Run a full connection diagnostic. Admin only."""
    _require_admin(authorization)
    try:
        diag = run_connection_diagnose()
        return diag.summary_dict()
    except Exception as e:
        return {"connected": False, "error": str(e), "strategy": "unknown"}




# ---------------------------------------------------------------------------
# Health check (used by Azure App Service and Docker HEALTHCHECK)
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    """Health check that also pings the database to prevent Azure SQL
    serverless auto-pause (which causes ~60s cold-start delays)."""
    db_ok = False
    try:
        eng = get_engine()
        if eng is not None:
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass
    return {
        "status": "healthy",
        "service": "trends-research-app",
        "database": "connected" if db_ok else "unavailable",
    }


@app.get("/debug/env")
async def debug_env():
    """Temporary debug endpoint — remove after deployment is verified."""
    return {
        "KEY_VAULT_NAME": os.environ.get("KEY_VAULT_NAME", "NOT SET"),
        "RESEND_API_KEY_set": bool(os.getenv("RESEND_API_KEY")),
        "RESEND_API_KEY_prefix": (os.getenv("RESEND_API_KEY", ""))[:8] + "..." if os.getenv("RESEND_API_KEY") else "EMPTY",
        "RESEND_FROM_EMAIL": os.getenv("RESEND_FROM_EMAIL", "NOT SET"),
        "AZURE_SQL_SERVER_set": bool(os.getenv("AZURE_SQL_SERVER")),
        "AZURE_SQL_USER_set": bool(os.getenv("AZURE_SQL_USER")),
        "db_engine_ok": engine is not None,
    }


@app.get("/debug/test_otp")
async def debug_test_otp(email: str = Query("test@test.com")):
    """Temporary debug endpoint to test OTP flow step by step."""
    result = {"steps": []}
    try:
        result["steps"].append("1. Starting")
        with session_scope() as session:
            result["steps"].append("2. Session opened")
            user = session.query(User).filter(User.email == email).first()
            result["steps"].append(f"3. User query done: {'found' if user else 'NOT FOUND'}")
            if not user:
                result["error"] = f"User {email} not in users table"
                return result
            result["steps"].append(f"4. User id={user.id}, role={user.role}")
            code = secrets.token_hex(3).upper()
            session.add(OtpCode(user_id=user.id, code=code))
            result["steps"].append("5. OTP code created")
        result["steps"].append("6. Session committed")
        result["steps"].append(f"7. Email from={EMAIL_FROM}")
        _send_email(
            to_email=email,
            subject="Test OTP",
            html_body=f"<p>Code: <strong>{code}</strong></p>",
        )
        result["steps"].append("8. Email sent!")
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        import traceback
        result["traceback"] = traceback.format_exc()
    return result


# ---------------------------------------------------------------------------
# SPA catch-all: serve React index.html for any route not matched by the API
# ---------------------------------------------------------------------------
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    """Serve the React SPA for any non-API route."""
    _index = os.path.join(_frontend_dist, "index.html")
    if os.path.isdir(_frontend_dist) and os.path.isfile(_index):
        return FileResponse(_index)
    raise HTTPException(status_code=404, detail="Frontend not built. Run: cd frontend && pnpm build")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Trends Research API")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    args = parser.parse_args()

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)

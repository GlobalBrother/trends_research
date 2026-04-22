"""FastAPI application entry point.
Endpoint logic lives in ``src/api/routes/*``; this module only wires
everything together (app construction, middleware, startup hooks, router
registration, the root handler, and the SPA catch-all).
"""
import logging
import os
import sys
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
load_dotenv()
# Ensure project root is on sys.path so `src.*` imports work in any environment (e.g. WSL).
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from src.config import CORS_ORIGINS, PROJECT_ROOT
from src.collector.trend_collector import TrendCollector  # re-exported for tests
from src.analytics.analytics_engine import AnalyticsEngine  # re-exported for tests
from src.db.connection import session_scope
from src.db.models import Base
from src.db.sql_compat import seed_niches
from src.api.dependencies import (
    analytics,
    collector,
    engine,
    niche,
    TEST_ACCOUNT_EMAIL,
)
from src.api.routes import (
    admin as admin_routes,
    ads as ads_routes,
    auth as auth_routes,
    content as content_routes,
    niches as niches_routes,
    scrape as scrape_routes,
    trends as trends_routes,
)
from src.api.schemas import RootResponse
# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
# ---------------------------------------------------------------------------
# App & middleware
# ---------------------------------------------------------------------------
app = FastAPI(title="Trends Research API", version="2.0.0")
def _check_test_account_env_guard() -> None:
    """Fail loudly if the dev-only OTP bypass is enabled in production."""
    env = os.getenv("ENV", "").strip().lower()
    test_email = os.getenv("TEST_ACCOUNT_EMAIL", "").strip()
    if env in {"production", "prod"} and test_email:
        raise RuntimeError(
            "Refusing to start: TEST_ACCOUNT_EMAIL is set in a production environment."
        )
    if test_email:
        logger.warning(
            "OTP bypass is ACTIVE for test account %r (ENV=%r). "
            "This must never be enabled in production.",
            test_email,
            env or "<unset>",
        )
@app.on_event("startup")
def _startup_test_account_guard() -> None:
    _check_test_account_env_guard()
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
# Schema bootstrapping
# ---------------------------------------------------------------------------
def _init_schema():
    """Ensure all tables and indexes exist on startup."""
    if engine is None:
        logger.warning("Skipping startup migration -- no database engine available.")
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
        logger.warning("Migration failed, falling back to create_all: %s", e)
        try:
            Base.metadata.create_all(engine)
        except Exception as e2:
            logger.warning("Could not create tables via ORM: %s", e2)
# Skip DB-touching bootstrap when running under pytest or when explicitly
# disabled — these calls block on Azure SQL during test collection.
_SKIP_DB_INIT = (
    os.getenv("SKIP_DB_INIT", "").lower() in {"1", "true", "yes"}
    or "PYTEST_CURRENT_TEST" in os.environ
    or "pytest" in sys.modules
)
if not _SKIP_DB_INIT:
    _init_schema()
def _init_niches_table():
    """Idempotently seed the niches table from NICHE_SEED_KEYWORDS."""
    try:
        with session_scope() as session:
            inserted = seed_niches(session)
            if inserted:
                logger.info("Seeded %d new niche row(s) from defaults.", inserted)
    except Exception as e:
        logger.warning(f"Could not seed niches table: {e}")
if not _SKIP_DB_INIT:
    _init_niches_table()
else:
    logger.info("Skipping _init_schema/_init_niches_table (pytest or SKIP_DB_INIT detected).")
# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth_routes.router)
app.include_router(niches_routes.router)
app.include_router(trends_routes.router)
app.include_router(content_routes.router)
app.include_router(ads_routes.router)
app.include_router(scrape_routes.router)
app.include_router(admin_routes.router)
# ---------------------------------------------------------------------------
# Root + SPA catch-all
# ---------------------------------------------------------------------------
@app.get("/api", response_model=RootResponse)
def api_status():
    """Programmatic API status endpoint (used to live at ``/``)."""
    return {"message": "Trends Research API v2.0 is running"}


@app.get("/", include_in_schema=False)
def root():
    """Serve the React SPA at the site root if the build exists.

    Falls back to the JSON status message when the frontend hasn't been
    built (e.g. local dev runs without ``pnpm build``).
    """
    _index = os.path.join(_frontend_dist, "index.html")
    if os.path.isdir(_frontend_dist) and os.path.isfile(_index):
        return FileResponse(_index)
    return {"message": "Trends Research API v2.0 is running (frontend not built)"}


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

"""Admin endpoints (`/admin/*`, `/table_filters`).

``/table_filters`` is included here because it is an internal/admin-style
introspection endpoint with no front-facing equivalent in the original
spec's per-concern split.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from sqlalchemy import func, text

from src.api.dependencies import (
    engine,
    logger,
    session_scope,
)
from src.api.schemas import (
    AzureDiagnoseResponse,
    AzureStatusResponse,
    MessageResponse,
    MigrationResponse,
    ResetDefaultsResponse,
    TableFiltersResponse,
    TokenUsageResponse,
)
from src.db.connection import diagnose as run_connection_diagnose
from src.db.connection import get_last_diagnostic
from src.db.models import (
    AdsInsight,
    Base,
    Content,
    ScrapeError as ScrapeErrorModel,
    TokenUsage,
    Trend,
)
from src.db.sql_compat import reset_niches_to_defaults

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------------------
# Niche defaults (admin)
# ---------------------------------------------------------------------------

@router.post("/admin/niches/reset_defaults", response_model=ResetDefaultsResponse)
def reset_niches_defaults():
    """Restore the default seeded niches without touching user-created rows.

    Deletes every row where ``is_seed = True`` and then re-runs the seeder
    from ``NICHE_SEED_KEYWORDS``. Rows created or modified by users
    (``is_seed = False``) are preserved.
    """
    try:
        with session_scope() as session:
            stats = reset_niches_to_defaults(session)
        return {"message": "Default niches reset", **stats}
    except Exception as e:
        logger.error("Failed to reset default niches: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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


@router.get("/table_filters", response_model=TableFiltersResponse)
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
# Token usage
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


@router.get("/admin/token_usage", response_model=TokenUsageResponse)
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

@router.post("/admin/azure/setup_schema", response_model=MessageResponse)
def setup_azure_schema(background_tasks: BackgroundTasks):
    """Run the Azure SQL schema setup (create tables & indexes)."""
    try:
        from src.db.setup_azure import run_schema
        background_tasks.add_task(run_schema)
        return {"message": "Azure schema setup started in background"}
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"setup_azure module not found: {e}")


@router.post("/admin/azure/migrate", response_model=MigrationResponse)
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


@router.get("/admin/azure/status", response_model=AzureStatusResponse)
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


@router.get("/admin/azure/diagnose", response_model=AzureDiagnoseResponse)
def azure_diagnose():
    """Run a full connection diagnostic (resets engine and retests everything)."""
    try:
        diag = run_connection_diagnose()
        return diag.summary_dict()
    except Exception as e:
        return {"connected": False, "error": str(e), "strategy": "unknown"}


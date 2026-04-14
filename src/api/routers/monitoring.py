import logging
import os
import re
from typing import Optional, List

from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy import func

from src.db.connection import session_scope, get_last_diagnostic
from src.db.models import (
    ReportBrief, BacktestRun, Content, Trend, AdsInsight, ScrapeError,
    TrendCluster, TrendSignal, TrendInsight, TrendAdMatch, InsightFeedback, Base
)
from src.api.instances import pipeline
from src.api.utils import decode_json_field, ensure_cluster_snapshot
from src.api.deps import get_current_user

router = APIRouter(tags=["monitoring"])
logger = logging.getLogger(__name__)

_TABLE_MODEL_MAP = {
    "content": Content,
    "trends": Trend,
    "ads_insight": AdsInsight,
    "scrape_errors": ScrapeError,
    "trend_clusters": TrendCluster,
    "trend_signals": TrendSignal,
    "trend_insights": TrendInsight,
    "trend_ad_matches": TrendAdMatch,
    "insight_feedback": InsightFeedback,
}


@router.get("/health")
def health_check():
    """Return 200 if the API is up, with DB connectivity status."""
    diag = get_last_diagnostic()
    return {
        "status": "healthy",
        "database": "connected" if diag and diag.get("success") else "disconnected",
        "last_check": diag.get("timestamp") if diag else None
    }


@router.get("/monitoring/platform_health")
def get_platform_health(force_refresh: bool = Query(False)):
    """Return snapshot of data freshness and volume per platform."""
    ensure_cluster_snapshot(pipeline, force=force_refresh)
    with session_scope() as session:
        return pipeline.build_monitoring_snapshot(session)


@router.get("/reports/generated")
def get_generated_reports(force_refresh: bool = Query(False)):
    """Return recently generated AI reports."""
    ensure_cluster_snapshot(pipeline, force=force_refresh)
    with session_scope() as session:
        rows = session.query(ReportBrief).order_by(ReportBrief.created_at.desc()).limit(20).all()
    
    return {
        "data": [
            {
                "id": r.id,
                "report_type": r.report_type,
                "title": r.title,
                "cluster_id": r.cluster_id,
                "content": decode_json_field(r.content_json, {}),
                "created_at": r.created_at,
            }
            for r in rows
        ]
    }


@router.post("/reports/generate")
def generate_reports():
    """Trigger a fresh report generation sync."""
    result = ensure_cluster_snapshot(pipeline, force=True)
    return {"message": "Reports generated", **result}


@router.get("/backtests")
def get_backtests(force_refresh: bool = Query(False)):
    """Return history of backtest runs."""
    if force_refresh:
        ensure_cluster_snapshot(pipeline, force=True)
    with session_scope() as session:
        rows = session.query(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(20).all()
    
    return {
        "data": [
            {
                "id": r.id,
                "run_label": r.run_label,
                "window_start": r.window_start,
                "window_end": r.window_end,
                "total_clusters": r.total_clusters,
                "matched_clusters": r.matched_clusters,
                "avg_opportunity_score": r.avg_opportunity_score,
                "precision_proxy": r.precision_proxy,
                "recall_proxy": r.recall_proxy,
                "summary": decode_json_field(r.summary_json, {}),
                "created_at": r.created_at,
            }
            for r in rows
        ]
    }


@router.get("/table_filters")
def get_table_filters(
    table_name: str = Query(...),
    geo_col: str = Query("geo"),
    keyword_col: str = Query("search_keyword"),
):
    """Return distinct geo and keyword values from a given DB table for UI dropdowns."""
    _safe = re.compile(r"^\w+$")
    if not _safe.match(table_name) or not _safe.match(geo_col) or not _safe.match(keyword_col):
        raise HTTPException(status_code=400, detail="Invalid table/column name")

    geos, keywords = ["Global"], ["All"]
    try:
        model = _TABLE_MODEL_MAP.get(table_name)
        if not model:
            # Try to find by tablename
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
                rows = session.query(geo_attr).filter(geo_attr.isnot(None), geo_attr != "").distinct().all()
                geos_raw = sorted(set(r[0] for r in rows if r[0]))
                if geos_raw: geos = ["All"] + geos_raw

            if kw_attr is not None:
                rows = session.query(kw_attr).filter(kw_attr.isnot(None), kw_attr != "").distinct().all()
                kws_raw = sorted(set(r[0] for r in rows if r[0]))
                if kws_raw: keywords = ["All"] + kws_raw

    except Exception as e:
        logger.warning(f"Failed to fetch table filters for {table_name}: {e}")
    
    return {"geos": geos, "keywords": keywords}

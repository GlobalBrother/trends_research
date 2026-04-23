"""Cluster / insight / report / backtest endpoints.

These were originally defined in ``src/api/main.py`` and migrated here as
part of the Tier 2.5 router split. Tests patch ``session_scope`` and
``_ensure_cluster_snapshot`` on THIS module, so keep those names bound at
module scope.
"""

from typing import Optional

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func

from src.api.dependencies import _sanitize, session_scope
from src.db.models import (
    AdsInsight,
    BacktestRun,
    InsightFeedback,
    ReportBrief,
    TrendAdMatch,
    TrendCluster,
    TrendInsight,
    TrendSignal,
)

router = APIRouter(tags=["insights"])


# ---------------------------------------------------------------------------
# Snapshot freshness helpers
# ---------------------------------------------------------------------------

def _cluster_snapshot_stale(session, max_age_hours: int = 6) -> bool:
    latest = session.query(func.max(TrendCluster.updated_at)).scalar()
    if latest is None:
        return True
    from datetime import datetime
    return (datetime.utcnow() - latest).total_seconds() > (max_age_hours * 3600)


def _ensure_cluster_snapshot(force: bool = False) -> dict:
    """Ensure the trend-cluster snapshot is fresh; refresh via the insight pipeline if needed."""
    # Import lazily so tests can monkeypatch this whole function without
    # eagerly building the pipeline.
    from src.api.dependencies import pipeline

    with session_scope() as session:
        if not force and not _cluster_snapshot_stale(session):
            return {"refreshed": False}
        result = pipeline.sync(session)
        return {"refreshed": True, **result}


# ---------------------------------------------------------------------------
# JSON field helper (kept local to avoid a cross-module import dependency)
# ---------------------------------------------------------------------------

def _decode_json_field(value, fallback=None):
    import json as _json
    if value in (None, "", "null"):
        return [] if fallback is None else fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return _json.loads(value)
    except Exception:
        return fallback if fallback is not None else value


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class InsightFeedbackRequest(BaseModel):
    useful: bool
    rating: Optional[int] = None
    used_in_campaign: bool = False
    outcome: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/clusters/refresh")
def refresh_clusters(background_tasks: BackgroundTasks):
    background_tasks.add_task(_ensure_cluster_snapshot, True)
    return {"message": "Cluster refresh started in background"}


@router.get("/clusters")
def get_clusters(
    stage: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    limit: int = Query(100),
    force_refresh: bool = Query(False),
):
    _ensure_cluster_snapshot(force=force_refresh)
    with session_scope() as session:
        q = session.query(TrendCluster, TrendInsight).outerjoin(
            TrendInsight, TrendInsight.cluster_id == TrendCluster.id
        )
        if stage:
            q = q.filter(TrendCluster.lifecycle_stage == stage)
        if platform:
            q = q.filter(TrendCluster.platforms.contains(platform))
        if date:
            parsed = pd.to_datetime(date, errors="coerce")
            if pd.notna(parsed):
                q = q.filter(TrendCluster.last_seen >= parsed.to_pydatetime())
        rows = q.order_by(TrendCluster.last_seen.desc()).limit(limit).all()

    data = []
    for cluster, insight in rows:
        data.append({
            "id": cluster.id,
            "cluster_key": cluster.cluster_key,
            "title": cluster.title,
            "keywords": _decode_json_field(cluster.cluster_keywords, []),
            "platforms": _decode_json_field(cluster.platforms, []),
            "primary_platform": cluster.primary_platform,
            "first_seen": cluster.first_seen,
            "last_seen": cluster.last_seen,
            "lifecycle_stage": cluster.lifecycle_stage,
            "confidence_score": cluster.confidence_score,
            "freshness_score": cluster.freshness_score,
            "source_confidence": cluster.source_confidence,
            "trend_strength": cluster.trend_strength,
            "quality_score": cluster.quality_score,
            "ad_opportunity_score": insight.ad_opportunity_score if insight else None,
            "audience_intent": insight.audience_intent if insight else None,
            "timing_window": insight.ad_timing_window if insight else None,
            "brand_safety_risk": insight.brand_safety_risk if insight else None,
            "saturation_risk": insight.saturation_risk if insight else None,
        })
    return {"data": _sanitize(pd.DataFrame(data)) if data else []}


@router.get("/clusters/{cluster_id}")
def get_cluster(cluster_id: int, force_refresh: bool = Query(False)):
    _ensure_cluster_snapshot(force=force_refresh)
    with session_scope() as session:
        row = (
            session.query(TrendCluster, TrendInsight)
            .outerjoin(TrendInsight, TrendInsight.cluster_id == TrendCluster.id)
            .filter(TrendCluster.id == cluster_id)
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Cluster not found")
        cluster, insight = row
        feedback_rows = (
            session.query(
                func.count(InsightFeedback.id).label("count"),
                func.avg(InsightFeedback.rating).label("avg_rating"),
                func.sum(InsightFeedback.useful).label("useful_votes"),
            )
            .filter(InsightFeedback.cluster_id == cluster_id)
            .first()
        )
    return {
        "id": cluster.id,
        "cluster_key": cluster.cluster_key,
        "title": cluster.title,
        "keywords": _decode_json_field(cluster.cluster_keywords, []),
        "platforms": _decode_json_field(cluster.platforms, []),
        "lifecycle_stage": cluster.lifecycle_stage,
        "confidence_score": cluster.confidence_score,
        "freshness_score": cluster.freshness_score,
        "source_confidence": cluster.source_confidence,
        "trend_strength": cluster.trend_strength,
        "quality_score": cluster.quality_score,
        "explanation": _decode_json_field(cluster.explanation_json, {}),
        "insight": None if not insight else {
            "ad_opportunity_score": insight.ad_opportunity_score,
            "audience_intent": insight.audience_intent,
            "creative_angle_candidates": _decode_json_field(insight.creative_angle_candidates, []),
            "platform_fit": _decode_json_field(insight.platform_fit, []),
            "ad_timing_window": insight.ad_timing_window,
            "saturation_risk": insight.saturation_risk,
            "brand_safety_risk": insight.brand_safety_risk,
            "monetization_potential": insight.monetization_potential,
            "explanation": _decode_json_field(insight.explanation_json, {}),
        },
        "feedback_summary": {
            "count": int(feedback_rows.count or 0),
            "avg_rating": None if feedback_rows.avg_rating is None else round(float(feedback_rows.avg_rating), 2),
            "useful_votes": int(feedback_rows.useful_votes or 0),
        },
    }


@router.get("/clusters/{cluster_id}/signals")
def get_cluster_signals(cluster_id: int):
    _ensure_cluster_snapshot()
    with session_scope() as session:
        rows = (
            session.query(TrendSignal)
            .filter(TrendSignal.cluster_id == cluster_id)
            .order_by(TrendSignal.signal_timestamp.desc())
            .all()
        )
    return {
        "data": [
            {
                "id": row.id,
                "platform": row.platform,
                "topic": row.topic,
                "keyword": row.keyword,
                "geo": row.geo,
                "signal_timestamp": row.signal_timestamp,
                "volume": row.volume,
                "growth": row.growth,
                "engagement": row.engagement,
                "sentiment": row.sentiment,
                "freshness": row.freshness,
                "source_confidence": row.source_confidence,
                "quality_flags": _decode_json_field(row.quality_flags, []),
            }
            for row in rows
        ]
    }


@router.get("/clusters/{cluster_id}/ads")
def get_cluster_ads(cluster_id: int, limit: int = Query(10)):
    _ensure_cluster_snapshot()
    with session_scope() as session:
        rows = (
            session.query(TrendAdMatch, AdsInsight)
            .join(AdsInsight, AdsInsight.id == TrendAdMatch.ads_insight_id)
            .filter(TrendAdMatch.cluster_id == cluster_id)
            .order_by(TrendAdMatch.match_score.desc())
            .limit(limit)
            .all()
        )
    return {
        "data": [
            {
                "match_score": match.match_score,
                "match_reason": _decode_json_field(match.match_reason, {}),
                "ad": {
                    "id": ad.id,
                    "brand_name": ad.brand_name,
                    "platform": ad.platform,
                    "display_format": ad.display_format,
                    "title": ad.title,
                    "body": ad.body,
                    "cta_type": ad.cta_type,
                    "performance_score": ad.performance_score,
                    "performance_score_title": ad.performance_score_title,
                    "days_active": ad.days_active,
                    "share_url": ad.share_url,
                },
            }
            for match, ad in rows
        ]
    }


@router.get("/clusters/{cluster_id}/evidence")
def get_cluster_evidence(cluster_id: int):
    _ensure_cluster_snapshot()
    with session_scope() as session:
        cluster = session.query(TrendCluster).filter(TrendCluster.id == cluster_id).first()
        insight = session.query(TrendInsight).filter(TrendInsight.cluster_id == cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster not found")
        rows = (
            session.query(TrendAdMatch, AdsInsight)
            .join(AdsInsight, AdsInsight.id == TrendAdMatch.ads_insight_id)
            .filter(TrendAdMatch.cluster_id == cluster_id)
            .all()
        )
    brand_counts: dict = {}
    format_counts: dict = {}
    cta_counts: dict = {}
    for _, ad in rows:
        if ad.brand_name:
            brand_counts[ad.brand_name] = brand_counts.get(ad.brand_name, 0) + 1
        if ad.display_format:
            format_counts[ad.display_format] = format_counts.get(ad.display_format, 0) + 1
        if ad.cta_type:
            cta_counts[ad.cta_type] = cta_counts.get(ad.cta_type, 0) + 1
    return {
        "cluster_id": cluster_id,
        "brands": sorted(brand_counts.items(), key=lambda item: item[1], reverse=True)[:5],
        "formats": sorted(format_counts.items(), key=lambda item: item[1], reverse=True)[:5],
        "ctas": sorted(cta_counts.items(), key=lambda item: item[1], reverse=True)[:5],
        "insight_components": _decode_json_field(insight.explanation_json, {}).get("components", {}) if insight else {},
    }


@router.post("/clusters/{cluster_id}/feedback")
def submit_cluster_feedback(cluster_id: int, body: InsightFeedbackRequest):
    _ensure_cluster_snapshot()
    with session_scope() as session:
        cluster = session.query(TrendCluster).filter(TrendCluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster not found")
        insight = session.query(TrendInsight).filter(TrendInsight.cluster_id == cluster_id).first()
        session.add(InsightFeedback(
            cluster_id=cluster_id,
            insight_id=insight.id if insight else None,
            useful=1 if body.useful else 0,
            rating=body.rating,
            used_in_campaign=1 if body.used_in_campaign else 0,
            outcome=body.outcome,
            notes=body.notes,
        ))
    return {"message": "Feedback recorded"}


@router.get("/reports/generated")
def get_generated_reports(force_refresh: bool = Query(False)):
    _ensure_cluster_snapshot(force=force_refresh)
    with session_scope() as session:
        rows = session.query(ReportBrief).order_by(ReportBrief.created_at.desc()).limit(20).all()
    return {
        "data": [
            {
                "id": row.id,
                "report_type": row.report_type,
                "title": row.title,
                "cluster_id": row.cluster_id,
                "content": _decode_json_field(row.content_json, {}),
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


@router.post("/reports/generate")
def generate_reports():
    result = _ensure_cluster_snapshot(force=True)
    return {"message": "Reports generated", **result}


@router.get("/backtests")
def get_backtests(force_refresh: bool = Query(False)):
    if force_refresh:
        _ensure_cluster_snapshot(force=True)
    with session_scope() as session:
        rows = session.query(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(20).all()
    return {
        "data": [
            {
                "id": row.id,
                "run_label": row.run_label,
                "window_start": row.window_start,
                "window_end": row.window_end,
                "total_clusters": row.total_clusters,
                "matched_clusters": row.matched_clusters,
                "avg_opportunity_score": row.avg_opportunity_score,
                "precision_proxy": row.precision_proxy,
                "recall_proxy": row.recall_proxy,
                "summary": _decode_json_field(row.summary_json, {}),
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


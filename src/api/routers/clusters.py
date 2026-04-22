from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query, HTTPException, BackgroundTasks, Depends
from sqlalchemy import func

from src.db.connection import session_scope
from src.db.models import TrendCluster, TrendInsight, InsightFeedback, User
from src.api.instances import pipeline, niche_discovery
from src.api.utils import sanitize_dataframe, decode_json_field, ensure_cluster_snapshot
from src.api.deps import get_current_user

router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.post("/refresh")
def refresh_clusters(background_tasks: BackgroundTasks, user: User = Depends(get_current_user)):
    """Trigger a cluster sync in the background."""
    background_tasks.add_task(ensure_cluster_snapshot, pipeline, True)
    return {"message": "Cluster refresh started in background"}


@router.get("")
def get_clusters(
    stage: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    niche_name: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    limit: int = Query(100),
    force_refresh: bool = Query(False),
):
    """Return a list of trend clusters with insights."""
    ensure_cluster_snapshot(pipeline, force=force_refresh)
    
    with session_scope() as session:
        q = session.query(TrendCluster, TrendInsight).outerjoin(TrendInsight, TrendInsight.cluster_id == TrendCluster.id)
        if stage:
            q = q.filter(TrendCluster.lifecycle_stage == stage)
        if platform:
            q = q.filter(TrendCluster.platforms.contains(platform))
        if date:
            parsed = pd.to_datetime(date, errors="coerce")
            if pd.notna(parsed):
                q = q.filter(TrendCluster.last_seen >= parsed.to_pydatetime())
        
        # Buffer the results for niche filtering
        rows = q.order_by(TrendCluster.last_seen.desc()).limit(limit * 2 if niche_name else limit).all()

    data = []
    for cluster, insight in rows:
        cluster_keywords = decode_json_field(cluster.cluster_keywords, [])
        data.append({
            "id": cluster.id,
            "cluster_key": cluster.cluster_key,
            "title": cluster.title,
            "topic": cluster.title,  # Alias for niche filtering
            "keyword": ", ".join(cluster_keywords[:5]) if cluster_keywords else cluster.title, # Alias for niche filtering
            "keywords": cluster_keywords,
            "platforms": decode_json_field(cluster.platforms, []),
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

    if not data:
        return {"data": []}

    df = pd.DataFrame(data)
    if niche_name and niche_name != "All":
        df = niche_discovery.filter_by_niche(df, niche_name)

    df = df.head(limit)
    return {"data": sanitize_dataframe(df) if not df.empty else []}


@router.get("/{cluster_id}")
def get_cluster_detail(cluster_id: int, force_refresh: bool = Query(False)):
    """Return full detail for a single cluster, including its AI insight."""
    ensure_cluster_snapshot(pipeline, force=force_refresh)
    
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
    
    return {
        "id": cluster.id,
        "cluster_key": cluster.cluster_key,
        "title": cluster.title,
        "keywords": decode_json_field(cluster.cluster_keywords, []),
        "platforms": decode_json_field(cluster.platforms, []),
        "lifecycle_stage": cluster.lifecycle_stage,
        "confidence_score": cluster.confidence_score,
        "freshness_score": cluster.freshness_score,
        "source_confidence": cluster.source_confidence,
        "trend_strength": cluster.trend_strength,
        "quality_score": cluster.quality_score,
        "explanation": decode_json_field(cluster.explanation_json, {}),
        "insight": None if not insight else {
            "ad_opportunity_score": insight.ad_opportunity_score,
            "audience_intent": insight.audience_intent,
            "creative_angle_candidates": decode_json_field(insight.creative_angle_candidates, []),
            "platform_fit": decode_json_field(insight.platform_fit, []),
            "ad_timing_window": insight.ad_timing_window,
            "saturation_risk": insight.saturation_risk,
            "brand_safety_risk": insight.brand_safety_risk,
            "explanation": decode_json_field(insight.explanation_json, {}),
        }
    }


@router.get("/{cluster_id}/signals")
def get_cluster_signals(cluster_id: int):
    """Return the raw platform signals that make up this cluster."""
    with session_scope() as session:
        # Implementation depends on TrendSignal model
        from src.db.models import TrendSignal
        signals = session.query(TrendSignal).filter(TrendSignal.cluster_id == cluster_id).all()
        # simplified return for now
        return {"data": [{"platform": s.platform, "topic": s.topic, "virality_score": s.virality_score} for s in signals]}


@router.post("/{cluster_id}/feedback")
def submit_cluster_feedback(cluster_id: int, useful: bool, user: User = Depends(get_current_user)):
    """Record user feedback for a cluster insight."""
    with session_scope() as session:
        fb = InsightFeedback(cluster_id=cluster_id, user_id=user.id, useful=useful)
        session.add(fb)
    return {"message": "Feedback recorded"}

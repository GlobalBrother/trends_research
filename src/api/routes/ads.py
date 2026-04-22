"""Ads endpoints (`/ads_insight`, `/search_brands`)."""

from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from src.api.dependencies import (
    HAS_GETHOOKEDAI,
    _get_niche_keywords_from_db,
    _sanitize,
    gethookd_search_brands,
    logger,
    session_scope,
)
from src.api.schemas import AdsInsightResponse, BrandSearchResponse
from src.db.models import AdsInsight

router = APIRouter(tags=["ads"])


@router.get("/ads_insight", response_model=AdsInsightResponse)
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


@router.get("/search_brands", response_model=BrandSearchResponse)
def search_brands_endpoint(query: str = Query(..., description="Brand name to search")):
    if not HAS_GETHOOKEDAI:
        raise HTTPException(status_code=501, detail="GetHookdAI scraper not available")
    try:
        brands = gethookd_search_brands(query)
        return {"data": brands}
    except Exception as e:
        logger.error(f"Brand search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


"""Ads endpoints (`/ads_insight`, `/search_brands`)."""

from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func

from src.api.dependencies import (
    HAS_GETHOOKEDAI,
    _get_niche_keywords_from_db,
    _sanitize,
    gethookd_search_brands,
    logger,
    session_scope,
)
from src.api.schemas import (
    AdsInsightFiltersResponse,
    AdsInsightResponse,
    BrandSearchResponse,
)
from src.db.models import AdsInsight

router = APIRouter(tags=["ads"])


@router.get("/ads_insight", response_model=AdsInsightResponse)
def get_ads_insight(
    niche_name: Optional[str] = Query(None),
    geo: Optional[str] = Query(None),
    limit: int = Query(500),
    offset: int = Query(0),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    platform_filter: Optional[str] = Query(None),
    format_filter: Optional[str] = Query(None),
    keyword_filter: Optional[str] = Query(None),
    brand_filter: Optional[str] = Query(None),
    perf_filter: Optional[str] = Query(None),
    sort_by: str = Query("extracted_at"),
    sort_dir: str = Query("desc"),
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
        q = session.query(AdsInsight)

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

        total_count = q.count()

        sort_col = _SORTABLE.get(sort_by, AdsInsight.extracted_at)
        if sort_dir.lower() == "asc":
            q = q.order_by(sort_col.asc())
        else:
            q = q.order_by(sort_col.desc())

        if offset > 0:
            q = q.offset(offset)
        if limit > 0:
            q = q.limit(limit)

        rows = q.all()

    if not rows:
        return {"data": [], "total": total_count}

    data = [
        {c.name: getattr(r, c.name) for c in AdsInsight.__table__.columns}
        for r in rows
    ]
    df = pd.DataFrame(data)
    sanitized = _sanitize(df)

    # Coerce types so the strict Pydantic ``AdsInsightResponse`` accepts the
    # row dicts: ``hookd_id`` is a DB int but the frontend/schema treat it as
    # a string, and several legacy "Integer" columns hold empty strings that
    # Pydantic cannot parse — convert those to ``None``.
    _INT_FIELDS = (
        "days_active", "active_in_library", "performance_score", "used_count",
        "age_audience_min", "age_audience_max", "eu_total_reach",
        "brand_active_ads", "ad_spend_range_score", "is_aaa_eligible",
    )
    for row in sanitized:
        if row.get("hookd_id") is not None and not isinstance(row["hookd_id"], str):
            row["hookd_id"] = str(row["hookd_id"])
        for f in _INT_FIELDS:
            if row.get(f) == "":
                row[f] = None

    return {"data": sanitized, "total": total_count}


@router.get("/ads_insight/filters", response_model=AdsInsightFiltersResponse)
def get_ads_insight_filters():
    """Return distinct filter values for the ads_insight table.

    Response shape mirrors the frontend ``AdsInsightFilters`` interface in
    ``frontend/src/lib/api.ts`` 1:1.
    """
    with session_scope() as session:
        # platforms: stored as a comma-separated string (e.g. "Facebook, Instagram")
        platform_rows = session.query(AdsInsight.platform).distinct().all()
        platforms: set[str] = set()
        for (p,) in platform_rows:
            if not p:
                continue
            for part in p.split(", "):
                part = part.strip()
                if part:
                    platforms.add(part)

        format_rows = session.query(AdsInsight.display_format).distinct().all()
        formats = sorted({r[0] for r in format_rows if r[0]})

        keyword_rows = session.query(AdsInsight.search_keyword).distinct().all()
        keywords = sorted({r[0] for r in keyword_rows if r[0]})

        perf_rows = session.query(AdsInsight.performance_score_title).distinct().all()
        performance_tiers = sorted({r[0] for r in perf_rows if r[0]})

        brand_rows = session.query(AdsInsight.brand_name).distinct().all()
        brands = sorted({r[0] for r in brand_rows if r[0]})

        min_date, max_date = session.query(
            func.min(AdsInsight.start_date),
            func.max(AdsInsight.start_date),
        ).one()

    def _iso(value) -> Optional[str]:
        if value in (None, ""):
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    return {
        "platforms": sorted(platforms),
        "formats": formats,
        "keywords": keywords,
        "performance_tiers": performance_tiers,
        "brands": brands,
        "date_range": {"min": _iso(min_date), "max": _iso(max_date)},
    }


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


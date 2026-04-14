import logging
from typing import Optional, List

import pandas as pd
from fastapi import APIRouter, Query, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel

from src.db.connection import session_scope
from src.db.models import MyBrand, AdsInsight, User
from src.api.instances import (
    HAS_GETHOOKEDAI, gethookd_search_brands, gethookd_scrape_brand_ads, gethookd_scrape_ads
)
from src.api.utils import sanitize_dataframe
from src.api.deps import get_current_user

router = APIRouter(tags=["my_brands"])
logger = logging.getLogger(__name__)


class MyBrandRequest(BaseModel):
    brand_name: str
    brand_external_id: Optional[str] = None
    brand_logo_url: Optional[str] = None
    brand_active_ads: int = 0


@router.get("/search_brands")
def search_brands_endpoint(query: str = Query(..., description="Brand name to search")):
    if not HAS_GETHOOKEDAI:
        raise HTTPException(status_code=501, detail="GetHookdAI scraper not available")
    try:
        brands = gethookd_search_brands(query)
        return {"data": brands}
    except Exception as e:
        logger.error(f"Brand search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrape_brand_ads")
def scrape_brand_ads_endpoint(
    background_tasks: BackgroundTasks,
    brand_id: int = Query(...),
    user: User = Depends(get_current_user)
):
    if not HAS_GETHOOKEDAI:
        raise HTTPException(status_code=501, detail="GetHookdAI scraper not available")
    
    # Import locally to avoid circular dependency
    from src.api.routers.trends import _trigger_background_scrape
    _trigger_background_scrape(f"brand_ads_{brand_id}", lambda: gethookd_scrape_brand_ads(brand_id=brand_id))
    
    return {"message": f"Brand spy started for brand {brand_id}"}


@router.get("/my_brands")
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


@router.post("/my_brands")
def add_my_brand(body: MyBrandRequest, background_tasks: BackgroundTasks, user: User = Depends(get_current_user)):
    """Add a brand to track and optionally trigger a brand spy scrape."""
    with session_scope() as session:
        existing = session.query(MyBrand).filter(MyBrand.brand_name == body.brand_name).first()
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

    if body.brand_external_id and HAS_GETHOOKEDAI:
        from src.api.routers.trends import _trigger_background_scrape
        _trigger_background_scrape(f"ads_spy_{body.brand_name}", lambda: gethookd_scrape_ads([body.brand_name], max_pages=5))

    return {"message": f"Brand '{body.brand_name}' added to tracking", "id": brand_id}


@router.delete("/my_brands/{brand_id}")
def remove_my_brand(brand_id: int, user: User = Depends(get_current_user)):
    """Remove a tracked brand."""
    with session_scope() as session:
        brand = session.query(MyBrand).filter(MyBrand.id == brand_id).first()
        if not brand:
            raise HTTPException(status_code=404, detail="Brand not found")
        session.delete(brand)
    return {"ok": True}


@router.get("/my_brands/ads")
def get_my_brand_ads(
    limit: int = Query(500),
    offset: int = Query(0),
    brand_name: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    platform_filter: Optional[str] = Query(None),
    sort_by: str = Query("start_date"),
    sort_dir: str = Query("desc"),
):
    """Retrieve ads for tracked brands."""
    _SORTABLE = {
        "start_date": AdsInsight.start_date,
        "end_date": AdsInsight.end_date,
        "days_active": AdsInsight.days_active,
        "performance_score": AdsInsight.performance_score,
        "brand_name": AdsInsight.brand_name,
    }
    
    with session_scope() as session:
        # Get all tracked brand names if none specified
        if not brand_name:
            brand_names = [r.brand_name for r in session.query(MyBrand.brand_name).all()]
        else:
            brand_names = [brand_name]
        
        if not brand_names:
            return {"data": [], "total": 0}

        q = session.query(AdsInsight).filter(AdsInsight.brand_name.in_(brand_names))
        
        if date_from:
            q = q.filter(AdsInsight.start_date >= date_from)
        if date_to:
            q = q.filter(AdsInsight.start_date <= date_to)
        if platform_filter:
            q = q.filter(AdsInsight.platform.contains(platform_filter))

        total_count = q.count()

        sort_col = _SORTABLE.get(sort_by, AdsInsight.start_date)
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

    data = [{c.name: getattr(r, c.name) for c in AdsInsight.__table__.columns} for r in rows]
    df = pd.DataFrame(data)
    return {"data": sanitize_dataframe(df), "total": total_count}

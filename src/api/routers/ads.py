import logging
import os
from typing import Optional, List

import pandas as pd
from fastapi import APIRouter, Query, HTTPException, Depends, BackgroundTasks
from sqlalchemy import func

from src.db.connection import session_scope
from src.db.models import AdsInsight, Content, Author, ContentMetric, Platform, User
from src.api.instances import (
    niche_discovery, HAS_GETHOOKEDAI, gethookd_scrape_ads, 
    gethookd_scrape_brand_ads, gethookd_search_brands
)
from src.api.utils import sanitize_dataframe
from src.api.deps import get_current_user

router = APIRouter(tags=["ads"])
logger = logging.getLogger(__name__)


def _content_query(platform_name: str, niche_name: Optional[str], geo: Optional[str], limit: int, order_attr=None):
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
            kws = niche_discovery.get_niche_keywords(niche_name)
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
    return sanitize_dataframe(df)


@router.get("/ads_insight")
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
            kws = niche_discovery.get_niche_keywords(niche_name)
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
    
    # Manually extract columns to avoid issues with InstrumentedAttribute if any
    data = []
    for r in rows:
        data.append({c.name: getattr(r, c.name) for c in AdsInsight.__table__.columns})
    
    df = pd.DataFrame(data)
    return {"data": sanitize_dataframe(df), "total": total_count}


@router.get("/ads_insight/filters")
def get_ads_insight_filters():
    """Return distinct filter values for the ads_insight table."""
    result = {}
    with session_scope() as session:
        rows = session.query(AdsInsight.platform).distinct().all()
        platforms = set()
        for (p,) in rows:
            if p:
                for part in p.split(", "):
                    platforms.add(part.strip())
        result["platforms"] = sorted(platforms)

        rows = session.query(AdsInsight.display_format).distinct().all()
        result["formats"] = sorted([r[0] for r in rows if r[0]])

        rows = session.query(AdsInsight.performance_score_title).distinct().all()
        result["performance_scores"] = sorted([r[0] for r in rows if r[0]])

    return result


@router.post("/scrape_ads")
def trigger_ads_scrape(
    keyword: str = Query(...), 
    geo: str = Query("US"), 
    user: User = Depends(get_current_user)
):
    """Trigger an ads scrape via GetHookedAI."""
    if not HAS_GETHOOKEDAI:
        raise HTTPException(status_code=501, detail="GetHookedAI integration not available")
    
    # Import locally to avoid issues if not present
    from src.api.routers.trends import _trigger_background_scrape
    _trigger_background_scrape(f"ads_{keyword}_{geo}", lambda: gethookd_scrape_ads(keyword, geo=geo))
    
    return {"message": f"Ads scrape triggered for {keyword} ({geo})"}


@router.get("/tiktok_videos")
def get_tiktok_videos(niche_name: Optional[str] = Query(None), geo: Optional[str] = Query(None), limit: int = Query(500)):
    data = _content_query("TikTok", niche_name, geo, limit, order_attr=ContentMetric.views.desc())
    rename_map = {
        "text_content": "description", "username": "author_unique_id",
        "views": "play_count", "likes": "digg_count", "comments": "comment_count",
        "shares": "share_count", "saves": "collect_count", "url": "share_url",
    }
    for row in data:
        for old_key, new_key in rename_map.items():
            if old_key in row: row[new_key] = row.pop(old_key)
        row["engagement_total"] = sum(row.get(k) or 0 for k in ["digg_count", "comment_count", "share_count", "collect_count"])
    return {"data": data}


@router.get("/youtube_videos")
def get_youtube_videos(niche_name: Optional[str] = Query(None), geo: Optional[str] = Query(None), limit: int = Query(500)):
    data = _content_query("YouTube", niche_name, geo, limit, order_attr=ContentMetric.views.desc())
    rename_map = {"text_content": "title", "username": "channel_title", "views": "view_count", "likes": "like_count", "comments": "comment_count"}
    for row in data:
        for old_key, new_key in rename_map.items():
            if old_key in row: row[new_key] = row.pop(old_key)
        row["engagement_total"] = sum(row.get(k) or 0 for k in ["view_count", "like_count", "comment_count"])
    return {"data": data}


@router.get("/instagram_posts")
def get_instagram_posts(niche_name: Optional[str] = Query(None), geo: Optional[str] = Query(None), limit: int = Query(500)):
    data = _content_query("Instagram", niche_name, geo, limit, order_attr=ContentMetric.likes.desc())
    rename_map = {"text_content": "caption", "likes": "like_count", "comments": "comment_count", "shares": "share_count", "saves": "save_count"}
    for row in data:
        for old_key, new_key in rename_map.items():
            if old_key in row: row[new_key] = row.pop(old_key)
        row["engagement_total"] = sum(row.get(k) or 0 for k in ["like_count", "comment_count", "share_count", "save_count"])
    return {"data": data}


@router.get("/reddit_posts")
def get_reddit_posts(niche_name: Optional[str] = Query(None), geo: Optional[str] = Query(None), limit: int = Query(500)):
    data = _content_query("Reddit", niche_name, geo, limit, order_attr=ContentMetric.likes.desc())
    rename_map = {"text_content": "title", "likes": "score", "comments": "num_comments", "username": "author", "keyword": "subreddit"}
    for row in data:
        for old_key, new_key in rename_map.items():
            if old_key in row: row[new_key] = row.pop(old_key)
        row["engagement_total"] = (row.get("score") or 0) + (row.get("num_comments") or 0)
    return {"data": data}

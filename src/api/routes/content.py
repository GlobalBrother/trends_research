"""Per-platform content endpoints (normalized content table)."""

from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query
from sqlalchemy import func

from src.api.dependencies import (
    _get_niche_keywords_from_db,
    _sanitize,
    session_scope,
)
from sqlalchemy import or_

from src.api.schemas import (
    InstagramPostsResponse,
    RedditPostsResponse,
    ThreadsPostsResponse,
    TiktokVideosResponse,
    YoutubeVideosResponse,
)
from src.db.models import (
    Author,
    Content,
    ContentHashtag,
    ContentMetric,
    Hashtag,
    Platform,
)

router = APIRouter(tags=["content"])


# ---------------------------------------------------------------------------
# Normalized content query helper — used only by this router
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
                # The `keyword` column is reliable for keyword-driven scrapers
                # (YouTube, TikTok, sometimes Instagram) but is the subreddit
                # name for Reddit (e.g. "r/all") and not always set for
                # Threads/Instagram. Match on keyword OR title/text substring
                # OR hashtag so each tab actually shows niche-relevant content.
                lowered = [k.lower() for k in kws if k]
                text_clauses = [
                    func.lower(Content.text_content).like(f"%{k}%") for k in lowered
                ]
                hashtag_match = (
                    session.query(ContentHashtag.content_id)
                    .join(Hashtag, Hashtag.id == ContentHashtag.hashtag_id)
                    .filter(func.lower(Hashtag.tag).in_(lowered))
                )
                query = query.filter(
                    or_(
                        Content.keyword.in_(kws),
                        Content.id.in_(hashtag_match),
                        *text_clauses,
                    )
                )

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
# YouTube videos
# ---------------------------------------------------------------------------

@router.get("/youtube_videos", response_model=YoutubeVideosResponse)
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
# TikTok videos
# ---------------------------------------------------------------------------

@router.get("/tiktok_videos", response_model=TiktokVideosResponse)
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
# Instagram posts
# ---------------------------------------------------------------------------

@router.get("/instagram_posts", response_model=InstagramPostsResponse)
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
# Reddit posts
# ---------------------------------------------------------------------------

@router.get("/reddit_posts", response_model=RedditPostsResponse)
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
# Threads posts
# ---------------------------------------------------------------------------

@router.get("/threads_posts", response_model=ThreadsPostsResponse)
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


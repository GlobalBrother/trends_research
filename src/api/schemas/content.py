"""Per-platform content row models.

Each handler in ``src/api/routes/content.py`` renames generic columns
(``text_content``/``views``/``likes``/…) to platform-specific names. The
models below reflect the **post-rename** shape so OpenAPI is accurate.

All inherit from :class:`OpenModel` (``extra="allow"``) so that any extra
columns produced by ``_sanitize(df)`` are preserved on the wire.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from .common import OpenModel


class _ContentBase(OpenModel):
    """Fields common to every per-platform content row."""

    external_id: Optional[str] = None
    keyword: Optional[str] = None
    geo: Optional[str] = None
    media_type: Optional[str] = None
    url: Optional[str] = None
    created_at: Optional[str] = None
    full_name: Optional[str] = None
    follower_count: Optional[int] = None
    is_verified: Optional[bool] = None
    profile_pic_url: Optional[str] = None
    platform: Optional[str] = None


class YoutubeVideoRow(_ContentBase):
    title: Optional[str] = None
    channel_title: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    engagement_total: Optional[float] = None
    published: Optional[str] = None


class YoutubeVideosResponse(BaseModel):
    data: list[YoutubeVideoRow]


class TiktokVideoRow(_ContentBase):
    description: Optional[str] = None
    author_unique_id: Optional[str] = None
    play_count: Optional[int] = None
    digg_count: Optional[int] = None
    comment_count: Optional[int] = None
    share_count: Optional[int] = None
    collect_count: Optional[int] = None
    share_url: Optional[str] = None
    engagement_total: Optional[float] = None
    created: Optional[str] = None


class TiktokVideosResponse(BaseModel):
    data: list[TiktokVideoRow]


class InstagramPostRow(_ContentBase):
    caption: Optional[str] = None
    username: Optional[str] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    share_count: Optional[int] = None
    save_count: Optional[int] = None
    engagement_total: Optional[float] = None
    posted: Optional[str] = None


class InstagramPostsResponse(BaseModel):
    data: list[InstagramPostRow]


class RedditPostRow(_ContentBase):
    # `keyword` from base is renamed to `subreddit` for Reddit responses
    keyword: Optional[str] = None  # may still appear if rename was a no-op
    subreddit: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    score: Optional[int] = None
    num_comments: Optional[int] = None
    engagement_total: Optional[float] = None
    posted: Optional[str] = None


class RedditPostsResponse(BaseModel):
    data: list[RedditPostRow]


class ThreadsPostRow(_ContentBase):
    caption: Optional[str] = None
    username: Optional[str] = None
    like_count: Optional[int] = None
    reply_count: Optional[int] = None
    repost_count: Optional[int] = None
    quote_count: Optional[int] = None
    engagement_total: Optional[float] = None
    posted: Optional[str] = None


class ThreadsPostsResponse(BaseModel):
    data: list[ThreadsPostRow]


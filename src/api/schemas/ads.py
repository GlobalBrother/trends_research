"""Ads endpoint response models."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from .common import OpenModel


class AdsInsightRow(OpenModel):
    """Mirrors ``AdsInsightRow`` in ``frontend/src/lib/api.ts`` 1:1."""

    hookd_id: Optional[str] = None
    external_id: Optional[str] = None
    search_keyword: Optional[str] = None
    platform: Optional[str] = None
    display_format: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    landing_page: Optional[str] = None
    cta_type: Optional[str] = None
    cta_text: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    days_active: Optional[int] = None
    active_in_library: Optional[int] = None
    performance_score: Optional[float] = None
    performance_score_title: Optional[str] = None
    used_count: Optional[int] = None
    age_audience_min: Optional[int] = None
    age_audience_max: Optional[int] = None
    gender_audience: Optional[str] = None
    eu_total_reach: Optional[int] = None
    brand_name: Optional[str] = None
    brand_logo_url: Optional[str] = None
    brand_active_ads: Optional[int] = None
    media: Optional[str] = None
    share_url: Optional[str] = None
    extracted_at: Optional[str] = None


class AdsInsightResponse(BaseModel):
    data: list[AdsInsightRow]
    total: int = 0


class BrandSearchResponse(BaseModel):
    """``/search_brands`` returns whatever shape the third-party API exposes;
    we keep it open so we don't drop fields the frontend may consume.
    """

    data: list[Any]


class AdsInsightDateRange(BaseModel):
    min: Optional[str] = None
    max: Optional[str] = None


class AdsInsightFiltersResponse(BaseModel):
    """Mirrors ``AdsInsightFilters`` in ``frontend/src/lib/api.ts`` 1:1."""

    platforms: list[str]
    formats: list[str]
    keywords: list[str]
    performance_tiers: list[str]
    brands: list[str]
    date_range: AdsInsightDateRange



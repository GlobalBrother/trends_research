"""Trend row model used by all ``/*_trends`` endpoints."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from .common import OpenModel


class TrendRow(OpenModel):
    """Mirrors ``frontend/src/lib/api.ts`` ``TrendRow`` (all-optional, open).

    NOTE / contract mismatch (flagged for the report):

    The frontend declares ``platform``, ``geo``, ``topic``, ``title``, and
    ``keyword`` as ``string?``. The backend's ``AnalyticsEngine.process_trends``
    aggregates rows and emits these fields as **lists of strings** in some
    cases (e.g. an aggregated row may have ``platform=['YouTube','Reddit',…]``).
    To preserve current backend output without silently rewriting either
    side, those fields are typed as ``Any`` here. Either the backend should
    flatten them or the frontend interface should widen them — see the
    "Mismatches" section of the implementation report.
    """

    title: Optional[Any] = None
    keyword: Optional[Any] = None
    platform: Optional[Any] = None
    search_volume: Optional[float] = None
    virality_score: Optional[float] = None
    sentiment_score: Optional[float] = None
    topic: Optional[Any] = None
    niche_cluster: Optional[int] = None
    geo: Optional[Any] = None
    extracted_at: Optional[str] = None


class TrendsResponse(BaseModel):
    data: list[TrendRow]


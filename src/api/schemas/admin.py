"""Admin endpoint response models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict

from .common import OpenModel


class TokenUsageRow(BaseModel):
    """Mirrors ``TokenUsageRow`` in ``frontend/src/lib/api.ts``."""

    model_config = ConfigDict(extra="allow")
    platform: str
    keyword: Optional[str] = None
    units_charged: float
    geo: Optional[str] = None
    created_at: Optional[datetime] = None
    provider: Optional[str] = None


class TokenUsageSummary(BaseModel):
    """Mirrors ``TokenUsageSummary`` in the frontend."""

    model_config = ConfigDict(extra="allow")
    platform: Optional[str] = None
    total_units: float
    request_count: int
    provider: Optional[str] = None


class TokenUsageResponse(BaseModel):
    data: list[TokenUsageRow]
    summary: list[TokenUsageSummary]
    provider_summary: list[TokenUsageSummary]


class AzureStatusResponse(BaseModel):
    """Mirrors ``AzureStatus`` in the frontend."""

    model_config = ConfigDict(extra="allow")
    connected: bool
    tables: Optional[dict[str, Union[int, str]]] = None
    error: Optional[str] = None
    diagnostic: Optional[dict[str, Any]] = None


class AzureDiagnoseResponse(OpenModel):
    """Free-form diagnostic dict — kept open."""

    connected: Optional[bool] = None
    error: Optional[str] = None
    strategy: Optional[str] = None


class MigrationResponse(OpenModel):
    """Either ``{mode: "dry_run", ...}`` or ``{message: "..."}``."""

    mode: Optional[str] = None
    message: Optional[str] = None


class TableFiltersResponse(BaseModel):
    geos: list[str]
    keywords: list[str]


class ResetDefaultsResponse(OpenModel):
    """Includes a ``message`` plus arbitrary stats from ``reset_niches_to_defaults``."""

    message: str


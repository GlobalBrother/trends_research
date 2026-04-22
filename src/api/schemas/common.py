"""Shared base + small generic response models."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OpenModel(BaseModel):
    """Base for row models that may carry extra DataFrame columns.

    ``extra="allow"`` is critical: ``_sanitize`` flattens whatever DataFrame
    columns exist (analytics-derived, ORM extras, …) and the frontend
    consumes them via ``[key: string]: unknown``. We must not drop them.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class MessageResponse(BaseModel):
    """Generic ``{"message": "..."}`` envelope."""

    model_config = ConfigDict(extra="allow")
    message: str


class OkResponse(BaseModel):
    """``{"ok": true}`` envelope used by delete endpoints."""

    ok: bool


class RootResponse(BaseModel):
    message: str


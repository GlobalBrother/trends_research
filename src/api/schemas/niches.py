"""Niche endpoint response models."""
from __future__ import annotations

from pydantic import BaseModel


class NicheKeywordsResponse(BaseModel):
    niche: str
    keywords: list[str]


class NicheMutationResponse(BaseModel):
    """Envelope returned by every niche create/update/delete endpoint."""

    message: str


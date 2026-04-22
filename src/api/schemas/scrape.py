"""Scrape endpoint response models."""
from __future__ import annotations

from typing import Optional, Union

from pydantic import BaseModel

from .common import OpenModel


class ScrapeErrorRow(OpenModel):
    """A single row from ``GET /scrape_errors`` (sourced from ScrapeError ORM).

    NOTE / contract mismatch: ``status`` is an HTTP status code stored as
    ``int`` in the ORM (e.g. 400, 401, 429). The frontend has no typed
    interface for these rows yet (uses ``unknown[]``), so this is
    backend-only — the field is typed as ``int | str`` to match what the
    DB actually emits.
    """

    platform: Optional[str] = None
    keyword: Optional[str] = None
    url: Optional[str] = None
    status: Optional[Union[int, str]] = None
    reason: Optional[str] = None
    extracted_at: Optional[str] = None


class ScrapeErrorsResponse(BaseModel):
    data: list[ScrapeErrorRow]


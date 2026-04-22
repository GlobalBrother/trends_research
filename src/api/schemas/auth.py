"""Auth endpoint response models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class OtpRequestResponse(BaseModel):
    message: str
    email: str


class OtpVerifyResponse(BaseModel):
    message: str
    email: str
    role: str
    token: str


class TokenValidationResponse(BaseModel):
    email: str
    role: str


class UserRow(BaseModel):
    """Single row from ``GET /auth/users`` (raw list, no envelope)."""

    model_config = ConfigDict(extra="allow")
    email: str
    role: str
    created_at: Optional[datetime] = None


class UserMutationResponse(BaseModel):
    """Envelope for ``POST/PUT/DELETE /auth/users``."""

    model_config = ConfigDict(extra="allow")
    message: str
    email: Optional[str] = None
    role: Optional[str] = None


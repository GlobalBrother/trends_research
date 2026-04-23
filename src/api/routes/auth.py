"""Auth endpoints (`/auth/*`)."""

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from src.api.dependencies import (
    TEST_ACCOUNT_EMAIL,
    TEST_ACCOUNT_OTP,
    logger,
    session_scope,
)
from src.api.schemas import (
    OtpRequestResponse,
    OtpVerifyResponse,
    TokenValidationResponse,
    UserMutationResponse,
    UserRow,
)
from src.api.utils import send_email
from src.db.models import AuthToken, OtpCode, User
from src.db.sql_compat import verify_otp

router = APIRouter(tags=["auth"])


class UserCreate(BaseModel):
    email: str
    role: str = "trends"  # "admin" or "trends"


@router.post("/auth/request_otp", response_model=OtpRequestResponse)
def request_otp(email: str = Query(...)):
    """Send an OTP code to a whitelisted email via Azure Communication Services."""
    # Test account bypass: auto-create user and skip email
    if TEST_ACCOUNT_EMAIL and email == TEST_ACCOUNT_EMAIL:
        with session_scope() as session:
            user = session.query(User).filter(User.email == email).first()
            if not user:
                user = User(email=email, role="admin")
                session.add(user)
                session.flush()
            session.add(OtpCode(user_id=user.id, code=TEST_ACCOUNT_OTP))
        return {"message": "OTP sent", "email": email}

    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=403, detail="Email not whitelisted")

        user_id = user.id
        code = secrets.token_hex(3).upper()  # 6-char hex code
        session.add(OtpCode(user_id=user_id, code=code))

    try:
        send_email(
            to_email=email,
            subject="Your Trends Research login code",
            html_body=(
                f"<p>Your one-time login code is: <strong>{code}</strong></p>"
                f"<p>This code expires in 10 minutes.</p>"
            ),
        )
    except Exception as e:
        logger.error(f"Failed to send OTP email to {email}: {e}")
        # Surface the underlying provider error so misconfiguration is
        # diagnosable from the frontend / network tab instead of a bare 500.
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send OTP email: {e}",
        )

    return {"message": "OTP sent", "email": email}


@router.post("/auth/verify_otp", response_model=OtpVerifyResponse)
def verify_otp_endpoint(email: str = Query(...), code: str = Query(...)):
    """Verify an OTP code and return the user's role."""
    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired OTP")
        user_id = user.id
        user_role = user.role

        # Test account bypass: accept the fixed OTP without DB lookup
        if TEST_ACCOUNT_EMAIL and email == TEST_ACCOUNT_EMAIL and code == TEST_ACCOUNT_OTP:
            token = secrets.token_hex(32)
            expires_at = datetime.utcnow() + timedelta(hours=12)
            session.add(AuthToken(token=token, user_id=user_id, expires_at=expires_at))
            return {"message": "Authenticated", "email": email, "role": user_role, "token": token}

        otp = verify_otp(session, user_id, code.upper())
        if not otp:
            raise HTTPException(status_code=401, detail="Invalid or expired OTP")

        otp.used = 1

        # Generate auth token valid for 12 hours
        token = secrets.token_hex(32)
        expires_at = datetime.utcnow() + timedelta(hours=12)
        session.add(AuthToken(token=token, user_id=user_id, expires_at=expires_at))

    return {"message": "Authenticated", "email": email, "role": user_role, "token": token}


@router.get("/auth/validate_token", response_model=TokenValidationResponse)
def validate_token(token: str = Query(...)):
    """Validate an auth token and return user info if still valid."""
    with session_scope() as session:
        row = session.query(User.email, User.role).join(
            AuthToken, AuthToken.user_id == User.id
        ).filter(
            AuthToken.token == token,
            AuthToken.expires_at > datetime.utcnow(),
        ).first()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"email": row.email, "role": row.role}


@router.get("/auth/users", response_model=list[UserRow])
def list_users():
    """List all whitelisted users.

    Defensive normalisation: any legacy rows with NULL ``role`` or ``email``
    are coerced to safe defaults so a single bad row can't blow up the
    entire response with a Pydantic validation error.
    """
    with session_scope() as session:
        rows = session.query(User.email, User.role, User.created_at).order_by(User.created_at).all()
    return [
        {
            "email": r.email or "",
            "role": r.role or "trends",
            "created_at": r.created_at,
        }
        for r in rows
        if r.email  # skip rows with no email at all
    ]


@router.post("/auth/users", response_model=UserMutationResponse)
def add_user(user: UserCreate):
    """Add a whitelisted user."""
    if user.role not in ("admin", "trends"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'trends'")
    try:
        with session_scope() as session:
            session.add(User(email=user.email, role=user.role))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="User already exists")
    return {"message": "User added", "email": user.email, "role": user.role}


@router.put("/auth/users", response_model=UserMutationResponse)
def update_user_role(email: str = Query(...), role: str = Query(...)):
    """Update a user's role."""
    if role not in ("admin", "trends"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'trends'")
    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.role = role
    return {"message": "Role updated", "email": email, "role": role}


@router.delete("/auth/users", response_model=UserMutationResponse)
def delete_user(email: str = Query(...)):
    """Remove a whitelisted user."""
    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        session.delete(user)
    return {"message": "User removed", "email": email}


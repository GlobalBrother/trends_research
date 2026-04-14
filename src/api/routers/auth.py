import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from src.db.connection import session_scope
from src.db.models import User, OtpCode, AuthToken
from src.db.sql_compat import verify_otp
from src.api.utils import send_email
from src.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

TEST_ACCOUNT_EMAIL = os.getenv("TEST_ACCOUNT_EMAIL", "").strip()
TEST_ACCOUNT_OTP = os.getenv("TEST_ACCOUNT_OTP", "000000").strip()


class UserCreate(BaseModel):
    email: str
    role: str = "trends"  # "admin" or "trends"


@router.post("/request_otp")
def request_otp(email: str = Query(...)):
    """Send an OTP code to a whitelisted email."""
    # Test account bypass: auto-create user and skip email
    if TEST_ACCOUNT_EMAIL and email == TEST_ACCOUNT_EMAIL:
        with session_scope() as session:
            user = session.query(User).filter(User.email == email).first()
            if not user:
                user = User(email=email, role="admin")
                session.add(user)
                session.flush()
            existing_otp = session.query(OtpCode).filter(OtpCode.user_id == user.id, OtpCode.used == 0).first()
            if existing_otp:
                existing_otp.code = TEST_ACCOUNT_OTP
                existing_otp.created_at = datetime.utcnow()
            else:
                session.add(OtpCode(user_id=user.id, code=TEST_ACCOUNT_OTP))
        return {"message": "OTP sent", "email": email}

    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=403, detail="Email not whitelisted")

        user_id = user.id
        code = secrets.token_hex(3).upper()  # 6-char hex code
        existing_otp = session.query(OtpCode).filter(OtpCode.user_id == user_id, OtpCode.used == 0).first()
        if existing_otp:
            existing_otp.code = code
            existing_otp.created_at = datetime.utcnow()
        else:
            session.add(OtpCode(user_id=user_id, code=code))

    send_email(
        to_email=email,
        subject="Your Trends Research login code",
        html_body=f"<p>Your one-time login code is: <strong>{code}</strong></p>"
                  f"<p>This code expires in 10 minutes.</p>",
    )

    return {"message": "OTP sent", "email": email}


@router.post("/verify_otp")
def verify_otp_endpoint(email: str = Query(...), code: str = Query(...)):
    """Verify OTP and return a session token."""
    # Test account bypass
    if TEST_ACCOUNT_EMAIL and email == TEST_ACCOUNT_EMAIL and code == TEST_ACCOUNT_OTP:
        with session_scope() as session:
            user = session.query(User).filter(User.email == email).first()
            if not user:
                raise HTTPException(status_code=403, detail="Test user not found")
            
            token = secrets.token_urlsafe(32)
            session.add(AuthToken(
                user_id=user.id,
                token=token,
                expires_at=datetime.utcnow() + timedelta(days=30)
            ))
            return {
                "token": token,
                "email": user.email,
                "role": user.role,
                "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat()
            }

    with session_scope() as session:
        user_id = verify_otp(session, email, code)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired OTP")

        user = session.query(User).get(user_id)
        token = secrets.token_urlsafe(32)
        session.add(AuthToken(
            user_id=user_id,
            token=token,
            expires_at=datetime.utcnow() + timedelta(days=30)
        ))
        
        return {
            "token": token,
            "email": user.email,
            "role": user.role,
            "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat()
        }


@router.get("/validate_token")
def validate_token(user: User = Depends(get_current_user)):
    """Return 200 if token is valid, along with user info."""
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role
    }

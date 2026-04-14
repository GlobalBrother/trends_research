import logging
from datetime import datetime

from fastapi import Header, HTTPException
from src.db.connection import session_scope
from src.db.models import User, AuthToken

logger = logging.getLogger(__name__)


def get_current_user(authorization: str = Header(None)) -> User:
    """Validate the Bearer token and return the User object.
    Raises 401 if the token is missing, invalid, or expired."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    token = authorization.split(" ", 1)[1]
    with session_scope() as session:
        row = session.query(User.id, User.email, User.role).join(
            AuthToken, AuthToken.user_id == User.id
        ).filter(
            AuthToken.token == token,
            AuthToken.expires_at > datetime.utcnow(),
        ).first()
    
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return row


def require_admin(authorization: str = Header(None)) -> User:
    """Verify the request comes from an admin user.
    Raises 401 if unauthenticated, 403 if not admin."""
    user = get_current_user(authorization)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

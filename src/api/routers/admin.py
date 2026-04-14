import os
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.db.connection import session_scope, diagnose as run_connection_diagnose, get_last_diagnostic
from src.db.models import User, ScrapeRun, ScrapeError, TokenUsage
from src.db.setup_azure import setup_azure_schema as run_setup_azure_schema
from src.db.migrate import run_migration
from src.api.deps import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


class UserCreate(BaseModel):
    email: str
    role: str = "trends"  # "admin" or "trends"


@router.get("/users", response_model=List[dict])
def list_users(admin_user: User = Depends(require_admin)):
    """List all whitelisted users. Admin only."""
    with session_scope() as session:
        rows = session.query(User.email, User.role, User.created_at).order_by(User.created_at).all()
    return [{"email": r.email, "role": r.role, "created_at": r.created_at} for r in rows]


@router.post("/users")
def add_user(user: UserCreate, admin_user: User = Depends(require_admin)):
    """Add a whitelisted user. Admin only."""
    if user.role not in ("admin", "trends"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'trends'")
    try:
        with session_scope() as session:
            session.add(User(email=user.email, role=user.role))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="User already exists")
    return {"message": "User added", "email": user.email, "role": user.role}


@router.put("/users")
def update_user_role(email: str = Query(...), role: str = Query(...), admin_user: User = Depends(require_admin)):
    """Update a user's role. Admin only."""
    if role not in ("admin", "trends"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'trends'")
    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.role = role
    return {"message": "Role updated", "email": email, "role": role}


@router.delete("/users")
def delete_user(email: str = Query(...), admin_user: User = Depends(require_admin)):
    """Remove a whitelisted user. Admin only."""
    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        session.delete(user)
    return {"message": "User removed", "email": email}


@router.get("/scrape-runs")
def get_scrape_runs(
    platform: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    admin_user: User = Depends(require_admin)
):
    """Retrieve history of scraping processes."""
    with session_scope() as session:
        query = session.query(ScrapeRun)
        if platform:
            query = query.filter(ScrapeRun.source == platform)
        if status:
            query = query.filter(ScrapeRun.status == status)
        
        runs = query.order_by(ScrapeRun.started_at.desc()).limit(limit).all()
        
        result = []
        for r in runs:
            errors = session.query(ScrapeError).filter(ScrapeError.scrape_run_id == r.id).all()
            error_map = {e.error_type: e.count for e in errors}
            
            result.append({
                "id": r.id,
                "source": r.source,
                "mode": r.mode,
                "status": r.status,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "items_fetched": r.items_fetched,
                "items_saved": r.items_saved,
                "error_count": r.error_count,
                "errors": error_map
            })
    return result


@router.get("/token_usage")
def get_token_usage(admin_user: User = Depends(require_admin)):
    """Return platform token usage stats. Admin only."""
    with session_scope() as session:
        rows = session.query(
            TokenUsage.platform,
            func.sum(TokenUsage.tokens_used).label("total"),
            func.max(TokenUsage.used_at).label("last_used")
        ).group_by(TokenUsage.platform).all()
    return [{"platform": r.platform, "total": r.total, "last_used": r.last_used} for r in rows]


@router.post("/azure/setup_schema")
def setup_azure_schema(background_tasks: BackgroundTasks, admin_user: User = Depends(require_admin)):
    """Trigger the creation of the Azure SQL schema (tables and indices)."""
    background_tasks.add_task(run_setup_azure_schema)
    return {"message": "Schema setup task started in background"}


@router.post("/azure/migrate")
def azure_migrate(admin_user: User = Depends(require_admin)):
    """Run database migrations to sync models with DB schema."""
    result = run_migration()
    return result.summary()


@router.get("/azure/status")
def azure_status(admin_user: User = Depends(require_admin)):
    """Return database connection status and recent diagnostics."""
    last = get_last_diagnostic()
    return {
        "connected": last is not None and last.get("success", False),
        "last_check": last.get("timestamp") if last else None,
        "details": last
    }


@router.get("/azure/diagnose")
def azure_diagnose(admin_user: User = Depends(require_admin)):
    """Run a fresh database connection diagnostic."""
    diag = run_connection_diagnose()
    return diag

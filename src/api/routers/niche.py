from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from src.db.connection import session_scope
from src.db.models import Niche, User
from src.db.sql_compat import insert_niche_if_not_exists
from src.niche.niche_discovery import NicheDiscovery
from src.api.deps import get_current_user

router = APIRouter(prefix="/niches", tags=["niches"])

niche_discovery = NicheDiscovery()


class NicheCreate(BaseModel):
    niche_name: str
    keywords: List[str] = []


class KeywordAdd(BaseModel):
    keywords: List[str]


@router.get("", response_model=List[str])
def get_niches():
    """Return distinct niche names from the DB."""
    try:
        with session_scope() as session:
            rows = session.query(Niche.niche_name).distinct().order_by(Niche.niche_name).all()
        return [r.niche_name for r in rows]
    except Exception:
        # Fallback to local discovery engine
        return list(niche_discovery.niche_map.keys())


@router.get("/{niche_name}/keywords")
def get_niche_keywords(niche_name: str):
    """Return keywords for a niche from the DB."""
    try:
        with session_scope() as session:
            rows = session.query(Niche.keyword).filter(
                Niche.niche_name == niche_name
            ).order_by(Niche.keyword).all()
        keywords = [r.keyword for r in rows]
        if not keywords:
            # Fallback to discovery engine
            keywords = niche_discovery.niche_map.get(niche_name, [niche_name])
        return {"niche": niche_name, "keywords": keywords}
    except Exception:
        keywords = niche_discovery.niche_map.get(niche_name, [niche_name])
        return {"niche": niche_name, "keywords": keywords}


@router.post("")
def create_niche(body: NicheCreate, user: User = Depends(get_current_user)):
    """Create a new niche with optional keywords."""
    if not body.niche_name.strip():
        raise HTTPException(status_code=400, detail="Niche name cannot be empty")
    
    keywords = body.keywords if body.keywords else [body.niche_name.strip()]
    added = 0
    with session_scope() as session:
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            insert_niche_if_not_exists(session, body.niche_name.strip(), kw)
            added += 1
    
    return {"message": f"Niche '{body.niche_name}' created with {added} keywords", "niche": body.niche_name}


@router.post("/{niche_name}/keywords")
def add_keywords_to_niche(niche_name: str, body: KeywordAdd, user: User = Depends(get_current_user)):
    """Add multiple keywords to an existing niche."""
    if not body.keywords:
        raise HTTPException(status_code=400, detail="No keywords provided")
    
    added = 0
    with session_scope() as session:
        for kw in body.keywords:
            kw = kw.strip()
            if not kw:
                continue
            insert_niche_if_not_exists(session, niche_name, kw)
            added += 1
            
    return {"message": f"Added {added} keywords to niche '{niche_name}'", "niche": niche_name}

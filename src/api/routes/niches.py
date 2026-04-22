"""Niche-management endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.dependencies import niche, session_scope
from src.api.schemas import NicheKeywordsResponse, NicheMutationResponse
from src.db.models import Niche
from src.db.sql_compat import insert_niche_if_not_exists

router = APIRouter(tags=["niches"])


class NicheCreate(BaseModel):
    niche_name: str
    keywords: list[str] = []


class KeywordAdd(BaseModel):
    keywords: list[str]


@router.get("/niches", response_model=list[str])
def get_niches():
    """Return distinct niche names from the DB."""
    try:
        with session_scope() as session:
            rows = session.query(Niche.niche_name).distinct().order_by(Niche.niche_name).all()
        return [r.niche_name for r in rows]
    except Exception:
        return niche.get_available_niches()


@router.get("/niche_keywords/{niche_name}", response_model=NicheKeywordsResponse)
def get_niche_keywords(niche_name: str):
    """Return keywords for a niche from the DB."""
    try:
        with session_scope() as session:
            rows = session.query(Niche.keyword).filter(
                Niche.niche_name == niche_name
            ).order_by(Niche.keyword).all()
        keywords = [r.keyword for r in rows]
        return {"niche": niche_name, "keywords": keywords if keywords else [niche_name]}
    except Exception:
        keywords = niche.get_niche_keywords(niche_name)
        return {"niche": niche_name, "keywords": keywords}


@router.post("/niches", response_model=NicheMutationResponse)
def create_niche(body: NicheCreate):
    """Create a new niche with optional keywords.

    Rows created via this endpoint are flagged ``is_seed=False`` so that
    ``POST /admin/niches/reset_defaults`` will leave them untouched.
    """
    if not body.niche_name.strip():
        raise HTTPException(status_code=400, detail="Niche name cannot be empty")
    keywords = body.keywords if body.keywords else [body.niche_name.strip()]
    added = 0
    with session_scope() as session:
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            insert_niche_if_not_exists(session, body.niche_name.strip(), kw, is_seed=False)
            added += 1
    return {"message": f"Niche '{body.niche_name}' created with {added} keyword(s)"}


@router.post("/niches/{niche_name}/keywords", response_model=NicheMutationResponse)
def add_keywords(niche_name: str, body: KeywordAdd):
    """Add keywords to an existing niche.

    New rows are flagged ``is_seed=False`` (user-owned).
    """
    added = 0
    with session_scope() as session:
        for kw in body.keywords:
            kw = kw.strip()
            if not kw:
                continue
            insert_niche_if_not_exists(session, niche_name, kw, is_seed=False)
            added += 1
    return {"message": f"Added {added} keyword(s) to '{niche_name}'"}


@router.delete("/niches/{niche_name}", response_model=NicheMutationResponse)
def delete_niche(niche_name: str):
    """Delete an entire niche and all its keywords."""
    with session_scope() as session:
        count = session.query(Niche).filter(Niche.niche_name == niche_name).delete()
        if count == 0:
            raise HTTPException(status_code=404, detail="Niche not found")
    return {"message": f"Niche '{niche_name}' deleted"}


@router.delete("/niches/{niche_name}/keywords/{keyword}", response_model=NicheMutationResponse)
def delete_keyword(niche_name: str, keyword: str):
    """Remove a single keyword from a niche."""
    with session_scope() as session:
        count = session.query(Niche).filter(
            Niche.niche_name == niche_name,
            Niche.keyword == keyword,
        ).delete()
        if count == 0:
            raise HTTPException(status_code=404, detail="Keyword not found")
    return {"message": f"Keyword '{keyword}' removed from '{niche_name}'"}


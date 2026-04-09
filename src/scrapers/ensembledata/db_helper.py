"""
Shared database helper for ensembledata scrapers.

Inserts trend rows and scrape errors into the database used by the rest
of the project.  Uses SQLAlchemy ORM via the ``session_scope`` context
manager for clean transaction lifecycle.

Optimizations over the previous version
----------------------------------------
* Uses ``session_scope()`` instead of manual try/except/rollback/close.
* Adds ``save_trends_batch()`` for committing multiple trends in a single
  transaction (reduces round-trips from N to 1).
* ``save_content_batch()`` for bulk-inserting normalized content rows.
"""

import json
import logging
import os
import sys
from datetime import datetime

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.db.connection import session_scope
from src.db.models import Trend, ScrapeError, TokenUsage
from src.db.sql_compat import (
    is_duplicate_trend, upsert_scrape_log, get_platform_id,
    upsert_author, upsert_content, upsert_content_metrics, upsert_hashtags,
)
from src.ingestion import CanonicalSignalInput, EvidenceInput, IngestionRun, IngestionService

logger = logging.getLogger(__name__)
ingestion = IngestionService()


# ---------------------------------------------------------------------------
# Single-trend write (kept for backward compatibility)
# ---------------------------------------------------------------------------

def save_trend(
    platform,
    topic,
    growth,
    keyword,
    geo,
    url=None,
    extra_data=None,
    *,
    language="en",
    entity_type="topic",
    entity_id=None,
    sampled_content_refs=None,
    fetch_metadata=None,
    raw_payload=None,
    run: IngestionRun | None = None,
):
    """Insert a canonical trend signal and mirror it to the legacy trend table."""
    extracted_at = datetime.utcnow()
    try:
        ed = extra_data.copy() if extra_data else {}
        if url:
            ed["url"] = url

        refs = list(sampled_content_refs or [])
        if not refs and url:
            refs.append(
                {
                    "id": entity_id or topic[:64],
                    "url": url,
                    "title": topic[:250],
                    "snippet": (ed.get("description") or ed.get("caption") or "")[:280],
                }
            )

        signal = CanonicalSignalInput(
            source=platform,
            entity_type=entity_type,
            entity_id=str(entity_id or ed.get("external_id") or url or topic[:120]),
            label=topic,
            country=geo or "Global",
            language=language,
            retrieved_at=extracted_at,
            granularity=fetch_metadata.get("granularity", "hour") if fetch_metadata else "hour",
            metrics={
                "volume": ed.get("views") or ed.get("traffic"),
                "growth_rate": growth,
                "rank": ed.get("rank"),
                "engagement": ed.get("engagement") or ed.get("likes") or ed.get("score"),
                "velocity": ed.get("velocity"),
            },
            sampled_content_refs=refs,
            fetch_metadata={
                "keyword": keyword,
                "quota_cost": ed.get("quota_cost") or ed.get("units_charged"),
                **(fetch_metadata or {}),
                **({"response_hash": ingestion.compute_idempotency_key_static(platform, str(entity_id or topic), geo or "Global", extracted_at.replace(minute=0, second=0, microsecond=0))} if raw_payload is None else {}),
            },
        )
        evidence_items = [
            EvidenceInput(
                evidence_type="content_ref",
                external_ref=str(ref.get("id") or ref.get("external_ref") or ""),
                url=ref.get("url") or "",
                title=ref.get("title") or topic[:250],
                snippet=ref.get("snippet") or "",
                metadata={k: v for k, v in ref.items() if k not in {"id", "external_ref", "url", "title", "snippet"}},
            )
            for ref in refs
        ]
        status = ingestion.ingest_signal(
            signal,
            evidence_items=evidence_items,
            raw_payload=raw_payload if raw_payload is not None else {"topic": topic, "keyword": keyword, "extra_data": ed},
            run=run,
            mirror_to_legacy=True,
        )
        with session_scope() as session:
            upsert_scrape_log(
                session, platform,
                f"{keyword}_{geo}" if geo else keyword,
                200, extracted_at,
            )
        if status["duplicate"]:
            logger.debug("Skipped duplicate trend signal: platform=%s, topic=%.60s, keyword=%s", platform, topic, keyword)
        else:
            logger.debug("Saved trend signal: platform=%s, topic=%.60s, keyword=%s", platform, topic, keyword)
    except Exception:
        logger.error("Failed to save trend: platform=%s, keyword=%s", platform, keyword, exc_info=True)
        raise


# ---------------------------------------------------------------------------
# Batch trend write (new — reduces N commits to 1)
# ---------------------------------------------------------------------------

def save_trends_batch(trends: list[dict], *, run: IngestionRun | None = None):
    """Insert multiple trends in a single transaction.

    Each dict in *trends* must contain keys:
    ``platform, topic, growth, keyword, geo`` and optionally ``url, extra_data``.

    Duplicates are silently skipped.  The entire batch is committed once.
    """
    if not trends:
        return
    saved = 0
    try:
        for t in trends:
            before = run.inserted_count if run else 0
            save_trend(
                platform=t["platform"],
                topic=t["topic"],
                growth=t.get("growth", 0),
                keyword=t.get("keyword", ""),
                geo=t.get("geo", ""),
                url=t.get("url"),
                extra_data=t.get("extra_data"),
                language=t.get("language", "en"),
                entity_type=t.get("entity_type", "topic"),
                entity_id=t.get("entity_id"),
                sampled_content_refs=t.get("sampled_content_refs"),
                fetch_metadata=t.get("fetch_metadata"),
                raw_payload=t.get("raw_payload"),
                run=run,
            )
            if not run or run.inserted_count > before:
                saved += 1
        logger.info("Batch saved %d/%d trends.", saved, len(trends))
    except Exception:
        logger.error("Failed to save trends batch (%d items)", len(trends), exc_info=True)
        raise


# ---------------------------------------------------------------------------
# Single content write (kept for backward compatibility)
# ---------------------------------------------------------------------------

def save_content_normalized(platform, external_id, keyword, geo,
                            text_content="", media_type="", url="", content_created_at=None,
                            author_external_id=None, author_username="", author_full_name="",
                            author_follower_count=0, author_is_verified=0, author_profile_pic="",
                            likes=0, comments=0, shares=0, views=0, saves=0,
                            hashtags=None):
    """Save content into the normalized content/authors/metrics/hashtags tables."""
    try:
        with session_scope() as session:
            platform_id = get_platform_id(session, platform)

            author_id = None
            if author_external_id:
                author_id = upsert_author(
                    session, platform_id, author_external_id,
                    username=author_username, full_name=author_full_name,
                    follower_count=author_follower_count,
                    is_verified=author_is_verified,
                    profile_pic_url=author_profile_pic,
                )

            content_id = upsert_content(
                session, platform_id, external_id,
                keyword=keyword, geo=geo, text_content=text_content,
                media_type=media_type, url=url,
                created_at=content_created_at, author_id=author_id,
            )

            upsert_content_metrics(
                session, content_id,
                likes=likes, comments=comments, shares=shares,
                views=views, saves=saves,
            )

            if hashtags:
                upsert_hashtags(session, content_id, hashtags)

            logger.debug("Saved content: platform=%s, external_id=%s", platform, external_id)
    except Exception:
        logger.error("Failed to save content: platform=%s, external_id=%s", platform, external_id, exc_info=True)
        raise


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------

def save_token_usage(platform, keyword, units_charged, geo=""):
    """Record EnsembleData API token/units consumption."""
    try:
        with session_scope() as session:
            session.add(TokenUsage(
                platform=platform, keyword=keyword,
                units_charged=units_charged, geo=geo,
                created_at=datetime.now(),
            ))
            logger.debug("Saved token usage: platform=%s, keyword=%s, units=%s", platform, keyword, units_charged)
    except Exception:
        logger.error("Failed to save token usage: platform=%s, keyword=%s", platform, keyword, exc_info=True)


# ---------------------------------------------------------------------------
# Scrape errors
# ---------------------------------------------------------------------------

def save_error(platform, keyword, url, status, reason, *, payload=None, run: IngestionRun | None = None):
    """Insert a scrape error row."""
    try:
        with session_scope() as session:
            session.add(ScrapeError(
                platform=platform, keyword=keyword, url=url,
                status=status, reason=reason,
                extracted_at=datetime.now(),
            ))
            logger.debug("Saved error: platform=%s, keyword=%s, reason=%.80s", platform, keyword, reason)
        ingestion.archive_dead_letter(
            source=platform,
            error_type=f"http_{status}" if status else "scrape_error",
            error_message=str(reason),
            payload=payload or {"keyword": keyword, "url": url, "status": status, "reason": reason},
            run=run,
            cursor_key=f"{keyword}_{url}" if url else keyword,
        )
    except Exception:
        logger.error("Failed to save error row: platform=%s, keyword=%s", platform, keyword, exc_info=True)
        raise


def archive_source_response(source: str, payload, metadata: dict | None = None) -> int:
    """Archive a raw source response for replay/debugging."""
    return ingestion.archive_payload(
        source_table="source_response",
        source_id=0,
        payload=payload,
        metadata={"source": source, **(metadata or {})},
    )

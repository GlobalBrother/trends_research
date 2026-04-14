import hashlib
import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional

from src.db.connection import session_scope
from src.db.models import (
    CanonicalTrendSignal,
    RawDataArchive,
    ScrapeDeadLetter,
    ScrapeRun,
    SourceCursor,
    Trend,
    TrendEvidence,
)
from src.db.sql_compat import get_platform_id, is_duplicate_trend
from .config import load_source_config

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _normalize_label(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _json_dumps(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)


def _response_hash(payload) -> str:
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _bucket_time(ts: datetime, granularity: str) -> datetime:
    if granularity == "day":
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == "minute":
        return ts.replace(second=0, microsecond=0)
    return ts.replace(minute=0, second=0, microsecond=0)


def _freshness_score(retrieved_at: datetime, window_hours: int) -> float:
    if not retrieved_at:
        return 0.0
    hours_ago = max((_utcnow() - retrieved_at).total_seconds() / 3600.0, 0.0)
    if window_hours <= 0:
        return 1.0
    return max(0.0, 1.0 - (hours_ago / float(window_hours)))


def _source_confidence(source: str, evidence_count: int, country: str) -> float:
    base = {
        "Google Trends": 0.82,
        "Google Trending Now": 0.8,
        "YouTube": 0.76,
        "Reddit": 0.74,
        "TikTok": 0.72,
        "Instagram": 0.7,
        "Threads": 0.68,
        "HackerNews": 0.78,
        "News": 0.75,
        "GetHookdAI": 0.84,
    }.get(source, 0.65)
    evidence_boost = min(evidence_count, 3) * 0.04
    geo_boost = 0.04 if country and country not in ("", "Global") else 0.0
    return min(1.0, base + evidence_boost + geo_boost)


@dataclass
class EvidenceInput:
    evidence_type: str = "content_ref"
    external_ref: str = ""
    url: str = ""
    title: str = ""
    snippet: str = ""
    metadata: dict = field(default_factory=dict)
    content_id: Optional[int] = None


@dataclass
class CanonicalSignalInput:
    source: str
    entity_type: str
    entity_id: str
    label: str
    country: str
    language: str
    retrieved_at: datetime
    granularity: str
    metrics: dict = field(default_factory=dict)
    sampled_content_refs: list[dict] = field(default_factory=list)
    fetch_metadata: dict = field(default_factory=dict)
    time_bucket_start: Optional[datetime] = None

    def as_storage_dict(self) -> dict:
        bucket = _bucket_time(self.time_bucket_start or self.retrieved_at, self.granularity)
        refs = self.sampled_content_refs or []
        return {
            "source": self.source,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "label": self.label,
            "normalized_label": _normalize_label(self.label),
            "country": self.country,
            "language": self.language,
            "time_bucket_start": bucket,
            "granularity": self.granularity,
            "volume": self.metrics.get("volume"),
            "growth_rate": self.metrics.get("growth_rate"),
            "rank": self.metrics.get("rank"),
            "engagement": self.metrics.get("engagement"),
            "velocity": self.metrics.get("velocity"),
            "sampled_content_refs": _json_dumps(refs),
            "retrieved_at": self.retrieved_at,
            "fetch_metadata": _json_dumps(self.fetch_metadata),
            "idempotency_key": IngestionService.compute_idempotency_key_static(
                self.source,
                self.entity_id or self.label,
                self.country,
                bucket,
            ),
            "evidence_count": len(refs),
            "source_confidence": _source_confidence(self.source, len(refs), self.country),
            "freshness_score": _freshness_score(
                self.retrieved_at,
                int(load_source_config(self.source).get("backfill_window_hours", 24)),
            ),
        }


@dataclass
class IngestionRun:
    run_id: int
    source: str
    started_at: datetime
    config: dict
    fetched_count: int = 0
    parsed_count: int = 0
    inserted_count: int = 0
    deduped_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    quota_usage: float = 0.0
    total_latency_ms: float = 0.0
    error_types: dict[str, int] = field(default_factory=dict)

    def record_error(self, error_type: str):
        self.failed_count += 1
        self.error_types[error_type] = self.error_types.get(error_type, 0) + 1


class IngestionRetryError(RuntimeError):
    pass


class _CircuitBreaker:
    def __init__(self):
        self._state: dict[str, dict] = {}

    def allow(self, source: str) -> bool:
        item = self._state.get(source)
        if not item:
            return True
        opened_at = item.get("opened_at")
        if item.get("failures", 0) < item.get("threshold", 3):
            return True
        if opened_at and (_utcnow() - opened_at).total_seconds() > item.get("cooldown_seconds", 300):
            self._state[source] = {
                "failures": 0,
                "threshold": item.get("threshold", 3),
                "cooldown_seconds": item.get("cooldown_seconds", 300),
            }
            return True
        return False

    def fail(self, source: str, threshold: int = 3, cooldown_seconds: int = 300):
        item = self._state.setdefault(
            source,
            {"failures": 0, "threshold": threshold, "cooldown_seconds": cooldown_seconds},
        )
        item["failures"] += 1
        if item["failures"] >= threshold:
            item["opened_at"] = _utcnow()

    def success(self, source: str):
        self._state[source] = {"failures": 0, "threshold": 3, "cooldown_seconds": 300}


_breaker = _CircuitBreaker()


class IngestionService:
    @staticmethod
    def compute_idempotency_key_static(source: str, entity_key: str, country: str, time_bucket_start: datetime) -> str:
        raw = f"{source}|{entity_key}|{country or 'Global'}|{time_bucket_start.isoformat()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def load_source_config(self, source: str) -> dict:
        return load_source_config(source)

    def start_run(
        self,
        source: str,
        acquisition_mode: Optional[str] = None,
        country: str = "",
        language: str = "en",
        category: str = "",
    ) -> IngestionRun:
        config = self.load_source_config(source)
        with session_scope() as session:
            row = ScrapeRun(
                source=source,
                acquisition_mode=acquisition_mode or config.get("acquisition_mode", "api"),
                country=country or None,
                language=language or None,
                category=category or None,
                status="running",
                started_at=_utcnow(),
            )
            session.add(row)
            session.flush()
            run_id = row.id
        return IngestionRun(run_id=run_id, source=source, started_at=_utcnow(), config=config)

    def finish_run(self, run: IngestionRun):
        duplicate_ratio = 0.0
        if run.parsed_count:
            duplicate_ratio = run.deduped_count / float(run.parsed_count)
        alert_state = "ok"
        if run.failed_count > max(3, run.parsed_count * 0.3):
            alert_state = "alert"
        elif duplicate_ratio > 0.4:
            alert_state = "warning"
        stale_window_hours = (_utcnow() - run.started_at).total_seconds() / 3600.0
        summary = {
            "source": run.source,
            "counts": {
                "fetched": run.fetched_count,
                "parsed": run.parsed_count,
                "inserted": run.inserted_count,
                "deduped": run.deduped_count,
                "skipped": run.skipped_count,
                "failed": run.failed_count,
            },
            "error_types": run.error_types,
        }
        with session_scope() as session:
            row = session.query(ScrapeRun).filter(ScrapeRun.id == run.run_id).first()
            if not row:
                return
            row.status = "failed" if run.failed_count and not run.inserted_count else "completed"
            row.fetched_count = run.fetched_count
            row.parsed_count = run.parsed_count
            row.inserted_count = run.inserted_count
            row.deduped_count = run.deduped_count
            row.skipped_count = run.skipped_count
            row.failed_count = run.failed_count
            row.duplicate_ratio = duplicate_ratio
            row.quota_usage = run.quota_usage
            row.latency_ms = run.total_latency_ms
            row.top_error_types = _json_dumps(run.error_types)
            row.stale_window_hours = stale_window_hours
            row.alert_state = alert_state
            row.summary_json = _json_dumps(summary)
            row.finished_at = _utcnow()

    def archive_payload(self, source_table: str, source_id: int, payload, metadata: Optional[dict] = None) -> int:
        wrapper = {
            "metadata": metadata or {},
            "response_hash": _response_hash(payload),
            "payload": payload,
        }
        with session_scope() as session:
            row = RawDataArchive(
                source_table=source_table,
                source_id=source_id,
                raw_data=_json_dumps(wrapper),
            )
            session.add(row)
            session.flush()
            archive_id = row.id
        return archive_id

    def ingest_signal(
        self,
        signal: CanonicalSignalInput,
        evidence_items: Optional[list[EvidenceInput]] = None,
        raw_payload=None,
        run: Optional[IngestionRun] = None,
        mirror_to_legacy: bool = True,
    ) -> dict:
        row_data = signal.as_storage_dict()
        evidence_items = evidence_items or []
        status = {"inserted": False, "duplicate": False, "canonical_signal_id": None, "legacy_trend_id": None}

        with session_scope() as session:
            existing = session.query(CanonicalTrendSignal).filter(
                CanonicalTrendSignal.idempotency_key == row_data["idempotency_key"]
            ).first()
            if existing:
                status["duplicate"] = True
                status["canonical_signal_id"] = existing.id
                if run:
                    run.deduped_count += 1
                return status

            legacy_trend_id = None
            if mirror_to_legacy:
                platform_id = get_platform_id(session, signal.source)
                legacy_topic = signal.label[:500]
                legacy_keyword = signal.fetch_metadata.get("keyword") or signal.label[:120]
                legacy_geo = signal.country or "Global"
                if is_duplicate_trend(session, platform_id, legacy_topic, legacy_keyword, legacy_geo):
                    if run:
                        run.deduped_count += 1
                else:
                    legacy = Trend(
                        platform_id=platform_id,
                        topic=legacy_topic,
                        growth=row_data.get("growth_rate") or row_data.get("engagement") or row_data.get("volume") or 0.0,
                        keyword=legacy_keyword,
                        geo=legacy_geo,
                        extracted_at=signal.retrieved_at,
                        extra_data=_json_dumps(
                            {
                                "metrics": signal.metrics,
                                "sampled_content_refs": signal.sampled_content_refs,
                                "fetch_metadata": signal.fetch_metadata,
                            }
                        ),
                    )
                    session.add(legacy)
                    session.flush()
                    legacy_trend_id = legacy.id

            canonical = CanonicalTrendSignal(**row_data, legacy_trend_id=legacy_trend_id)
            session.add(canonical)
            session.flush()

            for ref in evidence_items:
                session.add(
                    TrendEvidence(
                        signal_id=canonical.id,
                        content_id=ref.content_id,
                        evidence_type=ref.evidence_type,
                        external_ref=ref.external_ref,
                        url=ref.url,
                        title=ref.title,
                        snippet=ref.snippet,
                        metadata_json=_json_dumps(ref.metadata),
                    )
                )

            if not evidence_items and signal.sampled_content_refs:
                first = signal.sampled_content_refs[0]
                session.add(
                    TrendEvidence(
                        signal_id=canonical.id,
                        evidence_type="sampled_content_ref",
                        external_ref=str(first.get("id") or first.get("external_ref") or ""),
                        url=first.get("url") or "",
                        title=first.get("title") or signal.label[:250],
                        snippet=first.get("snippet") or "",
                        metadata_json=_json_dumps(first),
                    )
                )

            status["inserted"] = True
            status["canonical_signal_id"] = canonical.id
            status["legacy_trend_id"] = legacy_trend_id

        if raw_payload is not None and status["canonical_signal_id"]:
            self.archive_payload(
                source_table="canonical_trend_signals",
                source_id=status["canonical_signal_id"],
                payload=raw_payload,
                metadata={"source": signal.source, "entity_id": signal.entity_id, "idempotency_key": row_data["idempotency_key"]},
            )

        if run:
            run.parsed_count += 1
            if status["inserted"]:
                run.inserted_count += 1
        return status

    def archive_dead_letter(
        self,
        source: str,
        error_type: str,
        error_message: str,
        payload=None,
        run: Optional[IngestionRun] = None,
        cursor_key: str = "",
        retry_count: int = 0,
    ) -> int:
        payload_ref = ""
        if payload is not None:
            archive_id = self.archive_payload(
                source_table="scrape_dead_letters",
                source_id=run.run_id if run else 0,
                payload=payload,
                metadata={"source": source, "cursor_key": cursor_key, "error_type": error_type},
            )
            payload_ref = str(archive_id)
        with session_scope() as session:
            row = ScrapeDeadLetter(
                source=source,
                scrape_run_id=run.run_id if run else None,
                cursor_key=cursor_key or None,
                payload_ref=payload_ref or None,
                error_type=error_type,
                error_message=error_message,
                retry_count=retry_count,
            )
            session.add(row)
            session.flush()
            letter_id = row.id
        if run:
            run.record_error(error_type)
        return letter_id

    def update_cursor(
        self,
        source: str,
        country: str,
        language: str,
        category: str,
        cursor_value: str,
        payload=None,
        last_seen_entity_id: str = "",
    ):
        with session_scope() as session:
            row = session.query(SourceCursor).filter(
                SourceCursor.source == source,
                SourceCursor.country == (country or None),
                SourceCursor.language == (language or None),
                SourceCursor.category == (category or None),
            ).first()
            digest = _response_hash(payload) if payload is not None else None
            if row:
                row.cursor_value = cursor_value
                row.response_hash = digest
                row.last_seen_entity_id = last_seen_entity_id or row.last_seen_entity_id
                row.last_success_at = _utcnow()
                row.updated_at = _utcnow()
            else:
                session.add(
                    SourceCursor(
                        source=source,
                        country=country or None,
                        language=language or None,
                        category=category or None,
                        cursor_value=cursor_value,
                        response_hash=digest,
                        last_seen_entity_id=last_seen_entity_id or None,
                        last_success_at=_utcnow(),
                        updated_at=_utcnow(),
                    )
                )

    def _categorize_error(self, exc: Exception) -> str:
        """Categorize an exception into a standard error type."""
        name = type(exc).__name__
        msg = str(exc).lower()
        
        if "rate limit" in msg or "429" in msg:
            return "RateLimitError"
        if "timeout" in msg or "timed out" in msg:
            return "TimeoutError"
        if "connection" in msg or "unreachable" in msg:
            return "NetworkError"
        if "auth" in msg or "401" in msg or "403" in msg or "forbidden" in msg:
            return "AuthError"
        
        return name

    def with_retry(
        self,
        source: str,
        func: Callable[[], object],
        retries: Optional[int] = None,
        base_delay: float = 1.0,
        max_delay: float = 12.0,
        run: Optional[IngestionRun] = None,
        payload_hint=None,
    ):
        config = self.load_source_config(source)
        retry_limit = retries if retries is not None else int(config.get("rate_limit", {}).get("retry_times", 3))
        if not _breaker.allow(source):
            raise IngestionRetryError(f"Circuit breaker is open for {source}")

        last_exc = None
        for attempt in range(retry_limit + 1):
            started = time.perf_counter()
            try:
                result = func()
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                if run:
                    run.total_latency_ms += elapsed_ms
                _breaker.success(source)
                return result
            except Exception as exc:
                last_exc = exc
                _breaker.fail(source)
                error_type = self._categorize_error(exc)
                if run:
                    run.record_error(error_type)
                
                if attempt >= retry_limit:
                    logger.error(f"Ingestion failed for {source} after {attempt} retries: {exc}")
                    self.archive_dead_letter(
                        source=source,
                        error_type=error_type,
                        error_message=str(exc),
                        payload=payload_hint,
                        run=run,
                        retry_count=attempt,
                    )
                    raise IngestionRetryError(f"{source} failed after {retry_limit + 1} attempts") from exc
                
                delay = min(max_delay, base_delay * (2 ** attempt)) + random.uniform(0.0, 0.5)
                logger.warning(f"Retry {attempt + 1}/{retry_limit} for {source} after {delay:.2f}s due to {error_type}")
                time.sleep(delay)
        raise IngestionRetryError(str(last_exc))

    def daily_health_report(self, source: Optional[str] = None, days: int = 1) -> list[dict]:
        since = _utcnow() - timedelta(days=days)
        with session_scope() as session:
            query = session.query(ScrapeRun).filter(ScrapeRun.started_at >= since)
            if source:
                query = query.filter(ScrapeRun.source == source)
            rows = query.order_by(ScrapeRun.started_at.desc()).all()

        grouped: dict[str, dict] = {}
        for row in rows:
            bucket = grouped.setdefault(
                row.source,
                {
                    "source": row.source,
                    "runs": 0,
                    "fetched": 0,
                    "parsed": 0,
                    "inserted": 0,
                    "deduped": 0,
                    "failed": 0,
                    "quota_usage": 0.0,
                    "latency_ms": 0.0,
                    "duplicate_ratio": 0.0,
                    "top_error_types": {},
                    "alert_state": "ok",
                },
            )
            bucket["runs"] += 1
            bucket["fetched"] += row.fetched_count
            bucket["parsed"] += row.parsed_count
            bucket["inserted"] += row.inserted_count
            bucket["deduped"] += row.deduped_count
            bucket["failed"] += row.failed_count
            bucket["quota_usage"] += row.quota_usage
            bucket["latency_ms"] += row.latency_ms
            bucket["duplicate_ratio"] += row.duplicate_ratio
            if row.alert_state == "alert" or (bucket["alert_state"] == "ok" and row.alert_state == "warning"):
                bucket["alert_state"] = row.alert_state
            errors = json.loads(row.top_error_types or "{}")
            for key, value in errors.items():
                bucket["top_error_types"][key] = bucket["top_error_types"].get(key, 0) + value

        report = []
        for item in grouped.values():
            runs = max(item["runs"], 1)
            item["avg_latency_ms"] = round(item.pop("latency_ms") / runs, 2)
            item["avg_duplicate_ratio"] = round(item.pop("duplicate_ratio") / runs, 4)
            item["anomaly"] = (
                item["alert_state"] != "ok"
                or item["failed"] > item["inserted"]
                or item["avg_duplicate_ratio"] > 0.4
            )
            report.append(item)
        return sorted(report, key=lambda row: (not row["anomaly"], row["source"]))

    def replay_archived_payloads(self, source: str, limit: int = 20) -> list[dict]:
        with session_scope() as session:
            signals = (
                session.query(CanonicalTrendSignal)
                .filter(CanonicalTrendSignal.source == source)
                .order_by(CanonicalTrendSignal.created_at.desc())
                .limit(limit)
                .all()
            )
            signal_ids = [row.id for row in signals]
            archives = (
                session.query(RawDataArchive)
                .filter(
                    RawDataArchive.source_table == "canonical_trend_signals",
                    RawDataArchive.source_id.in_(signal_ids or [0]),
                )
                .all()
            )
        archive_map = {row.source_id: json.loads(row.raw_data or "{}") for row in archives}
        replay = []
        for signal in signals:
            replay.append(
                {
                    "signal_id": signal.id,
                    "source": signal.source,
                    "entity_id": signal.entity_id,
                    "label": signal.label,
                    "idempotency_key": signal.idempotency_key,
                    "payload": archive_map.get(signal.id, {}).get("payload"),
                    "metadata": archive_map.get(signal.id, {}).get("metadata", {}),
                }
            )
        return replay

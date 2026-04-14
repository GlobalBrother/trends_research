"""Deterministic cluster, matching, insight, and reporting pipeline."""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session, load_only

from src.analytics.analytics_engine import AnalyticsEngine
from src.db.models import (
    AdsInsight,
    BacktestRun,
    Platform,
    ReportBrief,
    ScrapeError,
    TokenUsage,
    Trend,
    TrendAdMatch,
    TrendCluster,
    TrendInsight,
    TrendSignal,
)

logger = logging.getLogger(__name__)

INSIGHT_SCORE_WEIGHTS = {
    "trend_strength": float(os.getenv("INSIGHT_WEIGHT_TREND_STRENGTH", "0.30")),
    "commercial_relevance": float(os.getenv("INSIGHT_WEIGHT_COMMERCIAL_RELEVANCE", "0.25")),
    "audience_signal": float(os.getenv("INSIGHT_WEIGHT_AUDIENCE_SIGNAL", "0.20")),
    "creative_reusability": float(os.getenv("INSIGHT_WEIGHT_CREATIVE_REUSABILITY", "0.15")),
    "saturation": float(os.getenv("INSIGHT_WEIGHT_SATURATION", "0.07")),
    "safety_risk": float(os.getenv("INSIGHT_WEIGHT_SAFETY_RISK", "0.03")),
}

FRESHNESS_WINDOW_HOURS = int(os.getenv("INSIGHT_FRESHNESS_WINDOW_HOURS", "48"))
CLUSTER_LOOKBACK_DAYS = int(os.getenv("INSIGHT_CLUSTER_LOOKBACK_DAYS", "21"))
MAX_MATCHES_PER_CLUSTER = int(os.getenv("INSIGHT_MAX_MATCHES_PER_CLUSTER", "15"))
MIN_MATCH_SCORE = float(os.getenv("INSIGHT_MIN_MATCH_SCORE", "0.28"))
UNSAFE_TERMS = {
    "nsfw", "gambling", "violence", "weapon", "crypto scam", "hate", "adult",
    "exploit", "fake", "misleading", "controversy",
}


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))


def _safe_json(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=True)


def _safe_load_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return [v.strip() for v in value.split(",") if v.strip()]
    return [value]


def _tokenize(text: Any) -> set[str]:
    if text is None:
        return set()
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", str(text).lower())
        if token not in {"with", "from", "this", "that", "have", "will", "your", "about"}
    }


def _token_jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def _ngram_similarity(a: str, b: str, n: int = 3) -> float:
    if not a or not b:
        return 0.0

    def grams(text: str) -> set[str]:
        normalized = re.sub(r"\s+", " ", text.lower().strip())
        if len(normalized) < n:
            return {normalized} if normalized else set()
        return {normalized[i:i + n] for i in range(len(normalized) - n + 1)}

    return _token_jaccard(grams(a), grams(b))


def _semantic_proxy_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    seq = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    ngram = _ngram_similarity(a, b)
    token = _token_jaccard(_tokenize(a), _tokenize(b))
    return (seq * 0.4) + (ngram * 0.35) + (token * 0.25)


def _parse_date(value: Any) -> datetime | None:
    if value in (None, "", "N/A"):
        return None
    if isinstance(value, datetime):
        return value
    try:
        ts = pd.to_datetime(value, utc=False, errors="coerce")
        return None if pd.isna(ts) else ts.to_pydatetime()
    except Exception:
        return None


def _slugify(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return base[:240] or "cluster"


class InsightPipeline:
    """Generate deterministic cluster-level insights from stored trend and ad data."""

    def __init__(self, analytics: AnalyticsEngine | None = None) -> None:
        self.analytics = analytics or AnalyticsEngine()

    def canonical_schemas(self) -> dict[str, Any]:
        """Return canonical schema definitions for core entities."""
        return {
            "trend": {
                "primary_key": "trends.id",
                "fields": ["topic", "keyword", "platform_id", "growth", "geo", "extracted_at", "extra_data"],
                "notes": "Raw trend signal from any platform-specific scraper.",
            },
            "content": {
                "primary_key": "content.id",
                "fields": ["platform_id", "external_id", "keyword", "geo", "text_content", "media_type", "url", "created_at", "author_id"],
                "notes": "Normalized social/content item with engagement metrics stored in content_metrics.",
            },
            "ad": {
                "primary_key": "ads_insight.id",
                "fields": ["search_keyword", "platform", "display_format", "title", "body", "cta_type", "start_date", "days_active", "performance_score", "brand_name"],
                "notes": "Tracked ad-library creative from GetHookdAI.",
            },
            "brand": {
                "primary_key": "my_brands.id",
                "fields": ["brand_name", "brand_external_id", "brand_logo_url", "brand_active_ads", "added_at"],
                "notes": "User-tracked brand for competitor and owned-brand monitoring.",
            },
            "insight": {
                "primary_key": "trend_insights.id",
                "fields": [
                    "cluster_id",
                    "ad_opportunity_score",
                    "trend_strength",
                    "confidence_score",
                    "audience_intent",
                    "creative_angle_candidates",
                    "platform_fit",
                    "ad_timing_window",
                    "saturation_risk",
                    "brand_safety_risk",
                    "monetization_potential",
                    "explanation_json",
                ],
                "notes": "Deterministic cluster-level opportunity record grounded in platform signals.",
            },
        }

    def build_monitoring_snapshot(self, session, now: datetime | None = None) -> dict[str, Any]:
        """Compute reliability and monitoring metrics from stored trends and scraper logs."""
        now = now or datetime.utcnow()

        trend_rows = (
            session.query(
                Platform.name.label("platform"),
                Trend.topic,
                Trend.keyword,
                Trend.geo,
                Trend.extracted_at,
            )
            .join(Platform, Platform.id == Trend.platform_id)
            .filter(Trend.extracted_at >= now - timedelta(days=CLUSTER_LOOKBACK_DAYS))
            .all()
        )
        trends_df = pd.DataFrame(trend_rows, columns=["platform", "topic", "keyword", "geo", "extracted_at"])

        errors = (
            session.query(
                ScrapeError.platform,
                func.count().label("count"),
                func.max(ScrapeError.extracted_at).label("last_error"),
            )
            .filter(ScrapeError.extracted_at >= now - timedelta(days=7))
            .group_by(ScrapeError.platform)
            .all()
        )
        error_map = {row.platform: {"count": row.count, "last_error": row.last_error} for row in errors}

        usage = (
            session.query(
                TokenUsage.platform,
                func.sum(TokenUsage.units_charged).label("units"),
                func.count().label("requests"),
                func.max(TokenUsage.created_at).label("last_request"),
            )
            .filter(TokenUsage.created_at >= now - timedelta(days=7))
            .group_by(TokenUsage.platform)
            .all()
        )
        usage_map = {
            row.platform: {"units": float(row.units or 0.0), "requests": int(row.requests or 0), "last_request": row.last_request}
            for row in usage
        }

        duplicates = 0
        missing_geo = 0
        missing_timestamp = 0
        platform_metrics: list[dict[str, Any]] = []

        if not trends_df.empty:
            trends_df = trends_df.copy()
            trends_df["platform"] = trends_df["platform"].fillna("Unknown")
            trends_df["geo_missing"] = trends_df["geo"].isna() | (trends_df["geo"].astype(str).str.strip() == "")
            trends_df["ts_missing"] = trends_df["extracted_at"].isna()
            missing_geo = int(trends_df["geo_missing"].sum())
            missing_timestamp = int(trends_df["ts_missing"].sum())
            duplicates = int(trends_df.duplicated(subset=["platform", "topic", "keyword", "geo", "extracted_at"]).sum())

            for platform_name, group in trends_df.groupby("platform", dropna=False):
                last_seen = pd.to_datetime(group["extracted_at"], errors="coerce").max()
                stale_hours = None
                freshness_score = 0.0
                if pd.notna(last_seen):
                    stale_hours = max(0.0, (now - last_seen.to_pydatetime()).total_seconds() / 3600.0)
                    freshness_score = _clamp((1 - (stale_hours / max(FRESHNESS_WINDOW_HOURS, 1))) * 100.0)
                error_count = error_map.get(platform_name, {}).get("count", 0)
                request_count = usage_map.get(platform_name, {}).get("requests", 0)
                base_confidence = 100.0 - min(35.0, error_count * 5.0)
                if stale_hours is not None and stale_hours > FRESHNESS_WINDOW_HOURS:
                    base_confidence -= min(40.0, stale_hours - FRESHNESS_WINDOW_HOURS)
                if request_count == 0:
                    base_confidence -= 10.0
                duplicate_rate = (group.duplicated(subset=["topic", "keyword", "geo", "extracted_at"]).sum() / len(group)) * 100 if len(group) else 0.0
                platform_metrics.append({
                    "platform": platform_name,
                    "trend_count": int(len(group)),
                    "duplicate_rate": round(duplicate_rate, 2),
                    "missing_geo_rate": round(float(group["geo_missing"].mean() * 100), 2),
                    "missing_timestamp_rate": round(float(group["ts_missing"].mean() * 100), 2),
                    "last_seen": last_seen,
                    "stale_hours": None if stale_hours is None else round(stale_hours, 2),
                    "freshness_score": round(freshness_score, 2),
                    "source_confidence": round(_clamp(base_confidence), 2),
                    "scrape_error_count_7d": int(error_count),
                    "api_units_7d": round(float(usage_map.get(platform_name, {}).get("units", 0.0)), 2),
                    "api_requests_7d": int(request_count),
                })

        return {
            "generated_at": now.isoformat(),
            "total_trends": int(len(trends_df)) if isinstance(trends_df, pd.DataFrame) else 0,
            "duplicate_count": duplicates,
            "missing_geo_count": missing_geo,
            "missing_timestamp_count": missing_timestamp,
            "stale_platforms": [m["platform"] for m in platform_metrics if (m["stale_hours"] or 0) > FRESHNESS_WINDOW_HOURS],
            "platforms": platform_metrics,
        }

    def sync(self, session, now: datetime | None = None) -> dict[str, Any]:
        """Materialize clusters, signals, matches, insights, reports, and a backtest run."""
        now = now or datetime.utcnow()
        bind = session.get_bind()
        with Session(bind=bind) as read_session:
            monitoring = self.build_monitoring_snapshot(read_session, now=now)
            trends_df = self._load_recent_trends(read_session, now=now)
            if trends_df.empty:
                return {"clusters": 0, "signals": 0, "matches": 0, "reports": 0, "monitoring": monitoring}

            grouped_raw = self.analytics.group_topics(trends_df.copy())
            processed = self.analytics.process_trends(trends_df.copy())
            processed_map = {
                str(row["aggregated_topic"]): row.to_dict()
                for _, row in processed.iterrows()
            }
            platform_health = {metric["platform"]: metric for metric in monitoring.get("platforms", [])}
            ads = self._load_recent_ads(read_session, now=now)
            cluster_groups = list(grouped_raw.groupby("aggregated_topic"))

        cluster_count = 0
        signal_count = 0
        match_count = 0
        cluster_ids: list[int] = []

        with Session(bind=bind) as write_session:
            cluster_keys = [_slugify(str(aggregated_topic)) for aggregated_topic, _ in cluster_groups]
            existing_clusters = {
                cluster.cluster_key: cluster
                for cluster in write_session.query(TrendCluster).filter(TrendCluster.cluster_key.in_(cluster_keys)).all()
            }

            for aggregated_topic, group in cluster_groups:
                aggregated_data = processed_map.get(str(aggregated_topic))
                if not aggregated_data:
                    continue
                cluster_key = _slugify(str(aggregated_topic))
                cluster = self._upsert_cluster(
                    write_session,
                    aggregated_topic,
                    group,
                    aggregated_data,
                    platform_health,
                    now,
                    existing_cluster=existing_clusters.get(cluster_key),
                )
                existing_clusters[cluster.cluster_key] = cluster
                cluster_ids.append(cluster.id)
                cluster_count += 1
                signal_count += self._replace_signals(write_session, cluster, group, platform_health)
                matches, evidence = self._replace_matches(write_session, cluster, ads, now)
                match_count += len(matches)
                self._upsert_insight(write_session, cluster, aggregated_data, group, matches, evidence, now)

            reports = self._generate_reports(write_session, cluster_ids, now)
            self._run_backtest(write_session, cluster_ids, now)
            write_session.commit()

        return {
            "clusters": cluster_count,
            "signals": signal_count,
            "matches": match_count,
            "reports": len(reports),
            "monitoring": monitoring,
        }

    def _load_recent_trends(self, session, now: datetime) -> pd.DataFrame:
        rows = (
            session.query(
                Trend.id.label("trend_id"),
                Platform.name.label("platform"),
                Trend.topic,
                Trend.growth,
                Trend.keyword,
                Trend.geo,
                Trend.extracted_at,
                Trend.extra_data,
            )
            .join(Platform, Platform.id == Trend.platform_id)
            .filter(Trend.extracted_at >= now - timedelta(days=CLUSTER_LOOKBACK_DAYS))
            .all()
        )
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["trend_id", "platform", "topic", "growth", "keyword", "geo", "extracted_at", "extra_data"])
        df["extracted_at"] = pd.to_datetime(df["extracted_at"], errors="coerce")
        return df

    def _load_recent_ads(self, session, now: datetime) -> list[AdsInsight]:
        candidates = (
            session.query(AdsInsight)
            .options(load_only(
                AdsInsight.id,
                AdsInsight.search_keyword,
                AdsInsight.platform,
                AdsInsight.display_format,
                AdsInsight.title,
                AdsInsight.body,
                AdsInsight.cta_type,
                AdsInsight.start_date,
                AdsInsight.brand_name,
                AdsInsight.days_active,
                AdsInsight.performance_score,
                AdsInsight.performance_score_title,
                AdsInsight.share_url,
            ))
            .order_by(AdsInsight.id.desc())
            .limit(3000)
            .all()
        )
        cutoff = now - timedelta(days=90)
        recent_ads: list[AdsInsight] = []
        for ad in candidates:
            ad_date = _parse_date(ad.start_date)
            if ad_date is None or ad_date >= cutoff:
                recent_ads.append(ad)
            if len(recent_ads) >= 1500:
                break
        return recent_ads

    def _upsert_cluster(
        self,
        session,
        aggregated_topic: str,
        group: pd.DataFrame,
        aggregated: dict[str, Any],
        platform_health: dict[str, Any],
        now: datetime,
        existing_cluster: TrendCluster | None = None,
    ) -> TrendCluster:
        keywords = self._cluster_keywords(group, aggregated)
        platforms = sorted({str(value) for value in _safe_load_list(aggregated.get("platform")) if value})
        if not platforms:
            platforms = sorted({str(value) for value in group["platform"].dropna().tolist() if value})
        source_conf = self._cluster_source_confidence(platforms, platform_health)
        freshness_score = round(float(aggregated.get("freshness_factor", 0.0)) * 100.0, 2)
        quality_score = self._cluster_quality_score(group)
        trend_strength = round(_clamp(float(aggregated.get("virality_score", 0.0))), 2)
        lifecycle_stage = self._lifecycle_stage(
            trend_strength=trend_strength,
            freshness_score=freshness_score,
            momentum=float(aggregated.get("momentum", 0.0) or 0.0),
            diversity=int(aggregated.get("source_diversity", 1) or 1),
            surprise=float(aggregated.get("surprise", 0.0) or 0.0),
        )
        confidence_score = self._cluster_confidence(
            source_confidence=source_conf,
            freshness_score=freshness_score,
            quality_score=quality_score,
            diversity=int(aggregated.get("source_diversity", 1) or 1),
        )
        last_seen = pd.to_datetime(group["extracted_at"], errors="coerce").max()
        first_seen = pd.to_datetime(group["extracted_at"], errors="coerce").min()
        cluster_key = _slugify(str(aggregated_topic))
        existing = existing_cluster or session.query(TrendCluster).filter(TrendCluster.cluster_key == cluster_key).first()
        explanation = {
            "lifecycle_inputs": {
                "trend_strength": trend_strength,
                "freshness_score": freshness_score,
                "source_confidence": source_conf,
                "quality_score": quality_score,
                "source_diversity": int(aggregated.get("source_diversity", 1) or 1),
                "momentum": float(aggregated.get("momentum", 0.0) or 0.0),
                "surprise": float(aggregated.get("surprise", 0.0) or 0.0),
            }
        }
        fields = {
            "title": str(aggregated.get("topic") or aggregated_topic),
            "cluster_keywords": _safe_json(keywords),
            "platforms": _safe_json(platforms),
            "primary_platform": platforms[0] if platforms else None,
            "first_seen": first_seen.to_pydatetime() if pd.notna(first_seen) else now,
            "last_seen": last_seen.to_pydatetime() if pd.notna(last_seen) else now,
            "lifecycle_stage": lifecycle_stage,
            "confidence_score": confidence_score,
            "freshness_score": freshness_score,
            "source_confidence": source_conf,
            "trend_strength": trend_strength,
            "quality_score": quality_score,
            "source_count": len(platforms),
            "signal_count": int(len(group)),
            "geo_coverage": int(group["geo"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique()),
            "explanation_json": _safe_json(explanation),
            "updated_at": now,
        }
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            cluster = existing
        else:
            cluster = TrendCluster(cluster_key=cluster_key, created_at=now, **fields)
            session.add(cluster)
            session.flush()
        return cluster

    def _replace_signals(self, session, cluster: TrendCluster, group: pd.DataFrame, platform_health: dict[str, Any]) -> int:
        session.query(TrendSignal).filter(TrendSignal.cluster_id == cluster.id).delete()
        created = 0
        for _, row in group.iterrows():
            extra = self._parse_extra_data(row.get("extra_data"))
            health = platform_health.get(str(row.get("platform")), {})
            quality_flags = []
            if not row.get("geo"):
                quality_flags.append("missing_geo")
            if pd.isna(row.get("extracted_at")):
                quality_flags.append("missing_timestamp")
            signal = TrendSignal(
                cluster_id=cluster.id,
                source_trend_id=int(row["trend_id"]) if pd.notna(row.get("trend_id")) else None,
                platform=str(row.get("platform") or "Unknown"),
                topic=str(row.get("topic") or ""),
                keyword=str(row.get("keyword") or ""),
                geo=str(row.get("geo") or ""),
                signal_timestamp=_parse_date(row.get("extracted_at")) or datetime.utcnow(),
                volume=float(extra.get("search_volume") or extra.get("volume") or 1.0),
                growth=float(row.get("growth") or 0.0),
                engagement=float(extra.get("engagement") or extra.get("likes") or 0.0),
                sentiment=float(self.analytics.analyze_sentiment(row.get("topic") or row.get("keyword") or "")),
                freshness=float(health.get("freshness_score", 0.0)),
                source_confidence=float(health.get("source_confidence", cluster.source_confidence)),
                quality_flags=_safe_json(quality_flags),
            )
            session.add(signal)
            created += 1
        session.flush()
        return created

    def _replace_matches(self, session, cluster: TrendCluster, ads: list[AdsInsight], now: datetime) -> tuple[list[TrendAdMatch], dict[str, Any]]:
        session.query(TrendAdMatch).filter(TrendAdMatch.cluster_id == cluster.id).delete()

        cluster_keywords = _safe_load_list(cluster.cluster_keywords)
        cluster_text = " ".join([cluster.title] + [str(k) for k in cluster_keywords])
        cluster_tokens = _tokenize(cluster_text)
        cluster_last_seen = cluster.last_seen or now

        scored_ads: list[tuple[float, AdsInsight, dict[str, Any]]] = []
        for ad in ads:
            ad_text_parts = [ad.search_keyword, ad.title, ad.body, ad.brand_name, ad.cta_type, ad.display_format]
            ad_text = " ".join([str(part) for part in ad_text_parts if part])
            ad_tokens = _tokenize(ad_text)
            keyword_overlap = _token_jaccard(cluster_tokens, ad_tokens)
            semantic_similarity = _semantic_proxy_similarity(cluster_text, ad_text)
            brand_proximity = _token_jaccard(_tokenize(" ".join(cluster_keywords)), _tokenize(f"{ad.search_keyword or ''} {ad.brand_name or ''}"))
            timing_overlap = self._timing_overlap(cluster_last_seen, ad)
            match_score = _clamp(((keyword_overlap * 0.35) + (semantic_similarity * 0.30) + (timing_overlap * 0.20) + (brand_proximity * 0.15)) * 100.0)
            if match_score < (MIN_MATCH_SCORE * 100.0):
                continue
            scored_ads.append((match_score, ad, {
                "keyword_overlap": round(keyword_overlap, 3),
                "semantic_similarity": round(semantic_similarity, 3),
                "timing_overlap": round(timing_overlap, 3),
                "category_brand_proximity": round(brand_proximity, 3),
            }))

        scored_ads.sort(key=lambda item: item[0], reverse=True)
        brand_counter = Counter()
        cta_counter = Counter()
        format_counter = Counter()
        matches: list[TrendAdMatch] = []
        for score, ad, reason in scored_ads[:MAX_MATCHES_PER_CLUSTER]:
            match = TrendAdMatch(
                cluster_id=cluster.id,
                ads_insight_id=ad.id,
                match_score=round(score, 2),
                match_reason=_safe_json(reason),
                matched_at=now,
            )
            session.add(match)
            matches.append(match)
            if ad.brand_name:
                brand_counter[str(ad.brand_name)] += 1
            if ad.cta_type:
                cta_counter[str(ad.cta_type)] += 1
            if ad.display_format:
                format_counter[str(ad.display_format)] += 1
        session.flush()
        return matches, {
            "brands": brand_counter.most_common(5),
            "ctas": cta_counter.most_common(5),
            "formats": format_counter.most_common(5),
            "match_count": len(matches),
            "average_match_score": round(sum(m.match_score for m in matches) / len(matches), 2) if matches else 0.0,
        }

    def _upsert_insight(
        self,
        session,
        cluster: TrendCluster,
        aggregated: dict[str, Any],
        group: pd.DataFrame,
        matches: list[TrendAdMatch],
        evidence: dict[str, Any],
        now: datetime,
    ) -> TrendInsight:
        source_diversity = int(aggregated.get("source_diversity", 1) or 1)
        engagement = float(aggregated.get("engagement", 0.0) or 0.0)
        sentiment = float(aggregated.get("sentiment", 0.0) or 0.0)
        trend_strength = round(_clamp(float(aggregated.get("virality_score", cluster.trend_strength) or 0.0)), 2)
        commercial_relevance = self._commercial_relevance(matches, evidence)
        audience_signal = _clamp((min(engagement, 20000.0) / 200.0) + (abs(sentiment) * 25.0) + (source_diversity * 8.0))
        creative_reusability = self._creative_reusability(evidence)
        saturation_risk = self._saturation_risk(matches, evidence)
        brand_safety_risk = self._brand_safety_risk(cluster.title, cluster.cluster_keywords, sentiment)
        monetization_potential = _clamp((commercial_relevance * 0.6) + (trend_strength * 0.4))
        ad_opportunity_score = self._opportunity_score(
            trend_strength=trend_strength,
            commercial_relevance=commercial_relevance,
            audience_signal=audience_signal,
            creative_reusability=creative_reusability,
            saturation=saturation_risk,
            safety_risk=brand_safety_risk,
        )
        platform_fit = self._platform_fit(group, matches)
        audience_intent = self._audience_intent(cluster.title, evidence)
        creative_angles = self._creative_angles(cluster.title, cluster.cluster_keywords, evidence)
        timing_window = self._timing_window(cluster.lifecycle_stage, cluster.freshness_score)
        explanation = {
            "weights": INSIGHT_SCORE_WEIGHTS,
            "components": {
                "trend_strength": round(trend_strength, 2),
                "commercial_relevance": round(commercial_relevance, 2),
                "audience_signal": round(audience_signal, 2),
                "creative_reusability": round(creative_reusability, 2),
                "saturation": round(saturation_risk, 2),
                "safety_risk": round(brand_safety_risk, 2),
            },
            "evidence": {
                "linked_ads": len(matches),
                "brands": evidence.get("brands", []),
                "formats": evidence.get("formats", []),
                "ctas": evidence.get("ctas", []),
                "source_diversity": source_diversity,
                "freshness_score": cluster.freshness_score,
                "source_confidence": cluster.source_confidence,
            },
        }
        existing = session.query(TrendInsight).filter(TrendInsight.cluster_id == cluster.id).first()
        fields = {
            "ad_opportunity_score": round(ad_opportunity_score, 2),
            "trend_strength": trend_strength,
            "confidence_score": cluster.confidence_score,
            "audience_intent": audience_intent,
            "creative_angle_candidates": _safe_json(creative_angles),
            "platform_fit": _safe_json(platform_fit),
            "ad_timing_window": timing_window,
            "saturation_risk": round(saturation_risk, 2),
            "brand_safety_risk": round(brand_safety_risk, 2),
            "monetization_potential": round(monetization_potential, 2),
            "commercial_relevance": round(commercial_relevance, 2),
            "audience_signal": round(audience_signal, 2),
            "creative_reusability": round(creative_reusability, 2),
            "explanation_json": _safe_json(explanation),
            "updated_at": now,
        }
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            insight = existing
        else:
            insight = TrendInsight(cluster_id=cluster.id, created_at=now, **fields)
            session.add(insight)
        session.flush()
        return insight

    def _generate_reports(self, session, cluster_ids: list[int], now: datetime) -> list[ReportBrief]:
        recent_clusters = (
            session.query(TrendCluster, TrendInsight)
            .join(TrendInsight, TrendInsight.cluster_id == TrendCluster.id)
            .filter(TrendCluster.id.in_(cluster_ids))
            .order_by(TrendInsight.ad_opportunity_score.desc())
            .limit(12)
            .all()
        )
        if not recent_clusters:
            return []

        weekly_payload = {
            "generated_at": now.isoformat(),
            "clusters": [
                {
                    "cluster_id": cluster.id,
                    "title": cluster.title,
                    "stage": cluster.lifecycle_stage,
                    "score": insight.ad_opportunity_score,
                    "confidence": insight.confidence_score,
                }
                for cluster, insight in recent_clusters[:8]
            ],
        }
        deep_cluster, deep_insight = recent_clusters[0]
        deep_payload = {
            "cluster_id": deep_cluster.id,
            "title": deep_cluster.title,
            "score": deep_insight.ad_opportunity_score,
            "timing_window": deep_insight.ad_timing_window,
            "audience_intent": deep_insight.audience_intent,
            "creative_angles": _safe_load_list(deep_insight.creative_angle_candidates),
            "platform_fit": _safe_load_list(deep_insight.platform_fit),
            "explanation": json.loads(deep_insight.explanation_json or "{}"),
        }
        planning_payload = {
            "generated_at": now.isoformat(),
            "recommended_actions": [
                {
                    "cluster_id": cluster.id,
                    "title": cluster.title,
                    "action": f"Test {(_safe_load_list(insight.creative_angle_candidates) or ['a direct response hook'])[0]}",
                    "best_window": insight.ad_timing_window,
                    "risk": insight.brand_safety_risk,
                }
                for cluster, insight in recent_clusters[:5]
            ],
        }
        definitions = [
            ("weekly_digest", f"Weekly Trend Digest - {now:%Y-%m-%d}", weekly_payload, None),
            ("deep_dive", f"Deep Dive - {deep_cluster.title}", deep_payload, deep_cluster.id),
            ("planning_brief", f"Planning Brief - {now:%Y-%m-%d}", planning_payload, None),
        ]

        saved: list[ReportBrief] = []
        for report_type, title, payload, cluster_id in definitions:
            existing = session.query(ReportBrief).filter(ReportBrief.report_type == report_type, ReportBrief.title == title).first()
            if existing:
                existing.content_json = _safe_json(payload)
                existing.cluster_id = cluster_id
                existing.updated_at = now
                saved.append(existing)
                continue
            report = ReportBrief(
                report_type=report_type,
                title=title,
                cluster_id=cluster_id,
                content_json=_safe_json(payload),
                created_at=now,
                updated_at=now,
            )
            session.add(report)
            saved.append(report)
        session.flush()
        return saved

    def _run_backtest(self, session, cluster_ids: list[int], now: datetime) -> BacktestRun:
        insights = (
            session.query(TrendInsight, TrendCluster)
            .join(TrendCluster, TrendCluster.id == TrendInsight.cluster_id)
            .filter(TrendInsight.cluster_id.in_(cluster_ids))
            .all()
        )
        total = len(insights)
        positive_predictions = 0
        true_positive_proxy = 0
        matched_clusters = 0
        for insight, cluster in insights:
            match_count = session.query(func.count(TrendAdMatch.id)).filter(TrendAdMatch.cluster_id == cluster.id).scalar() or 0
            if match_count:
                matched_clusters += 1
            if insight.ad_opportunity_score >= 60:
                positive_predictions += 1
                if match_count >= 2 or cluster.lifecycle_stage in {"emerging", "surging"}:
                    true_positive_proxy += 1
        precision_proxy = (true_positive_proxy / positive_predictions) * 100 if positive_predictions else 0.0
        recall_proxy = (matched_clusters / total) * 100 if total else 0.0
        avg_score = sum(insight.ad_opportunity_score for insight, _ in insights) / total if total else 0.0
        run = BacktestRun(
            run_label=f"weekly-{now:%Y%m%d}",
            window_start=now - timedelta(days=7),
            window_end=now,
            total_clusters=total,
            matched_clusters=matched_clusters,
            avg_opportunity_score=round(avg_score, 2),
            precision_proxy=round(precision_proxy, 2),
            recall_proxy=round(recall_proxy, 2),
            summary_json=_safe_json({
                "method": "proxy",
                "positive_predictions": positive_predictions,
                "true_positive_proxy": true_positive_proxy,
            }),
            created_at=now,
        )
        session.add(run)
        session.flush()
        return run

    def _commercial_relevance(self, matches: list[TrendAdMatch], evidence: dict[str, Any]) -> float:
        match_count = len(matches)
        avg_match = sum(match.match_score for match in matches) / match_count if match_count else 0.0
        brand_count = len(evidence.get("brands", []))
        return _clamp((match_count * 6.0) + (avg_match * 0.5) + (brand_count * 8.0))

    def _creative_reusability(self, evidence: dict[str, Any]) -> float:
        cta_diversity = len(evidence.get("ctas", []))
        format_diversity = len(evidence.get("formats", []))
        avg_match_score = float(evidence.get("average_match_score", 0.0))
        return _clamp((cta_diversity * 15.0) + (format_diversity * 18.0) + (avg_match_score * 0.3))

    def _saturation_risk(self, matches: list[TrendAdMatch], evidence: dict[str, Any]) -> float:
        match_count = len(matches)
        brand_count = len(evidence.get("brands", []))
        return _clamp((match_count * 5.0) + (brand_count * 10.0))

    def _brand_safety_risk(self, title: str, keywords_json: str | None, sentiment: float) -> float:
        joined = " ".join([title] + [str(item) for item in _safe_load_list(keywords_json)])
        risk = 0.0
        for term in UNSAFE_TERMS:
            if term in joined.lower():
                risk += 18.0
        if sentiment < -0.35:
            risk += abs(sentiment) * 35.0
        return _clamp(risk)

    def _opportunity_score(
        self,
        trend_strength: float,
        commercial_relevance: float,
        audience_signal: float,
        creative_reusability: float,
        saturation: float,
        safety_risk: float,
    ) -> float:
        score = (
            (trend_strength * INSIGHT_SCORE_WEIGHTS["trend_strength"]) +
            (commercial_relevance * INSIGHT_SCORE_WEIGHTS["commercial_relevance"]) +
            (audience_signal * INSIGHT_SCORE_WEIGHTS["audience_signal"]) +
            (creative_reusability * INSIGHT_SCORE_WEIGHTS["creative_reusability"]) -
            (saturation * INSIGHT_SCORE_WEIGHTS["saturation"]) -
            (safety_risk * INSIGHT_SCORE_WEIGHTS["safety_risk"])
        )
        return _clamp(score)

    def _cluster_keywords(self, group: pd.DataFrame, aggregated: dict[str, Any]) -> list[str]:
        counter: Counter[str] = Counter()
        for raw in group["topic"].fillna("").tolist() + group["keyword"].fillna("").tolist():
            counter.update(_tokenize(raw))
        counter.update(_tokenize(aggregated.get("topic")))
        return [token for token, _ in counter.most_common(8)]

    def _cluster_source_confidence(self, platforms: list[str], platform_health: dict[str, Any]) -> float:
        if not platforms:
            return 0.0
        scores = [float(platform_health.get(platform, {}).get("source_confidence", 55.0)) for platform in platforms]
        return round(sum(scores) / len(scores), 2)

    def _cluster_quality_score(self, group: pd.DataFrame) -> float:
        if group.empty:
            return 0.0
        duplicate_penalty = float(group.duplicated(subset=["platform", "topic", "keyword", "geo", "extracted_at"]).mean() * 30.0)
        missing_geo_penalty = float((group["geo"].isna() | (group["geo"].astype(str).str.strip() == "")).mean() * 20.0)
        missing_ts_penalty = float(group["extracted_at"].isna().mean() * 30.0)
        return round(_clamp(100.0 - duplicate_penalty - missing_geo_penalty - missing_ts_penalty), 2)

    def _cluster_confidence(self, source_confidence: float, freshness_score: float, quality_score: float, diversity: int) -> float:
        return round(_clamp((source_confidence * 0.4) + (freshness_score * 0.25) + (quality_score * 0.2) + (min(diversity, 5) * 3.0)), 2)

    def _lifecycle_stage(self, trend_strength: float, freshness_score: float, momentum: float, diversity: int, surprise: float) -> str:
        if freshness_score < 30:
            return "cooling"
        if trend_strength >= 80 and momentum >= 0 and diversity >= 3:
            return "surging"
        if trend_strength >= 65 and freshness_score >= 60 and (momentum > 0 or surprise > 0.3):
            return "emerging"
        if trend_strength >= 45 and freshness_score >= 45:
            return "steady"
        return "watchlist"

    def _timing_overlap(self, cluster_last_seen: datetime, ad: AdsInsight) -> float:
        ad_date = _parse_date(ad.start_date) or _parse_date(ad.extracted_at)
        if ad_date is None:
            return 0.0
        delta_days = abs((cluster_last_seen - ad_date).days)
        return max(0.0, 1.0 - min(delta_days, 60) / 60.0)

    def _platform_fit(self, group: pd.DataFrame, matches: list[TrendAdMatch]) -> list[dict[str, Any]]:
        counts = Counter(str(value) for value in group["platform"].fillna("Unknown").tolist())
        ranked = []
        for platform, count in counts.most_common(5):
            ranked.append({
                "platform": platform,
                "supporting_signals": count,
                "linked_ads": len(matches),
                "fit_score": round(_clamp((count * 15.0) + (len(matches) * 4.0)), 2),
            })
        return ranked

    def _audience_intent(self, title: str, evidence: dict[str, Any]) -> str:
        ctas = [name for name, _ in evidence.get("ctas", [])]
        title_lower = title.lower()
        if any(cta in {"SHOP_NOW", "LEARN_MORE", "GET_OFFER"} for cta in ctas):
            return "High conversion intent with active commercial messaging."
        if "review" in title_lower or "vs" in title_lower or "best" in title_lower:
            return "Comparison and evaluation intent."
        if "how to" in title_lower or "guide" in title_lower:
            return "Research and education intent."
        return "Early interest formation with room for narrative and demand capture."

    def _creative_angles(self, title: str, keywords_json: str | None, evidence: dict[str, Any]) -> list[str]:
        keywords = [str(item) for item in _safe_load_list(keywords_json)[:3]]
        cta = evidence.get("ctas", [("LEARN_MORE", 0)])
        top_cta = cta[0][0].replace("_", " ") if cta else "LEARN MORE"
        return [
            f"Lead with the emerging hook around {keywords[0] if keywords else title}.",
            f"Show a concrete use case or transformation tied to {title}.",
            f"Use a {top_cta.lower()} call-to-action with proof-driven creative.",
        ]

    def _timing_window(self, lifecycle_stage: str, freshness_score: float) -> str:
        if lifecycle_stage == "surging":
            return "Act within 24-72 hours while cross-platform momentum is still compounding."
        if lifecycle_stage == "emerging":
            return "Test within the next 3-7 days before the market saturates."
        if lifecycle_stage == "steady":
            return "Can be folded into the next campaign cycle with moderate urgency."
        if freshness_score < 30:
            return "Low urgency. Use only for retrospective or evergreen positioning."
        return "Monitor and validate before allocating spend."

    @staticmethod
    def _parse_extra_data(raw: Any) -> dict[str, Any]:
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

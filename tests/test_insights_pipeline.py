"""Tests for deterministic insight scoring and lifecycle rules."""

from datetime import datetime

from src.insights.pipeline import InsightPipeline


def test_opportunity_score_rewards_strength_and_penalizes_risk():
    pipeline = InsightPipeline()
    high_signal = pipeline._opportunity_score(
        trend_strength=90,
        commercial_relevance=80,
        audience_signal=70,
        creative_reusability=60,
        saturation=10,
        safety_risk=5,
    )
    low_signal = pipeline._opportunity_score(
        trend_strength=40,
        commercial_relevance=25,
        audience_signal=20,
        creative_reusability=15,
        saturation=40,
        safety_risk=35,
    )
    assert high_signal > low_signal


def test_lifecycle_stage_rules():
    pipeline = InsightPipeline()
    assert pipeline._lifecycle_stage(85, 70, 1.0, 3, 0.5) == "surging"
    assert pipeline._lifecycle_stage(68, 65, 0.1, 2, 0.4) == "emerging"
    assert pipeline._lifecycle_stage(50, 50, -0.1, 2, 0.0) == "steady"
    assert pipeline._lifecycle_stage(20, 20, -1.0, 1, 0.0) == "cooling"


def test_brand_safety_risk_detects_unsafe_terms():
    pipeline = InsightPipeline()
    safe = pipeline._brand_safety_risk("Healthy snacks", '["snacks","wellness"]', 0.1)
    unsafe = pipeline._brand_safety_risk("Crypto scam controversy", '["crypto","scam"]', -0.6)
    assert unsafe > safe


def test_cluster_confidence_improves_with_better_inputs():
    pipeline = InsightPipeline()
    high = pipeline._cluster_confidence(source_confidence=85, freshness_score=80, quality_score=90, diversity=4)
    low = pipeline._cluster_confidence(source_confidence=40, freshness_score=20, quality_score=35, diversity=1)
    assert high > low


def test_recent_ads_loader_filters_in_python_and_keeps_recent_rows():
    pipeline = InsightPipeline()

    class DummyQuery:
        def __init__(self):
            self.ordered = None
            self.limit_value = None

        def filter(self, *_args, **_kwargs):
            return self

        def options(self, *_args, **_kwargs):
            return self

        def order_by(self, *args):
            self.ordered = args
            return self

        def limit(self, limit):
            self.limit_value = limit
            return self

        def all(self):
            return [
                type("Ad", (), {"id": 3, "start_date": "2026-04-10"})(),
                type("Ad", (), {"id": 2, "start_date": "2025-01-01"})(),
                type("Ad", (), {"id": 1, "start_date": None})(),
            ]

    class DummySession:
        def __init__(self):
            self.query_obj = DummyQuery()

        def query(self, _model):
            return self.query_obj

    session = DummySession()
    rows = pipeline._load_recent_ads(session, datetime(2026, 4, 14))

    assert session.query_obj.limit_value == 3000
    assert [row.id for row in rows] == [3, 1]

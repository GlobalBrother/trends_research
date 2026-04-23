"""Tests for src/api/main.py — FastAPI endpoints."""

import json
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

import pytest

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.db.models import Base, TrendCluster, TrendInsight, TrendSignal, AdsInsight, TrendAdMatch, ReportBrief, BacktestRun


@pytest.fixture
def client():
    return TestClient(app)


# ── root ──────────────────────────────────────────────────────────────────

class TestRoot:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)


# ── niches ────────────────────────────────────────────────────────────────

class TestNiches:
    def test_get_niches(self, client):
        resp = client.get("/niches")
        assert resp.status_code == 200
        niches = resp.json()
        assert isinstance(niches, list)
        assert "Survival" in niches

    def test_get_niche_keywords(self, client):
        resp = client.get("/niche_keywords/Survival")
        assert resp.status_code == 200
        data = resp.json()
        assert data["niche"] == "Survival"
        assert isinstance(data["keywords"], list)
        assert len(data["keywords"]) > 0

    def test_get_niche_keywords_unknown(self, client):
        resp = client.get("/niche_keywords/UnknownNiche")
        assert resp.status_code == 200
        data = resp.json()
        assert data["keywords"] == ["UnknownNiche"]


# ── trends ────────────────────────────────────────────────────────────────

class TestTrends:
    @patch("src.api.main.analytics")
    @patch("src.api.main.collector")
    def test_get_trends_empty(self, mock_collector, mock_analytics, client):
        mock_tc = MagicMock()
        mock_tc.collect_all.return_value = pd.DataFrame()
        mock_collector.collect_all = mock_tc.collect_all
        mock_analytics.process_trends.return_value = pd.DataFrame()

        resp = client.get("/trends")
        assert resp.status_code == 200

    @patch("src.api.main.analytics")
    @patch("src.api.main.collector")
    def test_get_all_trends(self, mock_collector, mock_analytics, client):
        mock_collector.collect_all.return_value = pd.DataFrame({
            'platform': ['Reddit'], 'topic': ['test'], 'growth': [100],
            'keyword': ['kw'], 'extracted_at': ['2025-01-01']
        })
        mock_analytics.process_trends.return_value = pd.DataFrame({
            'topic': ['test'], 'platform': [['Reddit']], 'virality_score': [55.0], 'keyword': ['kw'], 'extracted_at': [pd.Timestamp('2025-01-01')]
        })
        resp = client.get("/all_trends")
        assert resp.status_code == 200


# ── scrape_errors ─────────────────────────────────────────────────────────

class TestScrapeErrors:
    @patch("src.api.routes.scrape.collector")
    def test_get_scrape_errors(self, mock_collector, client):
        mock_collector.get_scrape_errors.return_value = pd.DataFrame(columns=['platform', 'keyword', 'url', 'status', 'reason', 'extracted_at'])
        resp = client.get("/scrape_errors")
        assert resp.status_code == 200


# ── scrape niche ──────────────────────────────────────────────────────────

class TestScrapeNiche:
    @patch("src.api.routes.scrape.collector")
    def test_scrape_niche_endpoint(self, mock_collector, client):
        mock_collector.run_niche_comprehensive_scrape = MagicMock(return_value=True)
        mock_collector.run_google_trends_scraper = MagicMock(return_value=True)
        mock_collector.run_social_trends_scraper = MagicMock(return_value=True)
        resp = client.post("/scrape", json={
            "niche": "Survival",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data or "status" in data


@pytest.fixture
def insight_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    @contextmanager
    def fake_session_scope():
        session = TestingSession()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr("src.api.routes.insights.session_scope", fake_session_scope)
    monkeypatch.setattr("src.api.routes.insights._ensure_cluster_snapshot", lambda force=False: {"refreshed": False})

    with fake_session_scope() as session:
        ad = AdsInsight(
            search_keyword="ai agents",
            platform="FACEBOOK",
            display_format="VIDEO",
            title="AI agent workflow ad",
            body="Automate ops with AI agents",
            cta_type="LEARN_MORE",
            performance_score=84,
            performance_score_title="winning",
            brand_name="AgentCo",
            days_active=12,
        )
        session.add(ad)
        session.flush()

        cluster = TrendCluster(
            cluster_key="ai-agents",
            title="AI agents",
            cluster_keywords='["ai","agents","automation"]',
            platforms='["Reddit","YouTube"]',
            primary_platform="Reddit",
            first_seen=pd.Timestamp("2026-04-01").to_pydatetime(),
            last_seen=pd.Timestamp("2026-04-08").to_pydatetime(),
            lifecycle_stage="emerging",
            confidence_score=82.0,
            freshness_score=76.0,
            source_confidence=79.0,
            trend_strength=88.0,
            quality_score=91.0,
            source_count=2,
            signal_count=3,
            geo_coverage=2,
            explanation_json='{"lifecycle_inputs":{"trend_strength":88}}',
        )
        session.add(cluster)
        session.flush()

        session.add(TrendInsight(
            cluster_id=cluster.id,
            ad_opportunity_score=74.0,
            trend_strength=88.0,
            confidence_score=82.0,
            audience_intent="High conversion intent with active commercial messaging.",
            creative_angle_candidates='["Lead with automation","Show ROI"]',
            platform_fit='[{"platform":"Reddit","supporting_signals":2,"linked_ads":1,"fit_score":34.0}]',
            ad_timing_window="Test within the next 3-7 days before the market saturates.",
            saturation_risk=18.0,
            brand_safety_risk=6.0,
            monetization_potential=80.0,
            commercial_relevance=60.0,
            audience_signal=70.0,
            creative_reusability=55.0,
            explanation_json='{"components":{"trend_strength":88,"commercial_relevance":60}}',
        ))
        session.add(TrendSignal(
            cluster_id=cluster.id,
            platform="Reddit",
            topic="AI agents are replacing workflows",
            keyword="ai agents",
            geo="US",
            signal_timestamp=pd.Timestamp("2026-04-08").to_pydatetime(),
            volume=10,
            growth=250,
            engagement=1000,
            sentiment=0.5,
            freshness=76,
            source_confidence=79,
            quality_flags='["ok"]',
        ))
        session.add(TrendAdMatch(
            cluster_id=cluster.id,
            ads_insight_id=ad.id,
            match_score=71.0,
            match_reason='{"keyword_overlap":0.8}',
            matched_at=pd.Timestamp("2026-04-08").to_pydatetime(),
        ))
        session.add(ReportBrief(
            report_type="weekly_digest",
            title="Weekly Trend Digest - 2026-04-08",
            cluster_id=cluster.id,
            content_json='{"clusters":[{"title":"AI agents"}]}',
        ))
        session.add(BacktestRun(
            run_label="weekly-20260408",
            total_clusters=1,
            matched_clusters=1,
            avg_opportunity_score=74.0,
            precision_proxy=100.0,
            recall_proxy=100.0,
            summary_json='{"method":"proxy"}',
        ))

    return TestingSession


class TestInsightEndpoints:
    def test_get_clusters(self, client, insight_db):
        resp = client.get("/clusters")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["title"] == "AI agents"
        assert data[0]["lifecycle_stage"] == "emerging"

    def test_cluster_detail_and_feedback(self, client, insight_db):
        detail = client.get("/clusters/1")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["insight"]["ad_opportunity_score"] == 74.0

        feedback = client.post("/clusters/1/feedback", json={"useful": True, "rating": 5, "used_in_campaign": False})
        assert feedback.status_code == 200
        assert feedback.json()["message"] == "Feedback recorded"

    def test_reports_and_backtests(self, client, insight_db):
        reports = client.get("/reports/generated")
        assert reports.status_code == 200
        assert reports.json()["data"][0]["report_type"] == "weekly_digest"

        backtests = client.get("/backtests")
        assert backtests.status_code == 200
        assert backtests.json()["data"][0]["precision_proxy"] == 100.0

"""Tests for src/api/main.py — FastAPI endpoints."""

import json
import pytest
from unittest.mock import patch, MagicMock

import pandas as pd
from fastapi.testclient import TestClient

from src.api.main import app


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
    @patch("src.api.main.TrendCollector")
    @patch("src.api.main.AnalyticsEngine")
    def test_get_trends_empty(self, mock_ae_cls, mock_tc_cls, client):
        mock_tc = MagicMock()
        mock_tc.collect_all.return_value = pd.DataFrame()
        mock_tc_cls.return_value = mock_tc
        mock_ae = MagicMock()
        mock_ae.process_trends.return_value = pd.DataFrame()
        mock_ae_cls.return_value = mock_ae

        resp = client.get("/trends")
        assert resp.status_code == 200

    @patch("src.api.main.TrendCollector")
    def test_get_all_trends(self, mock_tc_cls, client):
        mock_tc = MagicMock()
        mock_tc.collect_all.return_value = pd.DataFrame({
            'platform': ['Reddit'], 'topic': ['test'], 'growth': [100],
            'keyword': ['kw'], 'extracted_at': ['2025-01-01']
        })
        mock_tc_cls.return_value = mock_tc
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

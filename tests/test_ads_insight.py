"""Tests for src/scrapers/gethookedai/ads_insight.py — helper functions and API wrappers."""

import json
import os
import sqlite3

import pytest
from unittest.mock import patch, MagicMock

# We need to mock db_helper before importing ads_insight since it does
# `from db_helper import save_trend, save_error, DB_PATH` at module level.
import sys
sys.modules.setdefault("db_helper", MagicMock())

from src.scrapers.gethookedai import ads_insight


# ── _get_headers ──────────────────────────────────────────────────────────

class TestGetHeaders:
    @patch.dict(os.environ, {"GETHOOKEDAI_TOKEN": "test-token-123"})
    def test_returns_bearer(self):
        headers = ads_insight._get_headers()
        assert headers["Authorization"] == "Bearer test-token-123"

    @patch.dict(os.environ, {"GETHOOKEDAI_TOKEN": ""})
    def test_empty_token_raises(self):
        with pytest.raises(RuntimeError, match="GETHOOKEDAI_TOKEN"):
            ads_insight._get_headers()

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_token_raises(self):
        # Remove the key entirely
        os.environ.pop("GETHOOKEDAI_TOKEN", None)
        with pytest.raises(RuntimeError):
            ads_insight._get_headers()


# ── _handle_rate_limit ────────────────────────────────────────────────────

class TestHandleRateLimit:
    def test_429_returns_true(self):
        resp = MagicMock()
        resp.status_code = 429
        resp.headers = {"Retry-After": "0"}
        assert ads_insight._handle_rate_limit(resp) is True

    def test_200_returns_false(self):
        resp = MagicMock()
        resp.status_code = 200
        assert ads_insight._handle_rate_limit(resp) is False

    def test_500_returns_false(self):
        resp = MagicMock()
        resp.status_code = 500
        assert ads_insight._handle_rate_limit(resp) is False


# ── _handle_credits ───────────────────────────────────────────────────────

class TestHandleCredits:
    @patch("src.scrapers.gethookedai.ads_insight.save_error")
    def test_402_returns_true(self, mock_save):
        resp = MagicMock()
        resp.status_code = 402
        resp.url = "http://test"
        resp.json.return_value = {"data": {"credits_needed": 1.0, "remaining_credits": 0}}
        assert ads_insight._handle_credits(resp, "kw") is True
        mock_save.assert_called_once()

    def test_200_returns_false(self):
        resp = MagicMock()
        resp.status_code = 200
        assert ads_insight._handle_credits(resp) is False


# ── _save_ad ──────────────────────────────────────────────────────────────

class TestSaveAd:
    def _setup_test_db(self, tmp_path):
        """Create a temp SQLite DB with ads_insight table and patch the engine."""
        from sqlalchemy import create_engine
        db_file = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_file)
        conn.executescript(ads_insight._CREATE_ADS_INSIGHT)
        conn.close()
        engine = create_engine(f"sqlite:///{db_file}")
        return db_file, engine

    def test_save_and_read(self, tmp_path):
        db_file, engine = self._setup_test_db(tmp_path)

        ad = {
            "id": 1, "external_id": "ext1", "platform": "facebook",
            "display_format": "image", "title": "Test Ad", "body": "body text",
            "landing_page": "http://example.com", "link_description": "desc",
            "cta_type": "SHOP_NOW", "cta_text": "Shop", "start_date": "2025-01-01",
            "end_date": None, "days_active": 30, "active_in_library": 1,
            "performance_score": 85, "performance_score_title": "winning",
            "used_count": 5, "is_aaa_eligible": 0,
            "age_audience_min": 18, "age_audience_max": 65,
            "gender_audience": "all", "eu_total_reach": 50000,
            "ad_spend_range_score": 3, "ad_spend_range_score_title": "medium",
            "share_url": "http://share",
            "brand": {"external_id": "b1", "name": "TestBrand", "logo_url": "http://logo", "active_ads": 10},
            "media": [{"url": "http://media"}],
            "ad_cards": [],
        }

        with patch.object(ads_insight, "_engine", engine), \
             patch("src.scrapers.gethookedai.ads_insight.is_sqlite", return_value=True), \
             patch("src.db.sql_compat.is_sqlite", return_value=True):
            ads_insight._save_ad(ad, "test_keyword")

        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM ads_insight WHERE hookd_id = 1").fetchone()
        conn.close()

        assert row is not None
        assert row["title"] == "Test Ad"
        assert row["brand_name"] == "TestBrand"
        assert row["search_keyword"] == "test_keyword"
        assert json.loads(row["media"]) == [{"url": "http://media"}]

    def test_save_minimal_ad(self, tmp_path):
        db_file, engine = self._setup_test_db(tmp_path)

        ad = {"id": 99}
        with patch.object(ads_insight, "_engine", engine), \
             patch("src.scrapers.gethookedai.ads_insight.is_sqlite", return_value=True), \
             patch("src.db.sql_compat.is_sqlite", return_value=True):
            ads_insight._save_ad(ad, "kw")

        conn = sqlite3.connect(db_file)
        row = conn.execute("SELECT * FROM ads_insight WHERE hookd_id = 99").fetchone()
        conn.close()
        assert row is not None


# ── scrape_ads ────────────────────────────────────────────────────────────

class TestScrapeAds:
    @patch("src.scrapers.gethookedai.ads_insight.requests.get")
    @patch("src.scrapers.gethookedai.ads_insight._get_headers", return_value={"Authorization": "Bearer x"})
    @patch("src.scrapers.gethookedai.ads_insight._ensure_table")
    @patch("src.scrapers.gethookedai.ads_insight._save_ad")
    @patch("src.scrapers.gethookedai.ads_insight.save_trend")
    def test_scrape_single_page(self, mock_save_trend, mock_save_ad, mock_ensure, mock_headers, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "data": [{"id": 1, "title": "Ad1", "brand": {"name": "B"}, "performance_score": 80, "share_url": "http://x"}],
            "meta": {"last_page": 1},
            "remaining_credits": 100,
        }
        mock_get.return_value = resp

        ads_insight.scrape_ads(["test_kw"], max_pages=1)
        mock_save_ad.assert_called_once()
        mock_save_trend.assert_called_once()

    @patch("src.scrapers.gethookedai.ads_insight.requests.get")
    @patch("src.scrapers.gethookedai.ads_insight._get_headers", return_value={"Authorization": "Bearer x"})
    @patch("src.scrapers.gethookedai.ads_insight._ensure_table")
    def test_scrape_empty_results(self, mock_ensure, mock_headers, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": [], "meta": {"last_page": 1}}
        mock_get.return_value = resp

        ads_insight.scrape_ads(["empty_kw"], max_pages=1)
        # Should not crash

    @patch("src.scrapers.gethookedai.ads_insight.requests.get")
    @patch("src.scrapers.gethookedai.ads_insight._get_headers", return_value={"Authorization": "Bearer x"})
    @patch("src.scrapers.gethookedai.ads_insight._ensure_table")
    @patch("src.scrapers.gethookedai.ads_insight.save_error")
    def test_scrape_credits_exhausted(self, mock_save_error, mock_ensure, mock_headers, mock_get):
        resp = MagicMock()
        resp.status_code = 402
        resp.url = "http://test"
        resp.json.return_value = {"data": {"credits_needed": 1, "remaining_credits": 0}}
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        ads_insight.scrape_ads(["kw"], max_pages=1)
        mock_save_error.assert_called()


# ── search_brands ─────────────────────────────────────────────────────────

class TestSearchBrands:
    @patch("src.scrapers.gethookedai.ads_insight.requests.get")
    @patch("src.scrapers.gethookedai.ads_insight._get_headers", return_value={"Authorization": "Bearer x"})
    def test_deduplicates_brands(self, mock_headers, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "data": [
                {"brand": {"external_id": "e1", "name": "BrandA", "logo_url": "", "active_ads": 5}},
                {"brand": {"external_id": "e1", "name": "BrandA", "logo_url": "", "active_ads": 5}},
                {"brand": {"external_id": "e2", "name": "BrandB", "logo_url": "", "active_ads": 3}},
            ]
        }
        mock_get.return_value = resp

        brands = ads_insight.search_brands("test")
        assert len(brands) == 2
        names = [b["name"] for b in brands]
        assert "BrandA" in names
        assert "BrandB" in names

    @patch("src.scrapers.gethookedai.ads_insight.requests.get")
    @patch("src.scrapers.gethookedai.ads_insight._get_headers", return_value={"Authorization": "Bearer x"})
    def test_empty_results(self, mock_headers, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": []}
        mock_get.return_value = resp

        brands = ads_insight.search_brands("nonexistent")
        assert brands == []

    @patch("src.scrapers.gethookedai.ads_insight.requests.get")
    @patch("src.scrapers.gethookedai.ads_insight._get_headers", return_value={"Authorization": "Bearer x"})
    def test_ads_without_brand(self, mock_headers, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": [{"brand": None}, {"brand": {}}]}
        mock_get.return_value = resp

        brands = ads_insight.search_brands("test")
        assert brands == []

"""Tests for src/collector/trend_collector.py — TrendCollector class."""

import json
import os
import sqlite3
import tempfile

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from src.collector.trend_collector import TrendCollector


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite DB with the trends schema."""
    db_file = str(tmp_path / "test_trends.db")
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT, topic TEXT, growth REAL,
            keyword TEXT, geo TEXT,
            extracted_at TEXT, extra_data TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE scrape_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT, keyword TEXT, url TEXT,
            status INTEGER, reason TEXT, extracted_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    return db_file


@pytest.fixture
def collector(tmp_db):
    tc = TrendCollector()
    tc.db_path = tmp_db
    return tc


def _insert_trend(db_path, platform, topic, growth=0, keyword="test", geo="US", extra_data=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO trends (platform, topic, growth, keyword, geo, extracted_at, extra_data) VALUES (?,?,?,?,?,?,?)",
        (platform, topic, growth, keyword, geo, "2025-01-01T00:00:00", json.dumps(extra_data or {}))
    )
    conn.commit()
    conn.close()


# ── get_db_trends ─────────────────────────────────────────────────────────

class TestGetDbTrends:
    def test_empty_db(self, collector):
        trends = collector.get_db_trends()
        assert trends == []

    def test_returns_google_always_included(self, collector, tmp_db):
        _insert_trend(tmp_db, "Google Interest", "bitcoin")
        trends = collector.get_db_trends()
        assert len(trends) == 1
        assert trends[0]['platform'] == 'Google Interest'

    def test_platform_filtering(self, collector, tmp_db):
        _insert_trend(tmp_db, "YouTube", "video topic")
        _insert_trend(tmp_db, "Reddit", "reddit topic")
        # Without include flags, only always-included platforms returned
        trends = collector.get_db_trends()
        assert len(trends) == 0
        # With YouTube flag
        trends = collector.get_db_trends(include_youtube=True)
        assert len(trends) == 1
        assert trends[0]['platform'] == 'YouTube'

    def test_include_multiple_platforms(self, collector, tmp_db):
        _insert_trend(tmp_db, "YouTube", "yt")
        _insert_trend(tmp_db, "Reddit", "rd")
        _insert_trend(tmp_db, "HackerNews", "hn")
        trends = collector.get_db_trends(include_youtube=True, include_reddit=True, include_hackernews=True)
        assert len(trends) == 3

    def test_geo_filtering_specific(self, collector, tmp_db):
        _insert_trend(tmp_db, "Google Interest", "topic1", geo="US")
        _insert_trend(tmp_db, "Google Interest", "topic2", geo="UK")
        trends = collector.get_db_trends(geo="US")
        topics = [t['topic'] for t in trends]
        assert "topic1" in topics
        assert "topic2" not in topics

    def test_geo_global_includes_empty(self, collector, tmp_db):
        _insert_trend(tmp_db, "Google Interest", "global_topic", geo="")
        _insert_trend(tmp_db, "Google Interest", "us_topic", geo="US")
        trends = collector.get_db_trends(geo="Global")
        topics = [t['topic'] for t in trends]
        assert "global_topic" in topics
        assert "us_topic" not in topics

    def test_extra_data_expanded(self, collector, tmp_db):
        _insert_trend(tmp_db, "Google Interest", "topic", extra_data={"score": 42, "author": "test"})
        trends = collector.get_db_trends()
        assert trends[0]['score'] == 42
        assert trends[0]['author'] == 'test'

    def test_invalid_extra_data_ignored(self, collector, tmp_db):
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            "INSERT INTO trends (platform, topic, growth, keyword, geo, extracted_at, extra_data) VALUES (?,?,?,?,?,?,?)",
            ("Google Interest", "topic", 0, "kw", "US", "2025-01-01", "not-json{{{")
        )
        conn.commit()
        conn.close()
        trends = collector.get_db_trends()
        assert len(trends) == 1

    def test_db_not_found(self, collector):
        collector.db_path = "/nonexistent/path/db.sqlite"
        trends = collector.get_db_trends()
        assert trends == []


# ── collect_all ───────────────────────────────────────────────────────────

class TestCollectAll:
    def test_returns_dataframe(self, collector, tmp_db):
        _insert_trend(tmp_db, "Google Interest", "topic1")
        result = collector.collect_all()
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1

    def test_empty_returns_empty_df(self, collector):
        result = collector.collect_all()
        assert isinstance(result, pd.DataFrame)
        assert result.empty
        assert 'platform' in result.columns

    def test_passes_filters(self, collector, tmp_db):
        _insert_trend(tmp_db, "Reddit", "rd")
        result = collector.collect_all(include_reddit=True)
        assert len(result) == 1


# ── _run_scraper ──────────────────────────────────────────────────────────

class TestRunScraper:
    @patch("src.collector.trend_collector.subprocess.run")
    def test_success(self, mock_run, collector):
        mock_run.return_value = MagicMock(returncode=0)
        assert collector.run_google_trends_scraper(["bitcoin"]) is True

    @patch("src.collector.trend_collector.subprocess.run")
    def test_failure(self, mock_run, collector):
        mock_run.return_value = MagicMock(returncode=1)
        assert collector.run_google_trends_scraper(["bitcoin"]) is False

    @patch("src.collector.trend_collector.subprocess.run", side_effect=Exception("boom"))
    def test_exception(self, mock_run, collector):
        assert collector.run_google_trends_scraper(["bitcoin"]) is False

    @patch("src.collector.trend_collector.subprocess.run")
    def test_keywords_joined(self, mock_run, collector):
        mock_run.return_value = MagicMock(returncode=0)
        collector.run_google_trends_scraper(["a", "b", "c"])
        cmd = mock_run.call_args[0][0]
        # keywords should be comma-joined
        assert "a,b,c" in " ".join(cmd)


# ── run_social_trends_scraper ─────────────────────────────────────────────

class TestRunSocialScraper:
    def test_unknown_platform(self, collector):
        result = collector.run_social_trends_scraper("UnknownPlatform", ["kw"])
        assert result is False

    @patch.dict(os.environ, {"ENSEMBLEDATA_TOKEN": ""})
    def test_no_token_skips(self, collector):
        result = collector.run_social_trends_scraper("TikTok", ["kw"])
        assert result is False


# ── get_scrape_errors ─────────────────────────────────────────────────────

class TestGetScrapeErrors:
    def test_empty(self, collector):
        result = collector.get_scrape_errors()
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_with_errors(self, collector, tmp_db):
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            "INSERT INTO scrape_errors (platform, keyword, url, status, reason, extracted_at) VALUES (?,?,?,?,?,?)",
            ("Reddit", "kw", "http://x", 500, "timeout", "2025-01-01")
        )
        conn.commit()
        conn.close()
        result = collector.get_scrape_errors()
        assert len(result) == 1

    def test_filter_by_platform(self, collector, tmp_db):
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            "INSERT INTO scrape_errors (platform, keyword, url, status, reason, extracted_at) VALUES (?,?,?,?,?,?)",
            ("Reddit", "kw", "http://x", 500, "err", "2025-01-01")
        )
        conn.execute(
            "INSERT INTO scrape_errors (platform, keyword, url, status, reason, extracted_at) VALUES (?,?,?,?,?,?)",
            ("YouTube", "kw", "http://y", 403, "err", "2025-01-01")
        )
        conn.commit()
        conn.close()
        result = collector.get_scrape_errors(platform="Reddit")
        assert len(result) == 1
        assert result.iloc[0]['platform'] == 'Reddit'

    def test_db_error_returns_empty(self, collector):
        collector.db_path = "/nonexistent/db.sqlite"
        result = collector.get_scrape_errors()
        assert isinstance(result, pd.DataFrame)
        assert result.empty

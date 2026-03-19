"""Tests for src/collector/trend_collector.py — TrendCollector class.

Note: These tests use a temporary SQLite database to test the ORM layer
in isolation. The production app uses Azure SQL, but SQLAlchemy's ORM
abstraction allows us to validate logic against SQLite for speed and
simplicity. The `get_session` function is patched to use the temp DB.
"""

import json
import os
import tempfile
from datetime import datetime

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, Platform, Trend, ScrapeError as ScrapeErrorModel
from src.collector.trend_collector import TrendCollector


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite DB with the ORM schema and return (db_file, session_factory)."""
    db_file = str(tmp_path / "test_trends.db")
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine)
    return db_file, sf


@pytest.fixture
def collector(tmp_db):
    db_file, sf = tmp_db
    tc = TrendCollector()
    # Patch get_session so the collector uses our temp DB
    with patch("src.collector.trend_collector.get_session", side_effect=sf):
        yield tc


def _insert_trend(session_factory, platform_name, topic, growth=0, keyword="test", geo="US", extra_data=None):
    session = session_factory()
    plat = session.query(Platform).filter(Platform.name == platform_name).first()
    if not plat:
        plat = Platform(name=platform_name)
        session.add(plat)
        session.flush()
    session.add(Trend(
        platform_id=plat.id, topic=topic, growth=growth,
        keyword=keyword, geo=geo, extracted_at=datetime(2025, 1, 1),
        extra_data=json.dumps(extra_data or {}),
    ))
    session.commit()
    session.close()


def _insert_error(session_factory, platform, keyword, url, status, reason):
    session = session_factory()
    session.add(ScrapeErrorModel(
        platform=platform, keyword=keyword, url=url,
        status=status, reason=reason, extracted_at=datetime(2025, 1, 1),
    ))
    session.commit()
    session.close()


# ── get_db_trends ─────────────────────────────────────────────────────────

class TestGetDbTrends:
    def test_empty_db(self, collector, tmp_db):
        _, sf = tmp_db
        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            trends = collector.get_db_trends()
        assert trends == []

    def test_returns_google_always_included(self, collector, tmp_db):
        _, sf = tmp_db
        _insert_trend(sf, "Google Interest", "bitcoin")
        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            trends = collector.get_db_trends()
        assert len(trends) == 1
        assert trends[0]['platform'] == 'Google Interest'

    def test_platform_filtering(self, collector, tmp_db):
        _, sf = tmp_db
        _insert_trend(sf, "YouTube", "video topic")
        _insert_trend(sf, "Reddit", "reddit topic")
        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            # Without include flags, only always-included platforms returned
            trends = collector.get_db_trends()
            assert len(trends) == 0
            # With YouTube flag
            trends = collector.get_db_trends(include_youtube=True)
            assert len(trends) == 1
            assert trends[0]['platform'] == 'YouTube'

    def test_include_multiple_platforms(self, collector, tmp_db):
        _, sf = tmp_db
        _insert_trend(sf, "YouTube", "yt")
        _insert_trend(sf, "Reddit", "rd")
        _insert_trend(sf, "HackerNews", "hn")
        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            trends = collector.get_db_trends(include_youtube=True, include_reddit=True, include_hackernews=True)
        assert len(trends) == 3

    def test_geo_filtering_specific(self, collector, tmp_db):
        _, sf = tmp_db
        _insert_trend(sf, "Google Interest", "topic1", geo="US")
        _insert_trend(sf, "Google Interest", "topic2", geo="UK")
        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            trends = collector.get_db_trends(geo="US")
        topics = [t['topic'] for t in trends]
        assert "topic1" in topics
        assert "topic2" not in topics

    def test_geo_global_includes_empty(self, collector, tmp_db):
        _, sf = tmp_db
        _insert_trend(sf, "Google Interest", "global_topic", geo="")
        _insert_trend(sf, "Google Interest", "us_topic", geo="US")
        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            trends = collector.get_db_trends(geo="Global")
        topics = [t['topic'] for t in trends]
        assert "global_topic" in topics
        assert "us_topic" not in topics

    def test_extra_data_expanded(self, collector, tmp_db):
        _, sf = tmp_db
        _insert_trend(sf, "Google Interest", "topic", extra_data={"score": 42, "author": "test"})
        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            trends = collector.get_db_trends()
        assert trends[0]['score'] == 42
        assert trends[0]['author'] == 'test'

    def test_invalid_extra_data_ignored(self, collector, tmp_db):
        _, sf = tmp_db
        # Insert with invalid JSON extra_data
        session = sf()
        plat = Platform(name="Google Interest")
        session.add(plat)
        session.flush()
        session.add(Trend(
            platform_id=plat.id, topic="topic", growth=0,
            keyword="test", geo="US", extracted_at=datetime(2025, 1, 1),
            extra_data="not-json{{{",
        ))
        session.commit()
        session.close()

        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            trends = collector.get_db_trends()
        assert len(trends) == 1
        assert 'topic' in trends[0]['topic']

    def test_db_not_found(self, collector):
        # When session raises, should return empty list
        def bad_session():
            raise Exception("DB not found")
        with patch("src.collector.trend_collector.get_session", side_effect=bad_session):
            trends = collector.get_db_trends()
        assert trends == []


# ── collect_all ───────────────────────────────────────────────────────────

class TestCollectAll:
    def test_returns_dataframe(self, collector, tmp_db):
        _, sf = tmp_db
        _insert_trend(sf, "Google Interest", "topic1")
        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            df = collector.collect_all()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1

    def test_empty_returns_empty_df(self, collector, tmp_db):
        _, sf = tmp_db
        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            df = collector.collect_all()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert 'platform' in df.columns

    def test_passes_filters(self, collector, tmp_db):
        _, sf = tmp_db
        _insert_trend(sf, "YouTube", "yt")
        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            df = collector.collect_all(include_youtube=True)
        assert len(df) == 1


# ── _run_scraper ──────────────────────────────────────────────────────────

@patch("subprocess.run")
class TestRunScraper:
    def test_success(self, mock_run, collector):
        mock_run.return_value = MagicMock(returncode=0)
        assert collector.run_google_trends_scraper(["kw"]) is True

    def test_failure(self, mock_run, collector):
        mock_run.return_value = MagicMock(returncode=1)
        assert collector.run_google_trends_scraper(["kw"]) is False

    def test_exception(self, mock_run, collector):
        mock_run.side_effect = Exception("boom")
        assert collector.run_google_trends_scraper(["kw"]) is False

    def test_keywords_joined(self, mock_run, collector):
        mock_run.return_value = MagicMock(returncode=0)
        collector.run_google_trends_scraper(["a", "b", "c"])
        call_args = mock_run.call_args[0][0]
        # Keywords should be joined with comma
        kw_arg_idx = call_args.index("-a") + 1
        # Find the keywords=... argument
        kw_args = [a for a in call_args if a.startswith("keywords=")]
        assert len(kw_args) == 1
        assert kw_args[0] == "keywords=a,b,c"


# ── run_social_trends_scraper ─────────────────────────────────────────────

class TestRunSocialScraper:
    def test_unknown_platform(self, collector):
        assert collector.run_social_trends_scraper("UnknownPlatform", ["kw"]) is False

    @patch.dict(os.environ, {"ENSEMBLEDATA_TOKEN": ""})
    def test_no_token_skips(self, collector):
        result = collector.run_social_trends_scraper("TikTok", ["kw"])
        assert result is False


# ── get_scrape_errors ─────────────────────────────────────────────────────

class TestGetScrapeErrors:
    def test_empty(self, collector, tmp_db):
        _, sf = tmp_db
        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            df = collector.get_scrape_errors()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_with_errors(self, collector, tmp_db):
        _, sf = tmp_db
        _insert_error(sf, "TestPlatform", "kw1", "http://test", 429, "rate limited")
        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            df = collector.get_scrape_errors()
        assert len(df) == 1
        assert df.iloc[0]['platform'] == 'TestPlatform'
        assert df.iloc[0]['status'] == 429

    def test_filter_by_platform(self, collector, tmp_db):
        _, sf = tmp_db
        _insert_error(sf, "PlatA", "kw1", "http://a", 500, "error")
        _insert_error(sf, "PlatB", "kw2", "http://b", 403, "forbidden")
        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            df = collector.get_scrape_errors(platform="PlatA")
        assert len(df) == 1
        assert df.iloc[0]['platform'] == 'PlatA'

        with patch("src.collector.trend_collector.get_session", side_effect=sf):
            df_all = collector.get_scrape_errors()
        assert len(df_all) == 2

    def test_db_error_returns_empty(self, collector):
        def bad_session():
            raise Exception("DB error")
        with patch("src.collector.trend_collector.get_session", side_effect=bad_session):
            df = collector.get_scrape_errors()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

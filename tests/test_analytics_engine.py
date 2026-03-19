"""Tests for src/analytics/analytics_engine.py — AnalyticsEngine class."""

import pandas as pd
import numpy as np
import pytest

from src.analytics.analytics_engine import AnalyticsEngine


@pytest.fixture
def engine():
    return AnalyticsEngine()


# ── analyze_sentiment ─────────────────────────────────────────────────────

class TestAnalyzeSentiment:
    def test_positive_text(self, engine):
        score = engine.analyze_sentiment("This is absolutely wonderful and amazing!")
        assert score > 0

    def test_negative_text(self, engine):
        score = engine.analyze_sentiment("This is terrible and awful!")
        assert score < 0

    def test_neutral_text(self, engine):
        score = engine.analyze_sentiment("The meeting is at 3pm.")
        assert -0.3 <= score <= 0.3

    def test_empty_string(self, engine):
        score = engine.analyze_sentiment("")
        assert score == 0.0

    def test_none_input(self, engine):
        # str(None) == "None" — should not crash
        score = engine.analyze_sentiment(None)
        assert isinstance(score, float)

    def test_numeric_input(self, engine):
        score = engine.analyze_sentiment(12345)
        assert isinstance(score, float)

    def test_score_range(self, engine):
        score = engine.analyze_sentiment("Great product, love it!")
        assert -1.0 <= score <= 1.0


# ── calculate_virality_score ──────────────────────────────────────────────

class TestCalculateViralityScore:
    def test_basic_score(self, engine):
        score = engine.calculate_virality_score(growth_rate=500, engagement=1000)
        assert 1 <= score <= 100

    def test_zero_growth(self, engine):
        score = engine.calculate_virality_score(growth_rate=0)
        assert 1 <= score <= 100

    def test_negative_growth_clamped(self, engine):
        score = engine.calculate_virality_score(growth_rate=-2)
        # growth_rate <= -1 is reset to 0
        assert 1 <= score <= 100

    def test_nan_growth(self, engine):
        score = engine.calculate_virality_score(growth_rate=float('nan'))
        assert 1 <= score <= 100

    def test_high_growth_caps(self, engine):
        score = engine.calculate_virality_score(growth_rate=999999)
        assert score <= 100

    def test_spread_bonus(self, engine):
        without_spread = engine.calculate_virality_score(growth_rate=500, spread=0)
        with_spread = engine.calculate_virality_score(growth_rate=500, spread=100)
        assert with_spread > without_spread

    def test_sentiment_bonus(self, engine):
        neutral = engine.calculate_virality_score(growth_rate=500, sentiment=0)
        positive = engine.calculate_virality_score(growth_rate=500, sentiment=0.9)
        assert positive > neutral

    def test_source_diversity_impact(self, engine):
        low = engine.calculate_virality_score(growth_rate=500, source_diversity=1)
        high = engine.calculate_virality_score(growth_rate=500, source_diversity=5)
        assert high > low

    def test_volume_impact(self, engine):
        low = engine.calculate_virality_score(growth_rate=500, volume=1)
        high = engine.calculate_virality_score(growth_rate=500, volume=100)
        assert high > low

    def test_return_type(self, engine):
        score = engine.calculate_virality_score(growth_rate=100)
        assert isinstance(score, float)


# ── group_topics ──────────────────────────────────────────────────────────

class TestGroupTopics:
    def test_empty_dataframe(self, engine):
        df = pd.DataFrame(columns=['topic', 'platform'])
        result = engine.group_topics(df)
        assert 'aggregated_topic' in result.columns
        assert len(result) == 0

    def test_single_row(self, engine):
        df = pd.DataFrame({'topic': ['AI trends'], 'platform': ['Reddit']})
        result = engine.group_topics(df)
        assert result['aggregated_topic'].iloc[0] == 'AI trends'

    def test_similar_topics_grouped(self, engine):
        df = pd.DataFrame({
            'topic': ['machine learning trends', 'machine learning news', 'unrelated cooking recipe'],
            'platform': ['Reddit', 'HackerNews', 'YouTube']
        })
        result = engine.group_topics(df)
        # The two ML topics should share the same aggregated_topic
        ml_groups = result[result['topic'].str.contains('machine learning')]['aggregated_topic'].unique()
        assert len(ml_groups) == 1

    def test_different_topics_not_grouped(self, engine):
        df = pd.DataFrame({
            'topic': ['quantum computing breakthrough', 'chocolate cake recipe'],
            'platform': ['Reddit', 'YouTube']
        })
        result = engine.group_topics(df)
        assert result['aggregated_topic'].iloc[0] != result['aggregated_topic'].iloc[1]

    def test_meta_platforms_exact_match(self, engine):
        df = pd.DataFrame({
            'topic': ['bitcoin', 'bitcoin', 'ethereum'],
            'platform': ['Google Interest', 'Google Regions', 'Reddit']
        })
        result = engine.group_topics(df)
        # The two Google meta entries for "bitcoin" should be grouped
        bitcoin_rows = result[result['topic'] == 'bitcoin']
        assert bitcoin_rows['aggregated_topic'].nunique() == 1

    def test_preserves_original_columns(self, engine):
        df = pd.DataFrame({
            'topic': ['topic A', 'topic B'],
            'platform': ['Reddit', 'YouTube'],
            'extra_col': [1, 2]
        })
        result = engine.group_topics(df)
        assert 'extra_col' in result.columns


# ── process_trends ────────────────────────────────────────────────────────

class TestProcessTrends:
    def _make_df(self, n=5):
        return pd.DataFrame({
            'topic': [f'topic {i}' for i in range(n)],
            'platform': ['Reddit'] * n,
            'growth': [100 * i for i in range(n)],
            'keyword': ['test'] * n,
            'geo': ['US'] * n,
            'extracted_at': ['2025-01-01'] * n,
        })

    def test_empty_dataframe(self, engine):
        df = pd.DataFrame()
        result = engine.process_trends(df)
        assert result.empty

    def test_adds_expected_columns(self, engine):
        df = self._make_df()
        result = engine.process_trends(df)
        for col in ['sentiment', 'virality_score', 'source_diversity', 'volume', 'aggregated_topic']:
            assert col in result.columns

    def test_sorted_by_virality(self, engine):
        df = self._make_df(10)
        result = engine.process_trends(df)
        scores = result['virality_score'].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_engagement_created_when_missing(self, engine):
        df = self._make_df(3)
        result = engine.process_trends(df)
        assert 'engagement' in result.columns

    def test_spread_column_added_before_aggregation(self, engine):
        df = self._make_df(3)
        # spread is used internally for virality calculation but may be
        # dropped during the final groupby aggregation — just verify no crash
        result = engine.process_trends(df)
        assert 'virality_score' in result.columns

    def test_with_existing_engagement(self, engine):
        df = self._make_df(3)
        df['engagement'] = [10, 20, 30]
        result = engine.process_trends(df)
        assert 'engagement' in result.columns


# ── cluster_threshold ─────────────────────────────────────────────────────

class TestClusterThreshold:
    def test_custom_threshold(self):
        engine = AnalyticsEngine(cluster_threshold=0.5)
        assert engine.cluster_threshold == 0.5

    def test_default_threshold(self):
        engine = AnalyticsEngine()
        assert engine.cluster_threshold == 0.7

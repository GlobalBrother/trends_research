"""Tests for src/niche/niche_discovery.py — NicheDiscovery class."""

import pandas as pd
import pytest

from src.niche.niche_discovery import NicheDiscovery


@pytest.fixture
def nd():
    return NicheDiscovery()


# ── get_available_niches ──────────────────────────────────────────────────

class TestGetAvailableNiches:
    def test_returns_list(self, nd):
        niches = nd.get_available_niches()
        assert isinstance(niches, list)

    def test_contains_expected_niches(self, nd):
        niches = nd.get_available_niches()
        for name in ["Survival", "Health", "Preppers", "Sustainability", "Homesteading"]:
            assert name in niches

    def test_count(self, nd):
        assert len(nd.get_available_niches()) == 5


# ── get_niche_keywords ────────────────────────────────────────────────────

class TestGetNicheKeywords:
    def test_known_niche(self, nd):
        kws = nd.get_niche_keywords("Survival")
        assert isinstance(kws, list)
        assert len(kws) > 0
        assert "Bushcraft" in kws

    def test_unknown_niche_returns_name(self, nd):
        kws = nd.get_niche_keywords("NonExistentNiche")
        assert kws == ["NonExistentNiche"]

    def test_all_niches_have_keywords(self, nd):
        for niche in nd.get_available_niches():
            kws = nd.get_niche_keywords(niche)
            assert len(kws) >= 5


# ── filter_by_niche ──────────────────────────────────────────────────────

class TestFilterByNiche:
    def _make_df(self):
        return pd.DataFrame({
            'topic': [
                'Survival skills for beginners',
                'Best chocolate cake recipe',
                'Emergency preparedness guide',
                'Minecraft survival mode tips',
                'Bushcraft knife review',
            ],
            'keyword': ['survival', 'cooking', 'emergency', 'gaming', 'bushcraft'],
            'platform': ['Reddit'] * 5,
        })

    def test_empty_df_returns_empty(self, nd):
        df = pd.DataFrame(columns=['topic', 'keyword', 'platform'])
        result = nd.filter_by_niche(df, "Survival")
        assert result.empty

    def test_none_keyword_returns_all(self, nd):
        df = self._make_df()
        result = nd.filter_by_niche(df, None)
        assert len(result) == len(df)

    def test_all_keyword_returns_all(self, nd):
        df = self._make_df()
        result = nd.filter_by_niche(df, "All")
        assert len(result) == len(df)

    def test_survival_includes_relevant(self, nd):
        df = self._make_df()
        result = nd.filter_by_niche(df, "Survival")
        topics = result['topic'].tolist()
        assert any('Survival skills' in t for t in topics)
        assert any('Bushcraft' in t for t in topics)

    def test_survival_excludes_gaming(self, nd):
        df = self._make_df()
        result = nd.filter_by_niche(df, "Survival")
        topics = result['topic'].tolist()
        assert not any('Minecraft' in t for t in topics)

    def test_unknown_niche_filters_by_name(self, nd):
        df = pd.DataFrame({
            'topic': ['crypto trading', 'bitcoin news', 'cooking tips'],
            'keyword': ['crypto', 'crypto', 'food'],
            'platform': ['Reddit'] * 3,
        })
        result = nd.filter_by_niche(df, "crypto")
        assert len(result) >= 1
        assert all('crypto' in t.lower() or 'crypto' in k.lower()
                    for t, k in zip(result['topic'], result['keyword']))

    def test_health_niche(self, nd):
        df = pd.DataFrame({
            'topic': ['Herbal wellness tips', 'Pharmacy stocks rising', 'Natural remedy guide'],
            'keyword': ['health', 'pharma', 'health'],
            'platform': ['Reddit'] * 3,
        })
        result = nd.filter_by_niche(df, "Health")
        topics = result['topic'].tolist()
        assert any('Herbal' in t for t in topics)
        # "Pharmacy" should be excluded
        assert not any('Pharmacy' in t for t in topics)


# ── discover_micro_niches ─────────────────────────────────────────────────

class TestDiscoverMicroNiches:
    def test_empty_df(self, nd):
        df = pd.DataFrame(columns=['topic'])
        result = nd.discover_micro_niches(df)
        assert result.empty

    def test_too_few_rows(self, nd):
        df = pd.DataFrame({'topic': ['one', 'two']})
        result = nd.discover_micro_niches(df)
        # Should return df as-is (fewer rows than n_clusters)
        assert len(result) == 2
        assert 'niche_cluster' not in result.columns

    def test_clustering_adds_column(self):
        nd = NicheDiscovery(n_clusters=2)
        df = pd.DataFrame({
            'topic': [
                'solar energy panels', 'wind power turbines', 'renewable energy',
                'chocolate cake', 'baking bread', 'cooking pasta',
            ]
        })
        result = nd.discover_micro_niches(df)
        assert 'niche_cluster' in result.columns
        assert result['niche_cluster'].nunique() == 2

    def test_custom_n_clusters(self):
        nd = NicheDiscovery(n_clusters=3)
        assert nd.n_clusters == 3

    def test_does_not_modify_original(self, nd):
        df = pd.DataFrame({'topic': ['a', 'b', 'c', 'd', 'e', 'f']})
        original_cols = list(df.columns)
        nd.discover_micro_niches(df)
        assert list(df.columns) == original_cols

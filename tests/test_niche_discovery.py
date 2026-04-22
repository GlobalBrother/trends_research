"""Tests for src/niche/niche_discovery.py — NicheDiscovery class."""

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.niche.niche_discovery import NicheDiscovery, NICHE_SEED_KEYWORDS
from src.db.models import Base, Niche
from src.db.sql_compat import (
    insert_niche_if_not_exists,
    seed_niches,
    reset_niches_to_defaults,
)


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


# ── seeding & user-edit ownership (is_seed flag) ─────────────────────────

@pytest.fixture
def db_session():
    """In-memory SQLite session with the niches table created from the ORM."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _expected_seed_count():
    return sum(len(v) for v in NICHE_SEED_KEYWORDS.values())


class TestNicheSeeding:
    def test_seeding_is_idempotent(self, db_session):
        first = seed_niches(db_session)
        db_session.commit()
        assert first == _expected_seed_count()
        assert db_session.query(Niche).count() == first

        # A second seed pass must insert nothing and must not modify rows.
        second = seed_niches(db_session)
        db_session.commit()
        assert second == 0
        assert db_session.query(Niche).count() == first
        # All seed-owned rows remain flagged correctly.
        assert db_session.query(Niche).filter(Niche.is_seed == True).count() == first  # noqa: E712

    def test_user_created_niche_survives_reseed(self, db_session):
        seed_niches(db_session)
        db_session.commit()

        # Simulate a user creating a fresh niche via the POST endpoint.
        insert_niche_if_not_exists(
            db_session, "MyCustomNiche", "custom keyword", is_seed=False
        )
        db_session.commit()

        user_row = db_session.query(Niche).filter(
            Niche.niche_name == "MyCustomNiche",
            Niche.keyword == "custom keyword",
        ).one()
        assert user_row.is_seed is False or user_row.is_seed == 0

        # Re-running the seeder must not delete or update the user row.
        seed_niches(db_session)
        db_session.commit()

        still_there = db_session.query(Niche).filter(
            Niche.niche_name == "MyCustomNiche",
            Niche.keyword == "custom keyword",
        ).one()
        assert still_there.id == user_row.id
        assert still_there.is_seed is False or still_there.is_seed == 0

    def test_reset_defaults_restores_seeds_without_touching_user_rows(self, db_session):
        seed_niches(db_session)
        # User-owned row that must survive
        insert_niche_if_not_exists(
            db_session, "MyCustomNiche", "custom keyword", is_seed=False
        )
        # User edit on a niche that ALSO has the same name as a seed niche:
        # the user added their own keyword under "Survival".
        insert_niche_if_not_exists(
            db_session, "Survival", "user-added survival kw", is_seed=False
        )
        db_session.commit()

        # Wipe a seed row to prove reset_defaults restores it.
        deleted = db_session.query(Niche).filter(
            Niche.niche_name == "Survival",
            Niche.keyword == "Bushcraft",
        ).delete()
        db_session.commit()
        assert deleted == 1

        stats = reset_niches_to_defaults(db_session)
        db_session.commit()

        # The previously-deleted seed keyword is back.
        restored = db_session.query(Niche).filter(
            Niche.niche_name == "Survival",
            Niche.keyword == "Bushcraft",
        ).one()
        assert restored.is_seed is True or restored.is_seed == 1

        # User-created niche is still there and still user-owned.
        user_row = db_session.query(Niche).filter(
            Niche.niche_name == "MyCustomNiche",
            Niche.keyword == "custom keyword",
        ).one()
        assert user_row.is_seed is False or user_row.is_seed == 0

        # User-added keyword on a seed niche is still there and still user-owned.
        user_kw = db_session.query(Niche).filter(
            Niche.niche_name == "Survival",
            Niche.keyword == "user-added survival kw",
        ).one()
        assert user_kw.is_seed is False or user_kw.is_seed == 0

        # Seed/user totals reconcile.
        seed_count = db_session.query(Niche).filter(Niche.is_seed == True).count()  # noqa: E712
        user_count = db_session.query(Niche).filter(Niche.is_seed == False).count()  # noqa: E712
        assert seed_count == _expected_seed_count()
        assert user_count == 2
        assert stats["inserted"] >= 1  # at minimum the wiped seed row


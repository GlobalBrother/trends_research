"""
Analytics engine for trend data processing.

Calculates virality scores, groups similar topics using Union-Find clustering,
and performs sentiment analysis on collected trends.
"""

import logging
import re
from typing import Optional

import numpy as np
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from src.config import PLATFORM_WEIGHTS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CLUSTER_THRESHOLD = 0.7
VIRALITY_SCORE_MIN = 1.0
VIRALITY_SCORE_MAX = 100.0
SIGMOID_STEEPNESS = 0.25
SIGMOID_MIDPOINT = 12
MAX_NORMALIZED_GROWTH = 10
GROWTH_NORMALIZATION_FACTOR = 500
ENGAGEMENT_SCALE = 2.0
DIVERSITY_WEIGHT = 1.5
PLATFORM_WEIGHT_MULTIPLIER = 2.0
SENTIMENT_BONUS_SCALE = 0.5
SPREAD_BONUS_SCALE = 0.5
MIN_KEYWORD_LENGTH = 3
MIN_KEYWORDS_FOR_STRONG_MATCH = 2

STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "with", "for",
    "is", "are", "was", "were", "why", "how", "what", "to", "of", "my",
    "your", "our", "show", "hn", "app", "apps",
})


META_PLATFORMS = frozenset({"Google Interest", "Google Regions"})

# Columns that may or may not exist in the DataFrame
OPTIONAL_AGG_COLUMNS = (
    "url", "published", "posts", "replies", "subreddit", "source", "author",
)


class AnalyticsEngine:
    """Processes trend DataFrames: sentiment, virality scoring, and topic clustering."""

    def __init__(self, cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD) -> None:
        self.analyzer = self._init_sentiment_analyzer()
        self.cluster_threshold = cluster_threshold

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _init_sentiment_analyzer() -> SentimentIntensityAnalyzer:
        """Initialise the VADER sentiment analyser with a fallback download."""
        try:
            return SentimentIntensityAnalyzer()
        except Exception:
            import nltk
            nltk.download("vader_lexicon", quiet=True)
            return SentimentIntensityAnalyzer()

    # ------------------------------------------------------------------
    # Sentiment
    # ------------------------------------------------------------------

    def analyze_sentiment(self, text: str) -> float:
        """Return the VADER compound sentiment score for *text*."""
        return self.analyzer.polarity_scores(str(text))["compound"]

    # ------------------------------------------------------------------
    # Virality score
    # ------------------------------------------------------------------

    @staticmethod
    def _sigmoid(x: float) -> float:
        """Sigmoid function used to scale the virality score to [0, 1]."""
        return 1.0 / (1.0 + np.exp(-SIGMOID_STEEPNESS * (x - SIGMOID_MIDPOINT)))

    def calculate_virality_score(
        self,
        growth_rate: float,
        engagement: float = 1.0,
        platform_weight: float = 1.0,
        sentiment: float = 0.0,
        spread: int = 0,
        source_diversity: int = 1,
        volume: int = 1,
    ) -> float:
        """Calculate a custom virality score scaled to 1–100.

        Formula: log(mentions) + 2 * growth_rate + engagement_weight + source_diversity
        """
        if pd.isna(growth_rate) or growth_rate <= -1:
            growth_rate = 0.0

        log_mentions = np.log1p(volume)
        norm_growth = min(MAX_NORMALIZED_GROWTH, growth_rate / GROWTH_NORMALIZATION_FACTOR)
        engagement_weight = np.log1p(max(0, engagement)) / ENGAGEMENT_SCALE
        diversity_weight = source_diversity * DIVERSITY_WEIGHT

        base_score = (
            log_mentions
            + (2 * norm_growth)
            + engagement_weight
            + diversity_weight
            + (platform_weight * PLATFORM_WEIGHT_MULTIPLIER)
        )

        # Sentiment bonus (absolute value — strong sentiment in either direction)
        base_score += abs(sentiment) * SENTIMENT_BONUS_SCALE

        # Geographical spread bonus
        if spread > 0:
            base_score += np.log1p(spread) * SPREAD_BONUS_SCALE

        scaled_score = VIRALITY_SCORE_MIN + (self._sigmoid(base_score) * (VIRALITY_SCORE_MAX - VIRALITY_SCORE_MIN))
        return round(scaled_score, 2)

    # ------------------------------------------------------------------
    # Topic grouping (Union-Find)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_keywords(text: str) -> set[str]:
        """Extract meaningful keywords from a topic string."""
        cleaned = re.sub(r"[^\w\s]", "", text.lower())
        words = set(cleaned.split())
        return {w for w in words if w not in STOP_WORDS and len(w) >= MIN_KEYWORD_LENGTH}

    def group_topics(self, df: pd.DataFrame) -> pd.DataFrame:
        """Group similar topics using keyword overlap and Union-Find clustering."""
        if df.empty or len(df) < 2:
            df["aggregated_topic"] = df["topic"]
            return df

        df = df.copy()
        topics = df["topic"].tolist()
        topic_keywords = [self._extract_keywords(t) for t in topics]
        topic_lower = [t.strip().lower() for t in topics]
        is_meta = [
            df.iloc[i]["platform"] in META_PLATFORMS for i in range(len(topics))
        ]

        parent, rank = self._init_union_find(len(topics))

        # Build inverted index: keyword → list of topic indices (non-meta only)
        keyword_to_indices: dict[str, list[int]] = {}
        for i, kws in enumerate(topic_keywords):
            if not is_meta[i]:
                for kw in kws:
                    keyword_to_indices.setdefault(kw, []).append(i)

        # Group exact-match meta topics
        self._union_exact_meta(topics, topic_lower, is_meta, parent, rank)

        # Union non-meta topics sharing keywords
        self._union_by_keyword_overlap(
            topic_keywords, topic_lower, keyword_to_indices, parent, rank,
        )

        # Build aggregated topic mapping
        aggregated_map = self._build_aggregated_map(topics, parent)
        df["aggregated_topic"] = [aggregated_map.get(i, topics[i]) for i in range(len(topics))]
        return df

    # --- Union-Find primitives ---

    @staticmethod
    def _init_union_find(n: int) -> tuple[list[int], list[int]]:
        return list(range(n)), [0] * n

    @staticmethod
    def _find(parent: list[int], i: int) -> int:
        root = i
        while parent[root] != root:
            root = parent[root]
        # Path compression
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    @staticmethod
    def _union(parent: list[int], rank: list[int], i: int, j: int) -> None:
        ri, rj = AnalyticsEngine._find(parent, i), AnalyticsEngine._find(parent, j)
        if ri == rj:
            return
        if rank[ri] < rank[rj]:
            parent[ri] = rj
        elif rank[ri] > rank[rj]:
            parent[rj] = ri
        else:
            parent[ri] = rj
            rank[rj] += 1

    # --- Grouping sub-steps ---

    @staticmethod
    def _union_exact_meta(
        topics: list[str],
        topic_lower: list[str],
        is_meta: list[bool],
        parent: list[int],
        rank: list[int],
    ) -> None:
        exact_groups: dict[str, int] = {}
        for i in range(len(topics)):
            if is_meta[i]:
                key = topic_lower[i]
                if key in exact_groups:
                    AnalyticsEngine._union(parent, rank, i, exact_groups[key])
                else:
                    exact_groups[key] = i

    @staticmethod
    def _union_by_keyword_overlap(
        topic_keywords: list[set[str]],
        topic_lower: list[str],
        keyword_to_indices: dict[str, list[int]],
        parent: list[int],
        rank: list[int],
    ) -> None:
        checked_pairs: set[tuple[int, int]] = set()
        for indices in keyword_to_indices.values():
            for idx_a in range(len(indices)):
                i = indices[idx_a]
                for idx_b in range(idx_a + 1, len(indices)):
                    j = indices[idx_b]
                    pair = (min(i, j), max(i, j))
                    if pair in checked_pairs:
                        continue
                    checked_pairs.add(pair)

                    intersection = topic_keywords[i] & topic_keywords[j]
                    if not intersection:
                        continue

                    min_len = min(len(topic_keywords[i]), len(topic_keywords[j]))
                    match = (
                        len(intersection) >= MIN_KEYWORDS_FOR_STRONG_MATCH
                        or (len(intersection) >= 1 and min_len <= 2 and topic_lower[i] == topic_lower[j])
                    )
                    if match:
                        AnalyticsEngine._union(parent, rank, i, j)

    @staticmethod
    def _build_aggregated_map(topics: list[str], parent: list[int]) -> dict[int, str]:
        group_to_indices: dict[int, list[int]] = {}
        for i in range(len(topics)):
            root = AnalyticsEngine._find(parent, i)
            group_to_indices.setdefault(root, []).append(i)

        aggregated_map: dict[int, str] = {}
        for indices in group_to_indices.values():
            rep_idx = min(indices, key=lambda x: len(topics[x]))
            rep_topic = topics[rep_idx]
            for idx in indices:
                aggregated_map[idx] = rep_topic
        return aggregated_map

    # ------------------------------------------------------------------
    # Main processing pipeline
    # ------------------------------------------------------------------

    def process_trends(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply full analytics pipeline to a DataFrame of collected trends."""
        if df.empty:
            return df

        # 1. Topic aggregation (clustering)
        df = self.group_topics(df)

        # 2. Sentiment analysis
        df.loc[:, "sentiment"] = df["topic"].apply(self.analyze_sentiment)

        # 3. Engagement handling
        if "engagement" not in df.columns:
            df.loc[:, "engagement"] = 1000.0 + (df["growth"].fillna(0) * 2)

        # 4. Source diversity and volume
        diversity_map = df.groupby("aggregated_topic")["platform"].nunique().to_dict()
        df.loc[:, "source_diversity"] = df["aggregated_topic"].map(diversity_map)

        volume_map = df.groupby("aggregated_topic")["topic"].count().to_dict()
        df.loc[:, "volume"] = df["aggregated_topic"].map(volume_map)

        # 5. Ensure 'spread' column exists
        if "spread" not in df.columns:
            df.loc[:, "spread"] = 0

        # 6. Calculate virality score
        df.loc[:, "virality_score"] = df.apply(
            lambda row: self.calculate_virality_score(
                growth_rate=row.get("growth", 0),
                engagement=row.get("engagement", 0),
                platform_weight=PLATFORM_WEIGHTS.get(row.get("platform"), 1.0),
                sentiment=row.get("sentiment", 0),
                spread=row.get("spread", 0),
                source_diversity=row.get("source_diversity", 1),
                volume=row.get("volume", 1),
            ),
            axis=1,
        )

        # 7. Aggregate results by aggregated_topic
        aggregated_results = self._aggregate_results(df)
        return aggregated_results.sort_values(by="virality_score", ascending=False)

    @staticmethod
    def _aggregate_results(df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate trend rows by ``aggregated_topic``."""
        agg_dict: dict = {
            "virality_score": "max",
            "growth": "max",
            "engagement": "max",
            "sentiment": "mean",
            "platform": lambda x: list(set(x)),
            "source_diversity": "first",
            "volume": "first",
            "topic": "first",
            "geo": lambda x: list({str(v) for v in x if v}),
            "keyword": "first",
            "extracted_at": "max",
        }

        for col in OPTIONAL_AGG_COLUMNS:
            if col in df.columns:
                agg_dict[col] = lambda x: next(
                    (v for v in x if v and v != "N/A"), x.iloc[0]
                )

        return df.groupby("aggregated_topic").agg(agg_dict).reset_index()

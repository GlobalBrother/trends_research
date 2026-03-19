"""
AnalyticsEngine — sentiment analysis, virality scoring, and topic clustering.

Key responsibilities:
  1. Compute VADER-based sentiment for each topic.
  2. Calculate a composite Virality Score (1-100 scale).
  3. Group similar topics across platforms using Union-Find keyword overlap.
  4. Aggregate per-topic metrics for a unified view.
"""

import logging
import re
from typing import Optional

import nltk
import numpy as np
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from src.config import PLATFORM_WEIGHTS

logger = logging.getLogger(__name__)

# Common stop words used in topic keyword extraction
_STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "with",
    "for", "is", "are", "was", "were", "why", "how", "what", "to",
    "of", "my", "your", "our", "show", "hn", "app", "apps",
})


class AnalyticsEngine:
    """Processes raw trend DataFrames into scored, clustered, aggregated results."""

    def __init__(self, cluster_threshold: float = 0.7):
        self.cluster_threshold = cluster_threshold
        self._init_sentiment_analyzer()

    # ------------------------------------------------------------------
    # Initialization helpers
    # ------------------------------------------------------------------

    def _init_sentiment_analyzer(self) -> None:
        try:
            self.analyzer = SentimentIntensityAnalyzer()
        except Exception:
            nltk.download("vader_lexicon", quiet=True)
            self.analyzer = SentimentIntensityAnalyzer()

    # ------------------------------------------------------------------
    # Sentiment
    # ------------------------------------------------------------------

    def analyze_sentiment(self, text: str) -> float:
        """Return the VADER compound sentiment score for *text*."""
        return self.analyzer.polarity_scores(str(text))["compound"]

    # ------------------------------------------------------------------
    # Virality Score
    # ------------------------------------------------------------------

    @staticmethod
    def _sigmoid(x: float) -> float:
        return 1.0 / (1.0 + np.exp(-0.25 * (x - 12)))

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
        """
        Composite virality score scaled to 1-100.

        Formula:
            base = log(volume) + 2*norm_growth + engagement_weight
                   + diversity_boost + platform_boost + sentiment_bonus + spread_bonus
            score = 1 + sigmoid(base) * 99
        """
        if pd.isna(growth_rate) or growth_rate <= -1:
            growth_rate = 0.0

        log_mentions = np.log1p(volume)
        norm_growth = min(10.0, growth_rate / 500.0)
        engagement_weight = np.log1p(max(0.0, engagement)) / 2.0
        diversity_weight = source_diversity * 1.5

        base_score = (
            log_mentions
            + 2.0 * norm_growth
            + engagement_weight
            + diversity_weight
            + platform_weight * 2.0
        )

        # Sentiment bonus (absolute value — both strong positive and negative are viral)
        base_score += abs(sentiment) * 0.5

        # Geographic spread bonus
        if spread > 0:
            base_score += np.log1p(spread) * 0.5

        return round(1.0 + self._sigmoid(base_score) * 99.0, 2)

    # ------------------------------------------------------------------
    # Topic grouping (Union-Find)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_keywords(text: str) -> set[str]:
        """Lowercase, strip punctuation, remove stop words, keep tokens len > 2."""
        cleaned = re.sub(r"[^\w\s]", "", text.lower())
        return {w for w in cleaned.split() if w not in _STOP_WORDS and len(w) > 2}

    def group_topics(self, df: pd.DataFrame) -> pd.DataFrame:
        """Cluster similar topics using keyword overlap + Union-Find."""
        if df.empty or len(df) < 2:
            df["aggregated_topic"] = df["topic"]
            return df

        df = df.copy()
        topics = df["topic"].tolist()
        topic_keywords = [self._extract_keywords(t) for t in topics]
        topic_lower = [t.strip().lower() for t in topics]
        is_meta = [
            df.iloc[i]["platform"] in ("Google Interest", "Google Regions")
            for i in range(len(topics))
        ]

        n = len(topics)
        parent = list(range(n))
        rank = [0] * n

        def find(i: int) -> int:
            root = i
            while parent[root] != root:
                root = parent[root]
            while parent[i] != root:
                parent[i], i = root, parent[i]
            return root

        def union(i: int, j: int) -> None:
            ri, rj = find(i), find(j)
            if ri == rj:
                return
            if rank[ri] < rank[rj]:
                parent[ri] = rj
            elif rank[ri] > rank[rj]:
                parent[rj] = ri
            else:
                parent[ri] = rj
                rank[rj] += 1

        # Exact-match grouping for meta-platform rows
        exact_groups: dict[str, int] = {}
        for i in range(n):
            if is_meta[i]:
                key = topic_lower[i]
                if key in exact_groups:
                    union(i, exact_groups[key])
                else:
                    exact_groups[key] = i

        # Inverted index for non-meta topics
        keyword_to_indices: dict[str, list[int]] = {}
        for i, kws in enumerate(topic_keywords):
            if not is_meta[i]:
                for kw in kws:
                    keyword_to_indices.setdefault(kw, []).append(i)

        checked_pairs: set[tuple[int, int]] = set()
        for indices in keyword_to_indices.values():
            for a_idx in range(len(indices)):
                i = indices[a_idx]
                for b_idx in range(a_idx + 1, len(indices)):
                    j = indices[b_idx]
                    pair = (min(i, j), max(i, j))
                    if pair in checked_pairs:
                        continue
                    checked_pairs.add(pair)

                    intersection = topic_keywords[i] & topic_keywords[j]
                    if not intersection:
                        continue
                    min_len = min(len(topic_keywords[i]), len(topic_keywords[j]))

                    if len(intersection) >= 2:
                        union(i, j)
                    elif len(intersection) >= 1 and min_len <= 2 and topic_lower[i] == topic_lower[j]:
                        union(i, j)

        # Build representative mapping (shortest title per group)
        group_to_indices: dict[int, list[int]] = {}
        for i in range(n):
            group_to_indices.setdefault(find(i), []).append(i)

        aggregated_map: dict[int, str] = {}
        for root, idxs in group_to_indices.items():
            rep_idx = min(idxs, key=lambda x: len(topics[x]))
            for idx in idxs:
                aggregated_map[idx] = topics[rep_idx]

        df["aggregated_topic"] = [aggregated_map.get(i, topics[i]) for i in range(n)]
        return df

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def process_trends(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run the complete analytics pipeline on a raw trends DataFrame."""
        if df.empty:
            return df

        # 1. Topic clustering
        df = self.group_topics(df)

        # 2. Sentiment
        df.loc[:, "sentiment"] = df["topic"].apply(self.analyze_sentiment)

        # 3. Engagement fallback
        if "engagement" not in df.columns:
            df.loc[:, "engagement"] = 1000.0 + df["growth"].fillna(0) * 2

        # 4. Source diversity & volume
        diversity_map = df.groupby("aggregated_topic")["platform"].nunique().to_dict()
        volume_map = df.groupby("aggregated_topic")["topic"].count().to_dict()
        df.loc[:, "source_diversity"] = df["aggregated_topic"].map(diversity_map)
        df.loc[:, "volume"] = df["aggregated_topic"].map(volume_map)

        # 5. Spread fallback
        if "spread" not in df.columns:
            df.loc[:, "spread"] = 0

        # 6. Virality score
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

        # 7. Aggregate to one row per aggregated_topic
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

        optional_cols = ["url", "published", "posts", "replies", "subreddit", "source", "author"]
        for col in optional_cols:
            if col in df.columns:
                agg_dict[col] = lambda x: next((v for v in x if v and v != "N/A"), x.iloc[0])

        aggregated = df.groupby("aggregated_topic").agg(agg_dict).reset_index()
        return aggregated.sort_values("virality_score", ascending=False)

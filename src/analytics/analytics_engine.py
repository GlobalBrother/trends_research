import pandas as pd
from textblob import TextBlob
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import numpy as np
import nltk
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re

class AnalyticsEngine:
    def __init__(self, cluster_threshold=0.7):
        try:
            # Ensure VADER lexicon is available if using nltk version, 
            # though vaderSentiment package usually includes it.
            # Using vaderSentiment package directly here as in original code.
            self.analyzer = SentimentIntensityAnalyzer()
        except Exception:
            # Fallback/Initialization if needed
            nltk.download('vader_lexicon', quiet=True)
            self.analyzer = SentimentIntensityAnalyzer()
        self.cluster_threshold = cluster_threshold

    def analyze_sentiment(self, text):
        """Analyzes sentiment using VADER."""
        scores = self.analyzer.polarity_scores(str(text))
        return scores['compound']

    def calculate_virality_score(self, growth_rate, engagement=1.0, platform_weight=1.0, sentiment=0.0, spread=0, source_diversity=1, volume=1):
        """Calculates a custom Virality Score based on growth, engagement, platform weight, sentiment and geographical spread.
        
        Formula from plan: ViralScore = log(mentions) + 2 * growth_rate + engagement_weight + source_diversity
        Simplified implementation for robust scaling.
        """
        # Handle invalid growth_rate (NaN or negative)
        if pd.isna(growth_rate) or growth_rate <= -1:
            growth_rate = 0
            
        # log(mentions) - We use 'volume' (number of occurrences across platforms) or 'engagement'
        log_mentions = np.log1p(volume)
        
        # growth_rate component (normalized 0-1)
        # Assuming growth_rate is provided in a scale where 100% is 1.0
        # If it's a raw number from scrapers, we normalize it.
        norm_growth = min(10, growth_rate / 500) 
        
        # engagement_weight (log(engagement))
        engagement_weight = np.log1p(max(0, engagement)) / 2.0
        
        # source_diversity - Number of platforms (already a count, but we can log it)
        diversity_weight = source_diversity * 1.5
        
        # ViralScore = log(mentions) + 2 * growth_rate + engagement_weight + source_diversity
        base_score = log_mentions + (2 * norm_growth) + engagement_weight + diversity_weight + (platform_weight * 2)
        
        # Sentiment impact (bonus)
        sentiment_bonus = abs(sentiment) * 0.5 
        base_score += sentiment_bonus
        
        # Spread impact
        if spread > 0:
            spread_bonus = np.log1p(spread) * 0.5
            base_score += spread_bonus
        
        # Final scaling: Mapping the expected range to 1-100 range using sigmoid.
        def sigmoid(x):
            return 1 / (1 + np.exp(-0.25 * (x - 12)))
        
        scaled_score = 1 + (sigmoid(base_score) * 99)
        return round(scaled_score, 2)

    def group_topics(self, df):
        """Groups similar topics across platforms using keyword overlap and fuzzy matching."""
        if df.empty or len(df) < 2:
            df['aggregated_topic'] = df['topic']
            return df
            
        # Create a copy to work on
        df = df.copy()
        topics = df['topic'].tolist()
        
        # Clean topics: lowercase, remove punctuation, split into words
        def get_keywords(text):
            text = re.sub(r'[^\w\s]', '', text.lower())
            words = set(text.split())
            # Remove common stop words (manual list for robustness if nltk is missing)
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'with', 'for', 'is', 'are', 'was', 'were', 'why', 'how', 'what', 'to', 'of', 'my', 'your', 'our', 'show', 'hn', 'app', 'apps'}
            return {w for w in words if w not in stop_words and len(w) > 2}

        topic_keywords = [get_keywords(t) for t in topics]
        
        # Union-Find
        parent = list(range(len(topics)))
        def find(i):
            root = i
            while parent[root] != root:
                root = parent[root]
            # Path compression (iterative)
            while parent[i] != root:
                next_node = parent[i]
                parent[i] = root
                i = next_node
            return root
            
        def union(i, j):
            root_i = find(i)
            root_j = find(j)
            if root_i != root_j:
                parent[root_i] = root_j
                
        for i in range(len(topics)):
            for j in range(i + 1, len(topics)):
                # Check for keyword overlap
                # If they share at least 2 significant words, or 1 if the shorter topic only has 1-2 words
                intersection = topic_keywords[i].intersection(topic_keywords[j])
                min_len = min(len(topic_keywords[i]), len(topic_keywords[j]))
                
                if not intersection:
                    continue
                    
                match = False
                if len(intersection) >= 2:
                    match = True
                elif len(intersection) >= 1 and min_len <= 2:
                    match = True
                
                if match:
                    union(i, j)
        
        # Build mapping from original index to representative topic
        group_to_indices = {}
        for i in range(len(topics)):
            root = find(i)
            if root not in group_to_indices:
                group_to_indices[root] = []
            group_to_indices[root].append(i)
            
        aggregated_map = {}
        for root, indices in group_to_indices.items():
            # Pick the shortest/cleanest title as the representative for the group
            rep_idx = min(indices, key=lambda x: len(topics[x]))
            rep_topic = topics[rep_idx]
            for idx in indices:
                aggregated_map[idx] = rep_topic

        df['aggregated_topic'] = [aggregated_map.get(i, topics[i]) for i in range(len(topics))]
        return df

    def process_trends(self, df):
        """Applies analytics to a DataFrame of collected trends."""
        if df.empty:
            return df
        
        # 1. Topic Aggregation (Clustering)
        df = self.group_topics(df)
        
        # 2. Add sentiment
        df.loc[:, 'sentiment'] = df['topic'].apply(self.analyze_sentiment)
        
        # 3. Engagement handling
        if 'engagement' not in df.columns:
            df.loc[:, 'engagement'] = 1000 
            df.loc[:, 'engagement'] = df['engagement'] + (df['growth'].fillna(0) * 2)
        
        # 4. Source diversity and aggregation
        # Count unique platforms per aggregated topic
        diversity_map = df.groupby('aggregated_topic')['platform'].nunique().to_dict()
        df.loc[:, 'source_diversity'] = df['aggregated_topic'].map(diversity_map)
        
        # Count volume (total mentions across platforms)
        volume_map = df.groupby('aggregated_topic')['topic'].count().to_dict()
        df.loc[:, 'volume'] = df['aggregated_topic'].map(volume_map)
        
        # 5. Define platform weights
        platform_weights = {
            "Google Trends": 1.0,
            "Google Related Queries": 1.1,
            "Google Related Topics": 1.1,
            "Google Interest": 1.0,
            "Google Regions": 1.2,
            "YouTube": 1.3,
            "X (Twitter)": 1.2,
            "Reddit": 1.4,
            "HackerNews": 1.3,
            "News": 1.1
        }
        
        # Ensure 'spread' column exists
        if 'spread' not in df.columns:
            df.loc[:, 'spread'] = 0

        # 6. Calculate Virality Score
        df.loc[:, 'virality_score'] = df.apply(lambda row: self.calculate_virality_score(
            row.get('growth', 0), 
            row.get('engagement', 0), 
            platform_weights.get(row.get('platform'), 1.0),
            row.get('sentiment', 0),
            row.get('spread', 0),
            row.get('source_diversity', 1),
            row.get('volume', 1)
        ), axis=1)
        
        # 7. Aggregate results to unique 'aggregated_topic'
        # Group by platform AND aggregated_topic to avoid losing information from different platforms
        # BUT the user wants a unified view of the trend across platforms.
        # If we group only by aggregated_topic, we lose platform-specific details if multiple platforms share the same topic.
        
        # Let's keep one entry per (aggregated_topic, platform) to show breadth, 
        # or aggregate them but keep the platform list (which we do).
        
        agg_dict = {
            'virality_score': 'max',
            'growth': 'max',
            'engagement': 'max', # Changed from sum to max to avoid inflated numbers
            'sentiment': 'mean',
            'platform': lambda x: list(set(x)),
            'source_diversity': 'first',
            'volume': 'first',
            'topic': 'first',
            'geo': lambda x: list(set(str(v) for v in x if v)), # Preserve geos
            'keyword': 'first',
            'extracted_at': 'max'
        }
        
        # Add source-specific columns if they exist in the dataframe
        optional_cols = ['url', 'published', 'posts', 'replies', 'subreddit', 'source', 'author']
        for col in optional_cols:
            if col in df.columns:
                # Instead of 'first', try to get the first non-null/non-empty value
                agg_dict[col] = lambda x: next((v for v in x if v and v != 'N/A'), x.iloc[0])
                
        aggregated_results = df.groupby('aggregated_topic').agg(agg_dict).reset_index()
        
        # Sort by Virality Score
        aggregated_results = aggregated_results.sort_values(by='virality_score', ascending=False)
        
        return aggregated_results

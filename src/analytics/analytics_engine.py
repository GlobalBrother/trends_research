import pandas as pd
from textblob import TextBlob
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import numpy as np
import nltk

class AnalyticsEngine:
    def __init__(self):
        try:
            # Ensure VADER lexicon is available if using nltk version, 
            # though vaderSentiment package usually includes it.
            # Using vaderSentiment package directly here as in original code.
            self.analyzer = SentimentIntensityAnalyzer()
        except Exception:
            # Fallback/Initialization if needed
            nltk.download('vader_lexicon', quiet=True)
            self.analyzer = SentimentIntensityAnalyzer()

    def analyze_sentiment(self, text):
        """Analyzes sentiment using VADER."""
        scores = self.analyzer.polarity_scores(str(text))
        return scores['compound']

    def calculate_virality_score(self, growth_rate, engagement=1.0, platform_weight=1.0, sentiment=0.0, spread=0):
        """Calculates a custom Virality Score based on growth, engagement, platform weight, sentiment and geographical spread."""
        # Logarithmic normalization of large values
        log_growth = np.log1p(growth_rate)
        log_engagement = np.log1p(engagement)
        
        # Weighted base score: 60% growth, 40% engagement
        base_score = (log_growth * 0.6) + (log_engagement * 0.4)
        
        # Apply platform weight
        base_score *= platform_weight
        
        # Sentiment impact
        sentiment_bonus = abs(sentiment) * 0.5 
        base_score += sentiment_bonus
        
        # Spread impact: If geographical spread data is available, it boosts the score.
        # Spread is typically number of regions (0-50+). log1p(spread) is around 0-4.
        if spread > 0:
            spread_bonus = np.log1p(spread) * 0.3
            base_score += spread_bonus
        
        # Final scaling: Mapping the expected log range (roughly 0 to 15-20) to 1-100 range.
        # Use a sigmoid-like scaling to compress extremely large outliers.
        def sigmoid(x):
            return 1 / (1 + np.exp(-0.4 * (x - 10)))
        
        scaled_score = 1 + (sigmoid(base_score) * 99)
        return round(scaled_score, 2)

    def process_trends(self, df):
        """Applies analytics to a DataFrame of collected trends."""
        if df.empty:
            return df
        
        # Add sentiment
        df['sentiment'] = df['topic'].apply(self.analyze_sentiment)
        
        # Fixed Engagement (default baseline since we don't have real API engagement metrics)
        df['engagement'] = 10000 
        
        # We can apply a small boost based on growth to make it feel more dynamic but still deterministic
        df['engagement'] = df['engagement'] + (df['growth'] * 2)
        
        # Define platform weights
        platform_weights = {
            "Google Trends": 1.0,
            "Google Related Queries": 1.1,
            "Google Related Topics": 1.1,
            "Google Interest": 1.0,
            "Google Regions": 1.2 # Geographical spread is a strong indicator
        }
        
        # Ensure 'spread' column exists
        if 'spread' not in df.columns:
            df['spread'] = 0

        # Calculate Virality Score
        df['virality_score'] = df.apply(lambda row: self.calculate_virality_score(
            row['growth'], 
            row['engagement'], 
            platform_weights.get(row['platform'], 1.0),
            row['sentiment'],
            row.get('spread', 0)
        ), axis=1)
        
        # Sort by Virality Score
        df = df.sort_values(by='virality_score', ascending=False)
        
        return df

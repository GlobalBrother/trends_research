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

    def calculate_virality_score(self, growth_rate, engagement=1.0, platform_weight=1.0):
        """Calculates a custom Virality Score based on growth, engagement, and platform weight."""
        # Log growth to normalize huge numbers
        log_growth = np.log1p(growth_rate)
        # Combine growth and engagement
        base_score = (log_growth * 0.7) + (np.log1p(engagement) * 0.3)
        # Apply platform weight (some platforms have higher viral velocity)
        final_score = base_score * platform_weight
        # Scale to 1-100 range
        scaled_score = min(max(final_score * 5, 1), 100)
        return round(scaled_score, 2)

    def process_trends(self, df):
        """Applies analytics to a DataFrame of collected trends."""
        if df.empty:
            return df
        
        # Add sentiment
        df['sentiment'] = df['topic'].apply(self.analyze_sentiment)
        
        # Engagement placeholder (random since we don't have real API engagement metrics)
        df['engagement'] = np.random.randint(1000, 100000, size=len(df))
        
        # Define platform weights
        platform_weights = {
            "Google Trends (Scrapy)": 1.0,
            "Google Related Queries (Scrapy)": 1.1,
            "Google Related Topics (Scrapy)": 1.1,
            "Google Interest (Scrapy)": 1.0
        }
        
        # Calculate Virality Score
        df['virality_score'] = df.apply(lambda row: self.calculate_virality_score(
            row['growth'], 
            row['engagement'], 
            platform_weights.get(row['platform'], 1.0)
        ), axis=1)
        
        # Sort by Virality Score
        df = df.sort_values(by='virality_score', ascending=False)
        
        return df

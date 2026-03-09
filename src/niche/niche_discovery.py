from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import pandas as pd

class NicheDiscovery:
    def __init__(self, n_clusters=5):
        self.n_clusters = n_clusters
        self.vectorizer = TfidfVectorizer(stop_words='english')

    def filter_by_niche(self, df, niche_keyword):
        """Filters trends by a specific niche keyword."""
        if df.empty:
            return df
        return df[df['topic'].str.contains(niche_keyword, case=False, na=False)]

    def discover_micro_niches(self, df):
        """Clusters related keywords to find micro-niches."""
        if df.empty or len(df) < self.n_clusters:
            return df
        
        # Vectorize topics
        X = self.vectorizer.fit_transform(df['topic'])
        
        # KMeans clustering
        kmeans = KMeans(n_clusters=self.n_clusters, random_state=42, n_init=10)
        df['niche_cluster'] = kmeans.fit_predict(X)
        
        return df

    def suggest_content_opportunities(self, df):
        """Generates simple content ideas based on trending topics."""
        opportunities = []
        for _, row in df.iterrows():
            topic = row['topic']
            # Simple content templates
            opportunities.append(f"How to leverage {topic} for your brand")
            opportunities.append(f"The ultimate guide to {topic} in 2026")
            opportunities.append(f"Why {topic} is currently trending: A deep dive")
            
        return opportunities

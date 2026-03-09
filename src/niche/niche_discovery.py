from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import pandas as pd

class NicheDiscovery:
    def __init__(self, n_clusters=5):
        self.n_clusters = n_clusters
        self.vectorizer = TfidfVectorizer(stop_words='english')

    def filter_by_niche(self, df, niche_keyword):
        """Filters trends by a specific niche keyword or common synonyms."""
        if df.empty or not niche_keyword or niche_keyword == "All":
            return df
        
        # Mapping niches to potential keywords for better filtering
        niche_map = {
            "Survival": ["Survival", "Emergency", "Outdoors", "Bushcraft", "Disaster", "Self-sufficiency"],
            "Health": ["Health", "Fitness", "Wellness", "Medical", "Diet", "Workout", "Medicine"],
            "Preppers": ["Prepper", "Emergency Prep", "Stockpile", "Off-grid", "Preparedness", "Survivalist"],
            "Tech": ["Tech", "Apple", "Software", "Hardware", "iPhone", "Review"],
            "Crypto": ["Crypto", "Bitcoin", "Ethereum", "#Crypto", "Blockchain"],
            "AI": ["AI", "Artificial Intelligence", "Machine Learning", "ChatGPT", "LLM"],
            "Gaming": ["Gaming", "Video Games", "PlayStation", "Xbox", "Nintendo", "Streamer"],
            "Finance": ["Finance", "Market", "Stock", "Economy", "Investment", "Trading"],
            "Food": ["Cooking", "Recipe", "Food", "Restaurant", "Chef", "Tutorial"],
            "Business": ["Business", "Startup", "Marketing", "Entrepreneur", "Strategy"],
            "Entertainment": ["Movie", "Trailer", "Actor", "Hollywood", "Music", "Singer", "#F1"]
        }
        
        keywords = niche_map.get(niche_keyword, [niche_keyword])
        pattern = '|'.join(keywords)
        
        return df[df['topic'].str.contains(pattern, case=False, na=False)]

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


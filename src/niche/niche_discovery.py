from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import pandas as pd

class NicheDiscovery:
    def __init__(self, n_clusters=5):
        self.n_clusters = n_clusters
        self.vectorizer = TfidfVectorizer(stop_words='english')

    def get_niche_keywords(self, niche_name):
        """Returns a representative list of keywords for a niche to be used in scraping."""
        niche_map = {
            "Survival": ["Survival", "Bushcraft", "SHTF", "Wilderness survival", "First aid", "Foraging", "Emergency preparedness"],
            "Health": ["Natural remedy", "Herbal wellness", "Holistic health"],
            "Preppers": ["Prepper", "Off-grid living", "DIY off grid", "Emergency preparedness", "Survivalist"]
        }
        return niche_map.get(niche_name, [niche_name])

    def filter_by_niche(self, df, niche_keyword):
        """Filters trends by a specific niche keyword or common synonyms."""
        if df.empty or not niche_keyword or niche_keyword == "All":
            return df
        
        # Mapping niches to potential keywords for better filtering
        # Each entry can be a list of include keywords or a dict with 'include' and 'exclude'
        niche_map = {
            "Survival": {
                "include": ["Survival", "Emergency", "Outdoors", "Bushcraft", "Disaster", "Self-sufficiency", "First aid", "Foraging", "Wilderness survival", "Preparedness"],
                "exclude": ["Gaming", "Video game", "Mod", "Download", "Novel", "Book", "Fiction", "Minecraft", "Zomboid", "Roblox", "Fortnite"]
            },
            "Health": {
                "include": ["Self remedies", "Home remedy", "Natural cure", "Herbal", "Wellness", "Holistic"],
                "exclude": ["Pharmacy", "Department", "Pharma", "Hospital", "Government", "Clinic"]
            },
            "Preppers": {
                "include": ["Prepper", "Emergency Prep", "Stockpile", "Off-grid", "Preparedness", "Survivalist", "DIY off grid", "Solar power", "Water purification", "Generator", "SHTF", "Homesteading"],
                "exclude": ["Gaming", "Video game"]
            }
        }
        
        config = niche_map.get(niche_keyword, [niche_keyword])
        
        if isinstance(config, list):
            include_keywords = config
            exclude_keywords = []
        else:
            include_keywords = config.get("include", [])
            exclude_keywords = config.get("exclude", [])

        # Include filter
        if include_keywords:
            include_pattern = '|'.join(include_keywords)
            df = df[df['topic'].str.contains(include_pattern, case=False, na=False)]
        
        # Exclude filter
        if not df.empty and exclude_keywords:
            exclude_pattern = '|'.join(exclude_keywords)
            df = df[~df['topic'].str.contains(exclude_pattern, case=False, na=False)]
            
        return df

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


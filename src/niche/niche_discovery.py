"""
Niche discovery — filters and clusters trends into predefined niches.

Provides keyword-based filtering with include/exclude lists and
KMeans micro-niche clustering via TF-IDF vectorisation.
"""

import logging
from typing import Optional

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_N_CLUSTERS = 5
KMEANS_RANDOM_STATE = 42
KMEANS_N_INIT = 10

# Niche seed keywords used for scraping
NICHE_SEED_KEYWORDS: dict[str, list[str]] = {
    "Survival": [
        "Survival skills", "Bushcraft", "SHTF", "Wilderness survival", "First aid kit",
        "Foraging", "Emergency preparedness", "Survival gear", "Water filtration",
        "Fire starting", "Survival shelter", "Wilderness medical", "EDC gear",
        "Navigation skills", "Survival mindset", "Outdoor survival",
    ],
    "Health": [
        "Natural remedy", "Herbal wellness", "Holistic health", "Essential oils",
        "Medicinal plants", "Acupuncture", "Detox diet", "Gut health",
        "Intermittent fasting", "Mindfulness meditation", "Homeopathy", "Ayurveda",
        "Yoga therapy", "Naturopathic medicine", "Biohacking", "Supplements",
        "Home remedies", "Self-remedy", "Natural cures", "Herbal remedies",
        "Traditional medicine",
    ],
    "Preppers": [
        "Prepper", "Off-grid living", "DIY off grid", "Emergency preparedness",
        "Survivalist", "Bug out bag", "Freeze dried food", "Ham radio",
        "Nuclear preparedness", "Long-term storage", "Root cellar", "Water catchment",
        "Solar generator", "Seed saving", "EMP protection", "Self-sufficiency",
    ],
    "Sustainability": [
        "Sustainable living", "Zero waste", "Permaculture", "Renewable energy",
        "Composting", "Rainwater harvesting", "Upcycling", "Solar energy",
        "Electric vehicles", "Plastic free", "Minimalism", "Urban farming",
        "Green building", "Biodiversity", "Carbon footprint",
    ],
    "Homesteading": [
        "Homesteading for beginners", "Raising chickens", "Beekeeping",
        "Preserving food", "Kitchen garden", "Dairy goats", "Organic gardening",
        "Small scale farming", "Animal husbandry", "Soap making", "Bread baking",
        "Off grid homestead", "Homestead chores", "Livestock", "Barn building",
    ],
}

# Niche filtering rules: include/exclude keyword patterns for topic matching
NICHE_FILTER_RULES: dict[str, dict[str, list[str]]] = {
    "Survival": {
        "include": [
            "Survival", "Emergency", "Outdoors", "Bushcraft", "Disaster",
            "Self-sufficiency", "First aid", "Foraging", "Wilderness survival",
            "Preparedness", "Water filter", "Fire steel", "Shelter", "Signaling",
            "Rescue", "Evasion", "EDC", "Tactical gear", "Knives", "Med kit",
        ],
        "exclude": [
            "Gaming", "Video game", "Mod", "Download", "Novel", "Book", "Fiction",
            "Minecraft", "Zomboid", "Roblox", "Fortnite", "Playstation", "Xbox",
            "Switch", "Simulator", "Steam", "Epic Games",
        ],
    },
    "Health": {
        "include": [
            "Self remedies", "Home remedy", "Natural cure", "Herbal", "Wellness",
            "Holistic", "Naturopathic", "Organic", "Detox", "Probiotics",
            "Microbiome", "Essential oils", "Acupressure", "Meditation", "Vegan",
            "Keto", "Paleo", "Superfoods", "Tincture", "Poultice", "Remedy",
            "Remedies", "Cures", "Traditional",
        ],
        "exclude": [
            "Pharmacy", "Department", "Pharma", "Hospital", "Government", "Clinic",
            "Surgery", "Drug", "Prescription", "Vaccine", "Medication",
        ],
    },
    "Preppers": {
        "include": [
            "Prepper", "Emergency Prep", "Stockpile", "Off-grid", "Preparedness",
            "Survivalist", "DIY off grid", "Solar power", "Water purification",
            "Generator", "SHTF", "Homesteading", "Canning", "Jarring",
            "Root cellar", "Ammunition", "Gold silver", "Barter", "Bug out",
            "Sustenance", "Self-reliance",
        ],
        "exclude": ["Gaming", "Video game", "Movie", "Trailer", "Review"],
    },
    "Sustainability": {
        "include": [
            "Sustainable", "Zero waste", "Permaculture", "Renewable", "Compost",
            "Harvesting", "Upcycle", "Solar", "Wind power", "Minimalism",
            "Eco-friendly", "Recycle", "Biodegradable",
        ],
        "exclude": ["Gaming", "Video game"],
    },
    "Homesteading": {
        "include": [
            "Homestead", "Chicken", "Beekeeping", "Preserving", "Garden", "Goat",
            "Farming", "Husbandry", "Livestock", "Barn", "Crops", "Soil",
        ],
        "exclude": ["Gaming", "Video game"],
    },
}


class NicheDiscovery:
    """Filters trends into predefined niches and discovers micro-niches via clustering."""

    def __init__(self, n_clusters: int = DEFAULT_N_CLUSTERS) -> None:
        self.n_clusters = n_clusters
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.niche_map = NICHE_SEED_KEYWORDS

    def get_available_niches(self) -> list[str]:
        """Return a list of all defined niche names."""
        return list(self.niche_map.keys())

    def get_niche_keywords(self, niche_name: str) -> list[str]:
        """Return seed keywords for a niche (used for scraping)."""
        return self.niche_map.get(niche_name, [niche_name])

    # ------------------------------------------------------------------
    # Niche filtering
    # ------------------------------------------------------------------

    def filter_by_niche(self, df: pd.DataFrame, niche_keyword: str) -> pd.DataFrame:
        """Filter trends by a specific niche using include/exclude keyword patterns."""
        if df.empty or not niche_keyword or niche_keyword == "All":
            return df

        config = NICHE_FILTER_RULES.get(niche_keyword)
        if config is None:
            # Unknown niche — simple substring match
            include_keywords = [niche_keyword]
            exclude_keywords: list[str] = []
        else:
            include_keywords = config.get("include", [])
            exclude_keywords = config.get("exclude", [])

        # Apply include filter
        if include_keywords:
            include_pattern = f"(?:{'|'.join(include_keywords)})|{niche_keyword}"
            mask = df["topic"].str.contains(include_pattern, case=False, na=False, regex=True)
            if "keyword" in df.columns:
                mask |= df["keyword"].str.contains(include_pattern, case=False, na=False, regex=True)
            df = df[mask].copy()

        # Apply exclude filter
        if not df.empty and exclude_keywords:
            exclude_pattern = "|".join(exclude_keywords)
            df = df[~df["topic"].str.contains(exclude_pattern, case=False, na=False, regex=True)]

        return df

    # ------------------------------------------------------------------
    # Micro-niche clustering
    # ------------------------------------------------------------------

    def discover_micro_niches(self, df: pd.DataFrame) -> pd.DataFrame:
        """Cluster related topics to find micro-niches using KMeans."""
        if df.empty or len(df) < self.n_clusters:
            return df

        try:
            df = df.copy()
            tfidf_matrix = self.vectorizer.fit_transform(df["topic"])
            kmeans = KMeans(
                n_clusters=self.n_clusters,
                random_state=KMEANS_RANDOM_STATE,
                n_init=KMEANS_N_INIT,
            )
            df["niche_cluster"] = kmeans.fit_predict(tfidf_matrix)
        except Exception as e:
            logger.warning("Clustering failed: %s", e)

        return df

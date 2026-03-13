import requests
import pandas as pd
import streamlit as st
import os

class APIClient:
    def __init__(self):
        self.base_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

    def get_niches(self):
        try:
            response = requests.get(f"{self.base_url}/niches")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Failed to fetch niches: {e}")
            return ["Survival", "Health", "Preppers", "Sustainability", "Homesteading"]

    def get_niche_keywords(self, niche_name):
        try:
            response = requests.get(f"{self.base_url}/niche_keywords/{niche_name}")
            response.raise_for_status()
            return response.json().get("keywords", [])
        except Exception as e:
            st.error(f"Failed to fetch keywords for {niche_name}: {e}")
            return []

    def import_tokens(self, file_bytes, filename, geo="US"):
        try:
            files = {"file": (filename, file_bytes, "application/json")}
            params = {"geo": geo}
            response = requests.post(f"{self.base_url}/import_tokens", files=files, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Token import failed: {e}")
            return None

    def trigger_scrape(self, niche_name, geo="US", timeframe="today 12-m", category=0, scraper_type="all"):
        try:
            payload = {
                "niche": niche_name,
                "geo": geo,
                "timeframe": timeframe,
                "category": category,
                "scraper_type": scraper_type
            }
            response = requests.post(f"{self.base_url}/scrape", json=payload)
            response.raise_for_status()
            return True
        except Exception as e:
            st.error(f"Scrape request failed: {e}")
            return False

    @st.cache_data(ttl=600)
    def get_trends(_self, geo="US", niche_name=None):
        try:
            params = {"geo": geo}
            if niche_name:
                params["niche_name"] = niche_name
            
            response = requests.get(f"{_self.base_url}/trends", params=params)
            response.raise_for_status()
            data = response.json().get("data", [])
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Failed to fetch trends: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=3600) # Longer cache for trending now
    def get_trending_now(_self, geo="US", trend_type="daily"):
        try:
            params = {"geo": geo, "trend_type": trend_type}
            response = requests.get(f"{_self.base_url}/trending_now", params=params)
            response.raise_for_status()
            data = response.json().get("data", [])
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Failed to fetch trending now: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def get_youtube_trends(_self, niche_name, geo="US"):
        try:
            params = {"niche_name": niche_name, "geo": geo}
            response = requests.get(f"{_self.base_url}/youtube_trends", params=params)
            response.raise_for_status()
            data = response.json().get("data", [])
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Failed to fetch YouTube trends: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def get_social_trends(_self, platform, niche_name, geo="US"):
        try:
            params = {"platform": platform, "niche_name": niche_name, "geo": geo}
            response = requests.get(f"{_self.base_url}/social_trends", params=params)
            response.raise_for_status()
            data = response.json().get("data", [])
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Failed to fetch {platform} trends: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=600)
    def get_hackernews_trends(_self, niche_name=None, geo="US"):
        try:
            params = {"geo": geo}
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/hackernews_trends", params=params)
            response.raise_for_status()
            data = response.json().get("data", [])
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Failed to fetch HackerNews trends: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=600)
    def get_reddit_trends(_self, subreddit='all', trend_type='hot', niche_name=None, geo="US"):
        try:
            params = {'subreddit': subreddit, 'trend_type': trend_type, 'geo': geo}
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/reddit_trends", params=params)
            response.raise_for_status()
            data = response.json().get("data", [])
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Failed to fetch Reddit trends: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=600)
    def get_news_trends(_self, query='niche', niche_name=None, geo="US"):
        try:
            params = {'query': query, 'geo': geo}
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/news_trends", params=params)
            response.raise_for_status()
            data = response.json().get("data", [])
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Failed to fetch News trends: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=60)
    def get_scrape_errors(_self, platform=None):
        try:
            params = {}
            if platform:
                params['platform'] = platform
            response = requests.get(f"{_self.base_url}/scrape_errors", params=params)
            response.raise_for_status()
            data = response.json().get("data", [])
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Failed to fetch scrape errors: {e}")
            return pd.DataFrame()

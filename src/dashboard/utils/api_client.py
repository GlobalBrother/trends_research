import requests
import pandas as pd
import streamlit as st
import os

class APIClient:
    def __init__(self):
        self.base_url = os.getenv("BACKEND_URL", "http://localhost:8000")

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

    def trigger_scrape(self, niche_name, geo="US", timeframe="today 12-m", category=0):
        try:
            payload = {
                "niche": niche_name,
                "geo": geo,
                "timeframe": timeframe,
                "category": category
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

"""
APIClient — typed HTTP wrapper around the FastAPI backend.

Used exclusively by the Streamlit dashboard. Handles caching, error display,
and DataFrame conversion so that dashboard code stays presentation-focused.
"""

import logging
import os
from typing import Optional

import pandas as pd
import requests
import streamlit as st

logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")


class APIClient:
    """Thin HTTP client for the Trends Research API."""

    def __init__(self, base_url: str = _BASE_URL):
        self.base_url = base_url

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None, timeout: int = 30) -> dict:
        """Perform a GET request and return the parsed JSON body."""
        try:
            resp = requests.get(f"{self.base_url}{path}", params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("GET %s failed: %s", path, exc)
            st.error(f"API request failed: {exc}")
            return {}

    def _post(self, path: str, payload: dict, timeout: int = 30) -> bool:
        try:
            resp = requests.post(f"{self.base_url}{path}", json=payload, timeout=timeout)
            resp.raise_for_status()
            return True
        except requests.RequestException as exc:
            logger.error("POST %s failed: %s", path, exc)
            st.error(f"API request failed: {exc}")
            return False

    @staticmethod
    def _to_df(data: dict, key: str = "data") -> pd.DataFrame:
        rows = data.get(key, [])
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_niches(self) -> list[str]:
        data = self._get("/niches")
        if isinstance(data, list):
            return data
        return ["Survival", "Health", "Preppers", "Sustainability", "Homesteading"]

    def get_niche_keywords(self, niche_name: str) -> list[str]:
        data = self._get(f"/niche_keywords/{niche_name}")
        return data.get("keywords", [])

    def trigger_scrape(self, niche_name: str, geo: str = "US",
                       timeframe: str = "today 12-m", category: int = 0) -> bool:
        return self._post("/scrape", {
            "niche": niche_name, "geo": geo,
            "timeframe": timeframe, "category": category,
        })

    # Cached data fetchers -------------------------------------------------

    @st.cache_data(ttl=600)
    def get_trends(_self, geo: str = "US", niche_name: Optional[str] = None) -> pd.DataFrame:
        params = {"geo": geo}
        if niche_name:
            params["niche_name"] = niche_name
        return _self._to_df(_self._get("/trends", params))

    @st.cache_data(ttl=3600)
    def get_trending_now(_self, geo: str = "US", trend_type: str = "daily") -> pd.DataFrame:
        return _self._to_df(_self._get("/trending_now", {"geo": geo, "trend_type": trend_type}))

    @st.cache_data(ttl=3600)
    def get_youtube_trends(_self, niche_name: str, geo: str = "US") -> pd.DataFrame:
        return _self._to_df(_self._get("/youtube_trends", {"niche_name": niche_name, "geo": geo}))

    @st.cache_data(ttl=3600)
    def get_social_trends(_self, platform: str, niche_name: str, geo: str = "US") -> pd.DataFrame:
        return _self._to_df(_self._get("/social_trends", {
            "platform": platform, "niche_name": niche_name, "geo": geo,
        }))

    @st.cache_data(ttl=600)
    def get_hackernews_trends(_self, niche_name: Optional[str] = None, geo: str = "US") -> pd.DataFrame:
        params: dict = {"geo": geo}
        if niche_name:
            params["niche_name"] = niche_name
        return _self._to_df(_self._get("/hackernews_trends", params))

    @st.cache_data(ttl=600)
    def get_reddit_trends(_self, subreddit: str = "all", trend_type: str = "hot",
                          niche_name: Optional[str] = None, geo: str = "US") -> pd.DataFrame:
        params: dict = {"subreddit": subreddit, "trend_type": trend_type, "geo": geo}
        if niche_name:
            params["niche_name"] = niche_name
        return _self._to_df(_self._get("/reddit_trends", params))

    @st.cache_data(ttl=600)
    def get_news_trends(_self, query: str = "niche", niche_name: Optional[str] = None,
                        geo: str = "US") -> pd.DataFrame:
        params: dict = {"query": query, "geo": geo}
        if niche_name:
            params["niche_name"] = niche_name
        return _self._to_df(_self._get("/news_trends", params))

    @st.cache_data(ttl=60)
    def get_scrape_errors(_self, platform: Optional[str] = None) -> pd.DataFrame:
        params: dict = {}
        if platform:
            params["platform"] = platform
        return _self._to_df(_self._get("/scrape_errors", params))

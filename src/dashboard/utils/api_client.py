import requests
import pandas as pd
import streamlit as st
import os
import sys
import json

# Ensure project root is in path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Try to import the niche discovery for keywords (lightweight, no scraper deps)
try:
    from src.niche.niche_discovery import NicheDiscovery
    _niche = NicheDiscovery()
except ImportError:
    _niche = None


class APIClient:
    def __init__(self):
        self.base_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
        self.direct = False  # Always use API mode now

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def request_otp(self, email):
        """Request an OTP code for the given email."""
        try:
            resp = requests.post(f"{self.base_url}/auth/request_otp", params={"email": email}, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            detail = ""
            try:
                detail = e.response.json().get("detail", str(e))
            except Exception:
                detail = str(e)
            return {"error": detail}
        except Exception as e:
            return {"error": str(e)}

    def verify_otp(self, email, code):
        """Verify an OTP code. Returns dict with 'role' on success or 'error'."""
        try:
            resp = requests.post(
                f"{self.base_url}/auth/verify_otp",
                params={"email": email, "code": code},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            detail = ""
            try:
                detail = e.response.json().get("detail", str(e))
            except Exception:
                detail = str(e)
            return {"error": detail}
        except Exception as e:
            return {"error": str(e)}

    def validate_token(self, token):
        """Validate an auth token. Returns dict with email/role or 'error'."""
        try:
            resp = requests.get(
                f"{self.base_url}/auth/validate_token",
                params={"token": token},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {"error": "Invalid or expired token"}

    def list_users(self):
        """Return list of whitelisted users."""
        try:
            resp = requests.get(f"{self.base_url}/auth/users", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return []

    def add_user(self, email, role="trends"):
        try:
            resp = requests.post(
                f"{self.base_url}/auth/users",
                json={"email": email, "role": role},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            detail = ""
            try:
                detail = e.response.json().get("detail", str(e))
            except Exception:
                detail = str(e)
            return {"error": detail}
        except Exception as e:
            return {"error": str(e)}

    def update_user_role(self, email, role):
        try:
            resp = requests.put(
                f"{self.base_url}/auth/users",
                params={"email": email, "role": role},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            detail = ""
            try:
                detail = e.response.json().get("detail", str(e))
            except Exception:
                detail = str(e)
            return {"error": detail}
        except Exception as e:
            return {"error": str(e)}

    def delete_user(self, email):
        try:
            resp = requests.delete(
                f"{self.base_url}/auth/users",
                params={"email": email},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            detail = ""
            try:
                detail = e.response.json().get("detail", str(e))
            except Exception:
                detail = str(e)
            return {"error": detail}
        except Exception as e:
            return {"error": str(e)}

    def _get_niche_keywords(self, niche_name):
        if _niche and niche_name:
            return _niche.get_niche_keywords(niche_name)
        return []

    def get_niches(self):
        try:
            response = requests.get(f"{self.base_url}/niches", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception:
            if _niche:
                return _niche.get_available_niches()
            return ["Survival", "Health", "Preppers", "Sustainability", "Homesteading"]

    @st.cache_data(ttl=600)
    def get_table_filters(_self, table_name, geo_col="geo", keyword_col="search_keyword"):
        """Return distinct geo and keyword values from a given DB table via API."""
        geos, keywords = ["Global"], ["All"]
        try:
            params = {"table_name": table_name, "geo_col": geo_col, "keyword_col": keyword_col}
            response = requests.get(f"{_self.base_url}/table_filters", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            geos = data.get("geos", geos)
            keywords = data.get("keywords", keywords)
        except Exception:
            pass
        return geos, keywords

    def get_niche_keywords(self, niche_name):
        try:
            response = requests.get(f"{self.base_url}/niche_keywords/{niche_name}", timeout=5)
            response.raise_for_status()
            return response.json().get("keywords", [])
        except Exception:
            return self._get_niche_keywords(niche_name)

    def import_tokens(self, file_bytes, filename, geo="US"):
        try:
            files = {"file": (filename, file_bytes, "application/json")}
            params = {"geo": geo}
            response = requests.post(f"{self.base_url}/import_tokens", files=files, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Token import failed: {e}")
            return None

    def trigger_scrape(self, niche_name, geo="US", timeframe="today 12-m", category=0, scraper_type="all"):
        """Trigger scraping via the FastAPI backend."""
        try:
            payload = {
                "niche": niche_name,
                "geo": geo,
                "timeframe": timeframe,
                "category": category,
                "scraper_type": scraper_type,
            }
            response = requests.post(f"{self.base_url}/scrape", json=payload, timeout=10)
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
            response = requests.get(f"{_self.base_url}/trends", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def get_trending_now(_self, geo="US", trend_type="daily"):
        try:
            params = {"geo": geo, "trend_type": trend_type}
            response = requests.get(f"{_self.base_url}/trending_now", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def get_youtube_videos(_self, niche_name=None, geo="US", limit=500):
        """Read from the dedicated youtube_videos table via API."""
        try:
            params = {"limit": limit}
            if geo and geo != "Global":
                params["geo"] = geo
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/youtube_videos", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def get_youtube_trends(_self, niche_name, geo="US"):
        """Fallback: read YouTube from generic trends table."""
        try:
            params = {"niche_name": niche_name, "geo": geo}
            response = requests.get(f"{_self.base_url}/youtube_trends", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def get_instagram_posts(_self, niche_name=None, geo="US", limit=500):
        """Read from the dedicated instagram_posts table via API."""
        try:
            params = {"limit": limit}
            if geo and geo != "Global":
                params["geo"] = geo
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/instagram_posts", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def get_reddit_posts(_self, niche_name=None, geo="US", limit=500):
        """Read from the dedicated reddit_posts table via API."""
        try:
            params = {"limit": limit}
            if geo and geo != "Global":
                params["geo"] = geo
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/reddit_posts", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def get_threads_posts(_self, niche_name=None, geo="US", limit=500):
        """Read from the dedicated threads_posts table via API."""
        try:
            params = {"limit": limit}
            if geo and geo != "Global":
                params["geo"] = geo
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/threads_posts", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=600)
    def get_hackernews_trends(_self, niche_name=None, geo="US"):
        try:
            params = {"geo": geo}
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/hackernews_trends", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=600)
    def get_reddit_trends(_self, subreddit='all', trend_type='hot', niche_name=None, geo="US"):
        """Fallback: read Reddit from generic trends table."""
        try:
            params = {'subreddit': subreddit, 'trend_type': trend_type, 'geo': geo}
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/reddit_trends", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=600)
    def get_news_trends(_self, query='niche', niche_name=None, geo="US"):
        try:
            params = {'query': query, 'geo': geo}
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/news_trends", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def get_tiktok_videos(_self, niche_name=None, geo="US", limit=500):
        """Read from the dedicated tiktok_videos table via API."""
        try:
            params = {"limit": limit}
            if geo and geo != "Global":
                params["geo"] = geo
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/tiktok_videos", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=60)
    def get_scrape_errors(_self, platform=None):
        try:
            params = {}
            if platform:
                params['platform'] = platform
            response = requests.get(f"{_self.base_url}/scrape_errors", params=params, timeout=10)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=600)
    def get_ads_insight(_self, niche_name=None, geo="US", limit=500):
        """Read from the dedicated ads_insight table via API."""
        try:
            params = {"limit": limit}
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/ads_insight", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            return pd.DataFrame()

    def scrape_ads_direct(self, keywords, max_pages=3):
        """Run GetHookdAI ads scraper via API."""
        try:
            params = {"keywords": ",".join(keywords), "max_pages": max_pages}
            response = requests.post(f"{self.base_url}/scrape_ads", params=params, timeout=10)
            response.raise_for_status()
            return True
        except Exception as e:
            st.error(f"Ads scrape failed: {e}")
            return False

    def search_brands(self, query):
        """Search brands by name via GetHookd explore API."""
        try:
            response = requests.get(f"{self.base_url}/search_brands", params={"query": query}, timeout=30)
            response.raise_for_status()
            return response.json().get("data", [])
        except Exception as e:
            st.error(f"Brand search failed: {e}")
            return []

    def scrape_brand_ads_direct(self, brand_id):
        """Run GetHookdAI brand spy scraper via API."""
        try:
            params = {"brand_id": brand_id}
            response = requests.post(f"{self.base_url}/scrape_brand_ads", params=params, timeout=10)
            response.raise_for_status()
            return True
        except Exception as e:
            st.error(f"Brand spy scrape failed: {e}")
            return False

    def get_token_usage(self):
        """Return token/units consumption data."""
        try:
            resp = requests.get(f"{self.base_url}/admin/token_usage", timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {"data": [], "summary": []}

    def clear_scrape_errors(self):
        """Delete all rows from the scrape_errors table via API."""
        try:
            response = requests.delete(f"{self.base_url}/scrape_errors", timeout=10)
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Failed to clear scrape_errors: {e}")
            return False

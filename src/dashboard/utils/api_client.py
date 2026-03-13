import requests
import pandas as pd
import streamlit as st
import os
import sys
import json
import sqlite3
from datetime import datetime

# Ensure project root is in path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Try to import ensembledata scrapers
try:
    _ed_dir = os.path.join(project_root, "src", "scrapers", "ensembledata")
    if _ed_dir not in sys.path:
        sys.path.insert(0, _ed_dir)
    from tiktok_scraper import scrape_tiktok
    from instagram_scraper import scrape_instagram
    from youtube_scraper import scrape_youtube
    from reddit_scraper import scrape_reddit
    from threads_scraper import scrape_threads
    from run_all import run_all as run_all_ensembledata
    HAS_ENSEMBLEDATA = True
except ImportError:
    HAS_ENSEMBLEDATA = False

# Try to import the niche discovery for keywords
try:
    from src.niche.niche_discovery import NicheDiscovery
    _niche = NicheDiscovery()
except ImportError:
    _niche = None

# Try to import analytics engine
try:
    from src.analytics.analytics_engine import AnalyticsEngine
    _analytics = AnalyticsEngine()
except ImportError:
    _analytics = None

DB_PATH = os.path.join(project_root, "src", "collector", "trends.db")


def _has_ensembledata_token():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(project_root, ".env"))
    return bool(os.getenv("ENSEMBLEDATA_TOKEN", ""))


def _use_direct_mode():
    """Use direct DB + ensembledata mode (no FastAPI backend needed)."""
    return _has_ensembledata_token() and HAS_ENSEMBLEDATA


def _read_db(platform_filter=None, geo=None, keyword_filter=None, limit=500):
    """Read trends directly from SQLite DB."""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        query = "SELECT platform, topic, growth, keyword, geo, url, extracted_at, extra_data FROM trends WHERE 1=1"
        params = []

        if platform_filter:
            if isinstance(platform_filter, list):
                placeholders = ", ".join(["?"] * len(platform_filter))
                query += f" AND platform IN ({placeholders})"
                params.extend(platform_filter)
            else:
                query += " AND platform = ?"
                params.append(platform_filter)

        if geo and geo != "Global":
            query += " AND (UPPER(geo) = UPPER(?) OR geo = '' OR UPPER(geo) = 'GLOBAL' OR geo IS NULL)"
            params.append(geo)

        if keyword_filter:
            if isinstance(keyword_filter, list):
                placeholders = ", ".join(["?"] * len(keyword_filter))
                query += f" AND keyword IN ({placeholders})"
                params.extend(keyword_filter)

        query += f" ORDER BY extracted_at DESC LIMIT {limit}"
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        records = []
        for row in rows:
            item = {
                "platform": row["platform"],
                "topic": row["topic"],
                "growth": row["growth"],
                "keyword": row["keyword"],
                "geo": row["geo"],
                "url": row["url"],
                "extracted_at": row["extracted_at"],
            }
            extra = row["extra_data"]
            if extra:
                try:
                    item.update(json.loads(extra))
                except Exception:
                    pass
            records.append(item)
        return pd.DataFrame(records)
    except Exception as e:
        print(f"DB read error: {e}")
        return pd.DataFrame()


def _read_errors(platform=None):
    """Read scrape errors directly from SQLite DB."""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT platform, keyword, url, status, reason, extracted_at FROM scrape_errors"
        params = []
        if platform:
            query += " WHERE platform = ?"
            params.append(platform)
        query += " ORDER BY extracted_at DESC"
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def _process_df(df, niche_name=None):
    """Apply analytics processing and niche filtering."""
    if df.empty:
        return df
    if niche_name and _niche:
        df = _niche.filter_by_niche(df, niche_name)
    if not df.empty and _analytics:
        df = _analytics.process_trends(df)
    return df


class APIClient:
    def __init__(self):
        self.base_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
        self.direct = _use_direct_mode()

    def _get_niche_keywords(self, niche_name):
        if _niche and niche_name:
            return _niche.get_niche_keywords(niche_name)
        return []

    def get_niches(self):
        if self.direct and _niche:
            return _niche.get_available_niches()
        try:
            response = requests.get(f"{self.base_url}/niches", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if _niche:
                return _niche.get_available_niches()
            return ["Survival", "Health", "Preppers", "Sustainability", "Homesteading"]

    def get_niche_keywords(self, niche_name):
        if self.direct and _niche:
            return _niche.get_niche_keywords(niche_name)
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
        """Trigger scraping — uses ensembledata directly if available, else calls FastAPI."""
        if self.direct:
            return self._direct_scrape(niche_name, geo, scraper_type)
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
            # Fallback to direct if API is down
            if HAS_ENSEMBLEDATA and _has_ensembledata_token():
                return self._direct_scrape(niche_name, geo, scraper_type)
            st.error(f"Scrape request failed: {e}")
            return False

    def _direct_scrape(self, niche_name, geo, scraper_type):
        """Run ensembledata scrapers directly (no FastAPI needed)."""
        keywords = self._get_niche_keywords(niche_name)
        if not keywords:
            keywords = [niche_name]
        try:
            if scraper_type == "all":
                run_all_ensembledata(keywords, geo=geo)
            elif scraper_type == "TikTok":
                scrape_tiktok(keywords, geo=geo)
            elif scraper_type == "Instagram":
                scrape_instagram(keywords, geo=geo)
            elif scraper_type == "youtube":
                scrape_youtube(keywords, geo=geo)
            elif scraper_type == "Threads":
                scrape_threads(keywords, geo=geo)
            elif scraper_type == "reddit":
                scrape_reddit(["all"], geo=geo)
            elif scraper_type == "google_trends":
                # Run all ensembledata scrapers as substitute
                run_all_ensembledata(keywords, geo=geo)
            else:
                run_all_ensembledata(keywords, geo=geo)
            return True
        except Exception as e:
            st.error(f"Direct scrape failed: {e}")
            return False

    @st.cache_data(ttl=600)
    def get_trends(_self, geo="US", niche_name=None):
        if _self.direct:
            platforms = [
                "Google Interest", "Google Regions", "Google Related Queries",
                "Google Related Topics", "TikTok", "Instagram", "YouTube",
                "Threads", "Reddit", "HackerNews", "News",
            ]
            df = _read_db(platform_filter=platforms, geo=geo)
            return _process_df(df, niche_name)
        try:
            params = {"geo": geo}
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/trends", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            # Fallback to direct DB
            df = _read_db(geo=geo)
            return _process_df(df, niche_name)

    @st.cache_data(ttl=3600)
    def get_trending_now(_self, geo="US", trend_type="daily"):
        if _self.direct:
            df = _read_db(platform_filter="Google Trends", geo=geo)
            return _process_df(df)
        try:
            params = {"geo": geo, "trend_type": trend_type}
            response = requests.get(f"{_self.base_url}/trending_now", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            df = _read_db(platform_filter="Google Trends", geo=geo)
            return _process_df(df)

    @st.cache_data(ttl=3600)
    def get_youtube_videos(_self, niche_name=None, geo="US", limit=500):
        """Read from the dedicated youtube_videos table."""
        if not os.path.exists(DB_PATH):
            return pd.DataFrame()
        try:
            conn = sqlite3.connect(DB_PATH)
            query = """
                SELECT video_id, title, description, search_keyword, geo,
                       channel_title, channel_id, published, duration, url,
                       thumbnail_url, tags, language,
                       view_count, like_count, dislike_count, comment_count,
                       favorite_count, engagement_total,
                       extracted_at
                FROM youtube_videos WHERE 1=1
            """
            params = []
            if geo and geo != "Global":
                query += " AND (UPPER(geo) = UPPER(?) OR geo = '' OR UPPER(geo) = 'GLOBAL' OR geo IS NULL)"
                params.append(geo)
            if niche_name:
                keywords = _self._get_niche_keywords(niche_name)
                if keywords:
                    placeholders = ", ".join(["?"] * len(keywords))
                    query += f" AND search_keyword IN ({placeholders})"
                    params.extend(keywords)
            query += f" ORDER BY view_count DESC LIMIT {limit}"
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            if 'tags' in df.columns:
                df['tags'] = df['tags'].apply(lambda x: ', '.join(json.loads(x)) if x and x.startswith('[') else (x or ''))
            return df
        except Exception as e:
            print(f"youtube_videos read error: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def get_youtube_trends(_self, niche_name, geo="US"):
        """Fallback: read YouTube from generic trends table."""
        if _self.direct:
            keywords = _self._get_niche_keywords(niche_name)
            df = _read_db(platform_filter="YouTube", geo=geo, keyword_filter=keywords if keywords else None)
            return _process_df(df, niche_name)
        try:
            params = {"niche_name": niche_name, "geo": geo}
            response = requests.get(f"{_self.base_url}/youtube_trends", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            df = _read_db(platform_filter="YouTube", geo=geo)
            return _process_df(df, niche_name)

    @st.cache_data(ttl=3600)
    def get_instagram_posts(_self, niche_name=None, geo="US", limit=500):
        """Read from the dedicated instagram_posts table."""
        if not os.path.exists(DB_PATH):
            return pd.DataFrame()
        try:
            conn = sqlite3.connect(DB_PATH)
            query = """
                SELECT post_pk, shortcode, search_keyword, geo,
                       caption, media_type, url, thumbnail_url, taken_at,
                       location_name,
                       username, full_name, follower_count, is_verified,
                       like_count, comment_count, share_count, save_count,
                       video_view_count, video_play_count,
                       engagement_total, hashtags,
                       extracted_at
                FROM instagram_posts WHERE 1=1
            """
            params = []
            if geo and geo != "Global":
                query += " AND (UPPER(geo) = UPPER(?) OR geo = '' OR UPPER(geo) = 'GLOBAL' OR geo IS NULL)"
                params.append(geo)
            if niche_name:
                keywords = _self._get_niche_keywords(niche_name)
                if keywords:
                    placeholders = ", ".join(["?"] * len(keywords))
                    query += f" AND search_keyword IN ({placeholders})"
                    params.extend(keywords)
            query += f" ORDER BY like_count DESC LIMIT {limit}"
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            if 'taken_at' in df.columns:
                df['posted'] = pd.to_datetime(df['taken_at'], unit='s', errors='coerce').dt.strftime('%Y-%m-%d %H:%M')
            if 'hashtags' in df.columns:
                df['hashtags'] = df['hashtags'].apply(lambda x: ', '.join(json.loads(x)) if x and x.startswith('[') else (x or ''))
            return df
        except Exception as e:
            print(f"instagram_posts read error: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def get_reddit_posts(_self, niche_name=None, geo="US", limit=500):
        """Read from the dedicated reddit_posts table."""
        if not os.path.exists(DB_PATH):
            return pd.DataFrame()
        try:
            conn = sqlite3.connect(DB_PATH)
            query = """
                SELECT post_id, title, selftext, search_keyword, geo,
                       url, permalink, domain,
                       subreddit, author,
                       score, upvote_ratio, num_comments, num_crossposts, total_awards,
                       engagement_total, link_flair_text,
                       created_utc, extracted_at
                FROM reddit_posts WHERE 1=1
            """
            params = []
            if geo and geo != "Global":
                query += " AND (UPPER(geo) = UPPER(?) OR geo = '' OR UPPER(geo) = 'GLOBAL' OR geo IS NULL)"
                params.append(geo)
            if niche_name:
                keywords = _self._get_niche_keywords(niche_name)
                if keywords:
                    kw_placeholders = ", ".join(["?"] * len(keywords))
                    query += f" AND search_keyword IN ({kw_placeholders})"
                    params.extend(keywords)
            query += f" ORDER BY score DESC LIMIT {limit}"
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            if 'created_utc' in df.columns:
                df['posted'] = pd.to_datetime(df['created_utc'], unit='s', errors='coerce').dt.strftime('%Y-%m-%d %H:%M')
            return df
        except Exception as e:
            print(f"reddit_posts read error: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def get_threads_posts(_self, niche_name=None, geo="US", limit=500):
        """Read from the dedicated threads_posts table."""
        if not os.path.exists(DB_PATH):
            return pd.DataFrame()
        try:
            conn = sqlite3.connect(DB_PATH)
            query = """
                SELECT post_code, search_keyword, geo,
                       caption, url, taken_at, media_type,
                       username, full_name, follower_count, is_verified,
                       like_count, reply_count, repost_count, quote_count, share_count,
                       engagement_total,
                       extracted_at
                FROM threads_posts WHERE 1=1
            """
            params = []
            if geo and geo != "Global":
                query += " AND (UPPER(geo) = UPPER(?) OR geo = '' OR UPPER(geo) = 'GLOBAL' OR geo IS NULL)"
                params.append(geo)
            if niche_name:
                keywords = _self._get_niche_keywords(niche_name)
                if keywords:
                    placeholders = ", ".join(["?"] * len(keywords))
                    query += f" AND search_keyword IN ({placeholders})"
                    params.extend(keywords)
            query += f" ORDER BY like_count DESC LIMIT {limit}"
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            if 'taken_at' in df.columns:
                df['posted'] = pd.to_datetime(df['taken_at'], unit='s', errors='coerce').dt.strftime('%Y-%m-%d %H:%M')
            return df
        except Exception as e:
            print(f"threads_posts read error: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=600)
    def get_hackernews_trends(_self, niche_name=None, geo="US"):
        if _self.direct:
            df = _read_db(platform_filter="HackerNews", geo=geo)
            return _process_df(df, niche_name)
        try:
            params = {"geo": geo}
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/hackernews_trends", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            df = _read_db(platform_filter="HackerNews", geo=geo)
            return _process_df(df, niche_name)

    @st.cache_data(ttl=600)
    def get_reddit_trends(_self, subreddit='all', trend_type='hot', niche_name=None, geo="US"):
        """Fallback: read Reddit from generic trends table."""
        if _self.direct:
            df = _read_db(platform_filter="Reddit", geo=geo)
            return _process_df(df, niche_name)
        try:
            params = {'subreddit': subreddit, 'trend_type': trend_type, 'geo': geo}
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/reddit_trends", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            df = _read_db(platform_filter="Reddit", geo=geo)
            return _process_df(df, niche_name)

    @st.cache_data(ttl=600)
    def get_news_trends(_self, query='niche', niche_name=None, geo="US"):
        if _self.direct:
            df = _read_db(platform_filter="News", geo=geo)
            return _process_df(df, niche_name)
        try:
            params = {'query': query, 'geo': geo}
            if niche_name:
                params["niche_name"] = niche_name
            response = requests.get(f"{_self.base_url}/news_trends", params=params, timeout=30)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            df = _read_db(platform_filter="News", geo=geo)
            return _process_df(df, niche_name)

    @st.cache_data(ttl=3600)
    def get_tiktok_videos(_self, niche_name=None, geo="US", limit=500):
        """Read from the dedicated tiktok_videos table."""
        if not os.path.exists(DB_PATH):
            return pd.DataFrame()
        try:
            conn = sqlite3.connect(DB_PATH)
            query = """
                SELECT aweme_id, description, search_keyword, geo, region,
                       create_time, duration, share_url,
                       digg_count, comment_count, share_count, play_count,
                       download_count, collect_count, engagement_total,
                       author_unique_id, author_nickname, author_follower_count,
                       author_verified,
                       music_title, music_author,
                       hashtags, video_ratio,
                       extracted_at
                FROM tiktok_videos WHERE 1=1
            """
            params = []
            if geo and geo != "Global":
                query += " AND (UPPER(geo) = UPPER(?) OR geo = '' OR UPPER(geo) = 'GLOBAL' OR geo IS NULL)"
                params.append(geo)
            if niche_name:
                keywords = _self._get_niche_keywords(niche_name)
                if keywords:
                    placeholders = ", ".join(["?"] * len(keywords))
                    query += f" AND search_keyword IN ({placeholders})"
                    params.extend(keywords)
            query += f" ORDER BY play_count DESC LIMIT {limit}"
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            # Parse create_time to human-readable
            if 'create_time' in df.columns:
                df['created'] = pd.to_datetime(df['create_time'], unit='s', errors='coerce').dt.strftime('%Y-%m-%d %H:%M')
            # Parse hashtags JSON
            if 'hashtags' in df.columns:
                df['hashtags'] = df['hashtags'].apply(lambda x: ', '.join(json.loads(x)) if x else '')
            return df
        except Exception as e:
            print(f"tiktok_videos read error: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=60)
    def get_scrape_errors(_self, platform=None):
        if _self.direct:
            return _read_errors(platform)
        try:
            params = {}
            if platform:
                params['platform'] = platform
            response = requests.get(f"{_self.base_url}/scrape_errors", params=params, timeout=10)
            response.raise_for_status()
            return pd.DataFrame(response.json().get("data", []))
        except Exception:
            return _read_errors(platform)

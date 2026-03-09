import os
import pandas as pd
from pytrends.request import TrendReq
import requests
from bs4 import BeautifulSoup
import time
import random
from dotenv import load_dotenv
from GoogleNews import GoogleNews

load_dotenv()

class TrendCollector:
    def __init__(self):
        self.pytrends = TrendReq(hl='en-US', tz=360)
        
    def get_google_trends(self):
        """Fetches daily search trends from Google Trends."""
        try:
            df = self.pytrends.trending_searches(pn='united_states')
            trends = df[0].tolist()
            return [{"platform": "Google Trends", "topic": t, "growth": random.randint(50, 500)} for t in trends]
        except Exception as e:
            print(f"Error fetching Google Trends: {e}")
            return []

    def get_google_news_trends(self):
        """Fetches latest news trends using GoogleNews library."""
        try:
            googlenews = GoogleNews(lang='en', period='1d')
            googlenews.search('trending')
            results = googlenews.result()
            return [{"platform": "Google News", "topic": item['title'], "growth": random.randint(50, 500)} for item in results[:10]]
        except Exception as e:
            print(f"Error fetching Google News: {e}")
            return []

    def get_youtube_trends(self):
        """Scrapes YouTube trending page (basic implementation)."""
        try:
            url = "https://www.youtube.com/feed/trending"
            # In a real scenario, we might need a headless browser or YouTube API
            # For this MVP, we provide placeholders
            topics = ["New Movie Trailer", "Tech Review", "Viral Challenge", "Cooking Tutorial", "Gaming Highlight"]
            return [{"platform": "YouTube", "topic": t, "growth": random.randint(200, 2000)} for t in topics]
        except Exception as e:
            print(f"Error fetching YouTube Trends: {e}")
            return []

    def get_twitter_trends(self):
        """Mock implementation for Twitter/X trends."""
        topics = ["#AppleEvent", "#CryptoMarket", "#F1", "#BreakingNews", "#TechTrends"]
        return [{"platform": "X/Twitter", "topic": t, "growth": random.randint(500, 5000)} for t in topics]

    def collect_all(self):
        all_trends = []
        all_trends.extend(self.get_google_trends())
        all_trends.extend(self.get_youtube_trends())
        all_trends.extend(self.get_twitter_trends())
        all_trends.extend(self.get_google_news_trends())
        return pd.DataFrame(all_trends)

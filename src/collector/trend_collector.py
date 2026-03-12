import os
import pandas as pd
import json
import subprocess
import sys
import re

class TrendCollector:
    def __init__(self):
        # Define the path to Scrapy output relative to project root
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.scrapy_output_path = os.path.join(base_dir, "src", "scrapers", "google_trends_scraper", "trends_output.jsonl")
        self.db_path = os.path.join(base_dir, "src", "collector", "trends.db")
        
    def get_db_trends(self, geo=None, include_trending_now=False, include_youtube=False, include_social=False, include_hackernews=False, include_reddit=False, include_news=False, include_stackexchange=False):
        """Reads trends from SQLite database."""
        import sqlite3
        import json

        if not os.path.exists(self.db_path):
            # Fallback to JSONL if DB doesn't exist yet
            return self.get_scrapy_trends(geo, include_trending_now, include_youtube, include_social, include_hackernews, include_reddit, include_news, include_stackexchange)

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = "SELECT * FROM trends WHERE 1=1"
            params = []

            # Platform filtering
            excluded_platforms = []
            if not include_trending_now:
                excluded_platforms.append('Google Trends')
            if not include_youtube:
                excluded_platforms.append('YouTube')
            if not include_social:
                excluded_platforms.extend(['X (Twitter)', 'Threads', 'Instagram'])
            if not include_hackernews:
                excluded_platforms.append('HackerNews')
            if not include_reddit:
                excluded_platforms.append('Reddit')
            if not include_news:
                excluded_platforms.append('News')
            if not include_stackexchange:
                excluded_platforms.append('StackExchange')
            
            if excluded_platforms:
                placeholders = ', '.join(['?'] * len(excluded_platforms))
                query += f" AND platform NOT IN ({placeholders})"
                params.extend(excluded_platforms)

            # Geo filtering (only for Google platforms that have geo)
            if geo is not None:
                # We want trends that either have no geo (Global) OR match requested geo
                # But wait, original logic was:
                # if data_type not in [...] and geo is not None:
                #     if str(item_geo).upper() != str(geo).upper(): continue
                
                google_platforms = ['Google Trends', 'Google Related Queries', 'Google Related Topics', 'Google Interest', 'Google Regions']
                gp_placeholders = ', '.join(['?'] * len(google_platforms))
                query += f" AND (platform NOT IN ({gp_placeholders}) OR UPPER(geo) = UPPER(?) OR geo = '' OR geo = 'Global' OR geo IS NULL)"
                params.extend(google_platforms)
                params.append(geo)

            query += " ORDER BY extracted_at DESC"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            trends = []
            seen = set()
            for row in rows:
                platform = row['platform']
                topic = row['topic']
                
                if (platform, topic) in seen:
                    continue
                
                item = {
                    "platform": platform,
                    "topic": topic,
                    "growth": row['growth'],
                    "keyword": row['keyword'],
                    "geo": row['geo'],
                    "url": row['url'],
                    "extracted_at": row['extracted_at']
                }
                
                # Expand extra_data
                if row['extra_data']:
                    try:
                        extra = json.loads(row['extra_data'])
                        item.update(extra)
                    except:
                        pass
                
                trends.append(item)
                seen.add((platform, topic))
                
            return trends
        except Exception as e:
            print(f"Error reading trends from DB: {e}")
            # Fallback to Scrapy
            return self.get_scrapy_trends(geo, include_trending_now, include_youtube, include_social, include_hackernews, include_reddit, include_news, include_stackexchange)

    def get_scrapy_trends(self, geo=None, include_trending_now=False, include_youtube=False, include_social=False, include_hackernews=False, include_reddit=False, include_news=False, include_stackexchange=False):
        """Reads trends from Scrapy output JSONL file, optionally filtered by geo."""
        trends = []
        if not os.path.exists(self.scrapy_output_path):
            print(f"Scrapy output file not found at {self.scrapy_output_path}")
            return []

        try:
            # We use a set of seen (platform, topic) to avoid duplicates if the file has historical data
            seen = set()
            with open(self.scrapy_output_path, 'r', encoding='utf-8') as f:
                # Read all lines but process them in reverse to get the latest first
                lines = f.readlines()
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    
                    data_type = item.get('data_type')
                    
                    # Apply geo filter if provided (case-insensitive)
                    # For YouTube, Social, HackerNews, Reddit, News and StackExchange, we bypass geo filtering as it's typically Global
                    if data_type not in ['youtube_trends', 'x_trends', 'threads_trends', 'instagram_trends', 'hackernews_trends', 'reddit_trends', 'news_trends', 'stackexchange_trends'] and geo is not None:
                        item_geo = item.get('geo')
                        if item_geo is None:
                            item_geo = ""
                        if str(item_geo).upper() != str(geo).upper():
                            continue
                    
                    # Skip trending_searches if not explicitly requested
                    if data_type == 'trending_searches' and not include_trending_now:
                        continue
                        
                    # Skip youtube_trends if not explicitly requested
                    if data_type == 'youtube_trends' and not include_youtube:
                        continue
                        
                    # Skip social trends if not explicitly requested
                    if data_type in ['x_trends', 'threads_trends', 'instagram_trends'] and not include_social:
                        continue

                    # Skip hackernews trends if not explicitly requested
                    if data_type == 'hackernews_trends' and not include_hackernews:
                        continue

                    # Skip reddit trends if not explicitly requested
                    if data_type == 'reddit_trends' and not include_reddit:
                        continue

                    # Skip news trends if not explicitly requested
                    if data_type == 'news_trends' and not include_news:
                        continue

                    # Skip stackexchange trends if not explicitly requested
                    if data_type == 'stackexchange_trends' and not include_stackexchange:
                        continue

                    results = item.get('results', [])
                    keyword = item.get('keyword', 'Unknown')
                    
                    if data_type == 'trending_searches':
                        for res in results:
                            query = res.get('query') or res.get('title')
                            if query and ("Google Trends", query) not in seen:
                                trends.append({
                                    "platform": "Google Trends",
                                    "topic": query,
                                    "growth": self._parse_traffic(res.get('traffic')) or 500,
                                    "keyword": keyword,
                                    "extracted_at": item.get('extracted_at')
                                })
                                seen.add(("Google Trends", query))
                    elif data_type in ['related_queries', 'related_topics']:
                        platform = f"Google {data_type.replace('_', ' ').title()}"
                        for res in results:
                            query = res.get('query') or res.get('topic')
                            if query and (platform, query) not in seen:
                                # 'value' from Google can be an int (0-100) or 'Breakout'
                                val = res.get('value')
                                if val == 'Breakout':
                                    growth = 5000 # Assigned breakout value
                                elif isinstance(val, (int, float)):
                                    growth = val * 10 # Scale to 0-1000 range for consistency
                                else:
                                    growth = 250 # Default middle-ground growth
                                
                                trends.append({
                                    "platform": platform,
                                    "topic": query,
                                    "growth": growth,
                                    "keyword": keyword,
                                    "extracted_at": item.get('extracted_at')
                                })
                                seen.add((platform, query))
                    elif data_type == 'interest_over_time':
                        topic = item.get('keyword')
                        if results and topic and ("Google Interest", topic) not in seen:
                            last_point = results[-1]
                            # value for interest_over_time is a list if there are multiple comparison items
                            vals = last_point.get('value', [0])
                            avg_value = sum(vals) / len(vals) if isinstance(vals, list) and vals else 0
                            trends.append({
                                "platform": "Google Interest",
                                "topic": topic,
                                "growth": avg_value * 20, # Scale to 0-2000 range
                                "keyword": keyword,
                                "extracted_at": item.get('extracted_at')
                            })
                            seen.add(("Google Interest", topic))
                    elif data_type == 'youtube_trends':
                        for res in results:
                            title = res.get('title')
                            if title and ("YouTube", title) not in seen:
                                trends.append({
                                    "platform": "YouTube",
                                    "topic": title,
                                    "growth": self._parse_views(res.get('views')) or 0,
                                    "keyword": keyword,
                                    "url": res.get('url'),
                                    "published": res.get('published'),
                                    "extracted_at": item.get('extracted_at')
                                })
                                seen.add(("YouTube", title))
                    elif data_type in ['x_trends', 'threads_trends', 'instagram_trends']:
                        platform_map = {
                            'x_trends': 'X (Twitter)',
                            'threads_trends': 'Threads',
                            'instagram_trends': 'Instagram'
                        }
                        platform = platform_map.get(data_type)
                        for res in results:
                            topic = res.get('topic')
                            if topic and (platform, topic) not in seen:
                                trends.append({
                                    "platform": platform,
                                    "topic": topic,
                                    "growth": res.get('engagement', 0),
                                    "keyword": keyword,
                                    "posts": res.get('posts'),
                                    "replies": res.get('replies'),
                                    "url": res.get('url'),
                                    "extracted_at": item.get('extracted_at')
                                })
                                seen.add((platform, topic))
                    elif data_type == 'hackernews_trends':
                        for res in results:
                            topic = res.get('title')
                            if topic and ("HackerNews", topic) not in seen:
                                trends.append({
                                    "platform": "HackerNews",
                                    "topic": topic,
                                    "growth": res.get('score', 0) * 10, # Score as a proxy for growth
                                    "engagement": res.get('descendants', 0) * 5, # Comments as engagement proxy
                                    "url": res.get('url'),
                                    "author": res.get('by'),
                                    "extracted_at": item.get('extracted_at')
                                })
                                seen.add(("HackerNews", topic))
                    elif data_type == 'reddit_trends':
                        for res in results:
                            topic = res.get('title')
                            if topic and ("Reddit", topic) not in seen:
                                trends.append({
                                    "platform": "Reddit",
                                    "topic": topic,
                                    "growth": res.get('score', 0) * 5, # Score as growth proxy
                                    "engagement": res.get('num_comments', 0) * 10, # Comments as engagement proxy
                                    "subreddit": res.get('subreddit'),
                                    "url": res.get('url'),
                                    "extracted_at": item.get('extracted_at')
                                })
                                seen.add(("Reddit", topic))
                    elif data_type == 'news_trends':
                        for res in results:
                            topic = res.get('title')
                            if topic and ("News", topic) not in seen:
                                trends.append({
                                    "platform": "News",
                                    "topic": topic,
                                    "growth": res.get('popularity', 50) * 10,
                                    "source": res.get('source'),
                                    "url": res.get('url'),
                                    "extracted_at": item.get('extracted_at')
                                })
                                seen.add(("News", topic))
                    elif data_type == 'stackexchange_trends':
                        for res in results:
                            topic = res.get('title')
                            if topic and ("StackExchange", topic) not in seen:
                                trends.append({
                                    "platform": "StackExchange",
                                    "topic": topic,
                                    "growth": res.get('score', 0) * 20,
                                    "engagement": res.get('view_count', 0) / 10,
                                    "tags": res.get('tags'),
                                    "url": res.get('url'),
                                    "extracted_at": item.get('extracted_at')
                                })
                                seen.add(("StackExchange", topic))
                    elif data_type == 'interest_by_region':
                        topic = item.get('keyword')
                        # Filtering only regions with significant interest (e.g. value > 0)
                        regions_with_interest = [res for res in results if res.get('value', [0])[0] > 0]
                        if topic and ("Google Regions", topic) not in seen:
                            trends.append({
                                "platform": "Google Regions",
                                "topic": topic,
                                "growth": len(regions_with_interest) * 10, # Number of regions as a 'growth' proxy for spread
                                "spread": len(regions_with_interest),
                                "keyword": keyword,
                                "extracted_at": item.get('extracted_at')
                            })
                            seen.add(("Google Regions", topic))
            return trends
        except Exception as e:
            print(f"Error reading Scrapy trends: {e}")
            return []

    def _parse_traffic(self, traffic_str):
        """Helper to parse strings like '50K+' or '1M+' into numbers."""
        if not traffic_str or not isinstance(traffic_str, str):
            return None
        try:
            traffic_str = traffic_str.replace('+', '').replace(',', '')
            if 'K' in traffic_str:
                return int(float(traffic_str.replace('K', '')) * 1000)
            if 'M' in traffic_str:
                return int(float(traffic_str.replace('M', '')) * 1000000)
            return int(traffic_str)
        except:
            return None

    def _parse_views(self, views_str):
        """Parses YouTube view count strings like '1.2M views' or '500K views'."""
        if not views_str or not isinstance(views_str, str):
            return None
        try:
            # Extract only the number and the multiplier (K, M)
            # Remove 'views', 'vizionări', etc.
            match = re.search(r'([\d.,]+)\s*([KM]?)', views_str.upper())
            if match:
                num_str = match.group(1).replace(',', '')
                multiplier = match.group(2)
                
                # Handle cases with '.' as decimal separator
                val = float(num_str)
                if multiplier == 'K':
                    return int(val * 1000)
                if multiplier == 'M':
                    return int(val * 1000000)
                return int(val)
            return None
        except:
            return None

    def run_google_trends_scraper(self, keywords, geo="US", timeframe="today 12-m", category=0):
        """Runs the Scrapy Google Trends spider for specific keywords."""
        return self._run_scraper("google_trends", keywords=keywords, geo=geo, timeframe=timeframe, category=category)

    def run_trending_now_scraper(self, geo="US", trend_type="daily"):
        """Runs the Scrapy Trending Now spider."""
        return self._run_scraper("trending_now", geo=geo, type=trend_type)

    def _run_scraper(self, spider_name, **kwargs):
        """Helper to run a Scrapy spider with given arguments."""
        # Use absolute path for the scraper directory
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        project_dir = os.path.join(base_dir, "src", "scrapers", "google_trends_scraper")
        
        cmd = [sys.executable, "-m", "scrapy", "crawl", spider_name]
        
        for key, value in kwargs.items():
            if key == "keywords" and isinstance(value, list):
                value = ",".join(value)
            cmd.extend(["-a", f"{key}={value}"])

        try:
            print(f"Running scraper command: {' '.join(cmd)} in {project_dir}")
            
            result = subprocess.run(
                cmd,
                cwd=project_dir,
                capture_output=False,
                text=True
            )
            
            if result.returncode != 0:
                print(f"Scraper {spider_name} failed with return code {result.returncode}")
                return False
            
            print(f"Scraper {spider_name} completed successfully.")
            return True
        except Exception as e:
            print(f"Failed to run Scrapy scraper {spider_name}: {e}")
            return False

    def run_youtube_trends_scraper(self, keywords):
        """Runs the Scrapy YouTube Trends spider for specific keywords."""
        return self._run_scraper("youtube_trends", keywords=keywords)

    def run_social_trends_scraper(self, platform, keywords):
        """Runs the Scrapy Social Trends spider for a specific platform."""
        return self._run_scraper("social_trends", platform=platform, keywords=keywords)

    def run_hackernews_scraper(self, keywords=None):
        """Runs the Scrapy HackerNews spider."""
        return self._run_scraper("hackernews", keywords=keywords)

    def run_reddit_scraper(self, subreddit='all', trend_type='hot', keywords=None):
        """Runs the Scrapy Reddit spider."""
        return self._run_scraper("reddit", subreddit=subreddit, trend_type=trend_type, keywords=keywords)

    def run_news_scraper(self, query='niche', api_key=None):
        """Runs the Scrapy NewsAPI spider."""
        return self._run_scraper("newsapi", q=query, api_key=api_key)

    def run_stackexchange_scraper(self, site='stackoverflow', sort='hot', keywords=None):
        """Runs the Scrapy StackExchange spider."""
        return self._run_scraper("stackexchange", site=site, sort=sort, keywords=keywords)

    def run_niche_comprehensive_scrape(self, niche_name, keywords, geo="US", timeframe="today 12-m", category=0):
        """Triggers all scrapers for a specific niche in sequence."""
        print(f"Starting comprehensive scrape for niche: {niche_name}")
        
        # We'll use a subset of keywords for more performant scraping across many platforms
        limited_keywords = keywords[:3] if len(keywords) > 3 else keywords
        
        # 1. Google Trends (the core scraper)
        self.run_google_trends_scraper(keywords, geo=geo, timeframe=timeframe, category=category)
        
        # 2. YouTube
        self.run_youtube_trends_scraper(limited_keywords)
        
        # 3. Social
        self.run_social_trends_scraper("X", limited_keywords)
        self.run_social_trends_scraper("Threads", limited_keywords)
        self.run_social_trends_scraper("Instagram", limited_keywords)
        
        # 4. Reddit
        self.run_reddit_scraper(keywords=limited_keywords)
        
        # 5. HackerNews
        self.run_hackernews_scraper(keywords=limited_keywords)
        
        # 6. StackExchange
        self.run_stackexchange_scraper(keywords=limited_keywords)
        
        # 7. NewsAPI (just use the niche name for NewsAPI)
        self.run_news_scraper(query=niche_name)
        
        print(f"Comprehensive scrape for {niche_name} finished.")
        return True

    def collect_all(self, geo=None, include_trending_now=False, include_youtube=False, include_social=False, include_hackernews=False, include_reddit=False, include_news=False, include_stackexchange=False):
        all_trends = []
        # Prefer DB over JSONL
        all_trends.extend(self.get_db_trends(geo=geo, include_trending_now=include_trending_now, include_youtube=include_youtube, include_social=include_social, include_hackernews=include_hackernews, include_reddit=include_reddit, include_news=include_news, include_stackexchange=include_stackexchange))
        
        if all_trends:
            return pd.DataFrame(all_trends)
        else:
            # Return empty DataFrame with expected columns
            return pd.DataFrame(columns=['platform', 'topic', 'growth', 'keyword', 'extracted_at'])

import os
import pandas as pd
import json
import subprocess
import sys

class TrendCollector:
    def __init__(self):
        # Define the path to Scrapy output relative to project root
        self.scrapy_output_path = os.path.join("src", "scrapers", "google_trends_scraper", "trends_output.jsonl")
        
    def get_scrapy_trends(self):
        """Reads trends from Scrapy output JSONL file."""
        trends = []
        if not os.path.exists(self.scrapy_output_path):
            print(f"Scrapy output file not found at {self.scrapy_output_path}")
            return []

        try:
            # We use a set of seen (platform, topic) to avoid duplicates if the file has historical data
            seen = set()
            with open(self.scrapy_output_path, 'r', encoding='utf-8') as f:
                # Read all lines but process them in reverse to get the latest first if we want,
                # or just use a dict to keep the latest value for each topic.
                lines = f.readlines()
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                        
                    data_type = item.get('data_type')
                    results = item.get('results', [])
                    
                    if data_type == 'trending_searches':
                        for res in results:
                            query = res.get('query') or res.get('title')
                            if query and ("Google Trends", query) not in seen:
                                trends.append({
                                    "platform": "Google Trends",
                                    "topic": query,
                                    "growth": self._parse_traffic(res.get('traffic')) or 500 # Default growth if traffic not parsed
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
                                    "growth": growth
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
                                "growth": avg_value * 20 # Scale to 0-2000 range
                            })
                            seen.add(("Google Interest", topic))
                    elif data_type == 'interest_by_region':
                        topic = item.get('keyword')
                        # Filtering only regions with significant interest (e.g. value > 0)
                        regions_with_interest = [res for res in results if res.get('value', [0])[0] > 0]
                        if topic and ("Google Regions", topic) not in seen:
                            trends.append({
                                "platform": "Google Regions",
                                "topic": topic,
                                "growth": len(regions_with_interest) * 10, # Number of regions as a 'growth' proxy for spread
                                "spread": len(regions_with_interest)
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

    def run_google_trends_scraper(self, keywords, geo="US", timeframe="today 12-m", category=0):
        """Runs the Scrapy Google Trends spider for specific keywords."""
        project_dir = os.path.join("src", "scrapers", "google_trends_scraper")
        # Ensure keywords are comma-separated if it's a list
        if isinstance(keywords, list):
            keywords_str = ",".join(keywords)
        else:
            keywords_str = str(keywords)

        try:
            # We use 'python -m scrapy' to avoid PATH issues with the scrapy executable
            # and run it from the project root.
            cmd = [
                sys.executable, "-m", "scrapy", "crawl", "google_trends",
                "-a", f"keywords={keywords_str}",
                "-a", f"geo={geo}",
                "-a", f"timeframe={timeframe}",
                "-a", f"category={category}"
            ]
            print(f"Running scraper command: {' '.join(cmd)} in {project_dir}")
            
            # Use subprocess.run and capture output for debugging if needed
            # We also want to see the logs in the terminal
            result = subprocess.run(
                cmd,
                cwd=project_dir,
                capture_output=False, # Let it print to stdout/stderr directly
                text=True
            )
            
            if result.returncode != 0:
                print(f"Scraper failed with return code {result.returncode}")
                return False
            
            print("Scraper completed successfully.")
            return True
        except Exception as e:
            print(f"Failed to run Scrapy scraper: {e}")
            return False

    def collect_all(self, geo="US"):
        all_trends = []
        all_trends.extend(self.get_scrapy_trends())
        return pd.DataFrame(all_trends)

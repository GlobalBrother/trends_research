import sys
import os
import pandas as pd

# Ensure the project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.collector.trend_collector import TrendCollector
from src.analytics.analytics_engine import AnalyticsEngine

def main():
    print("--- Starting Reddit Integration Test ---")
    
    # 1. Initialize
    collector = TrendCollector()
    analytics = AnalyticsEngine()
    
    # 2. Run Reddit Scraper
    print("Running Reddit scraper for r/all/hot...")
    if collector.run_reddit_scraper(subreddit='all', trend_type='hot'):
        print("Scraper finished successfully.")
    else:
        print("Scraper failed.")
        return

    # 3. Collect Data (Collector)
    print("Fetching trends including Reddit...")
    raw_data = collector.collect_all(include_reddit=True)
    
    if raw_data.empty:
        print("No raw data found.")
        return

    # Filter to see only Reddit if possible
    reddit_data = raw_data[raw_data['platform'] == 'Reddit']
    print(f"Collected {len(reddit_data)} Reddit trend points.")
    
    if reddit_data.empty:
        print("Reddit data not found in collector output.")
        return
    
    # 4. Process Trends (Processor/TrendEngine/ViralCalc)
    print("Processing trends through Analytics Engine...")
    processed_df = analytics.process_trends(raw_data)
    
    # Filter for Reddit in processed results
    reddit_processed = processed_df[processed_df['platform'] == 'Reddit']
    print(f"Processed {len(reddit_processed)} Reddit trends.")
    
    # 5. Display top trends
    print("\n--- Top 5 Reddit Posts (Viral Factor) ---")
    cols_to_show = ['platform', 'topic', 'growth', 'engagement', 'virality_score']
    # Filter for columns that actually exist in the result
    available_cols = [c for c in cols_to_show if c in reddit_processed.columns]
    print(reddit_processed[available_cols].head(5).to_string(index=False))
    
    print("\n--- Reddit Integration Test Complete ---")

if __name__ == "__main__":
    main()

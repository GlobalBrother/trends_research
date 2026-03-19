import sys
import os
import pandas as pd

# Ensure the project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.collector.trend_collector import TrendCollector
from src.analytics.analytics_engine import AnalyticsEngine

def test_source(collector, analytics, source_name, run_method, collect_key):
    print(f"\n--- Testing {source_name} ---")
    print(f"Running {source_name} scraper...")
    if run_method():
        print(f"{source_name} scraper finished successfully.")
    else:
        print(f"{source_name} scraper failed.")
        return

    print(f"Collecting {source_name} data...")
    raw_data = collector.collect_all(**{collect_key: True})
    
    if raw_data.empty:
        print(f"No raw data found for {source_name}.")
        return

    source_data = raw_data[raw_data['platform'] == source_name]
    print(f"Collected {len(source_data)} {source_name} trend points.")
    
    if source_data.empty:
        print(f"{source_name} data not found in collector output.")
        return
    
    print(f"Processing {source_name} trends...")
    processed_df = analytics.process_trends(raw_data)
    source_processed = processed_df[processed_df['platform'].apply(lambda x: source_name in x if isinstance(x, list) else x == source_name)]
    print(f"Processed {len(source_processed)} {source_name} trends.")
    
    print(f"Top 3 {source_name} trends by virality:")
    print(source_processed[['topic', 'virality_score']].head(3).to_string(index=False))

def main():
    collector = TrendCollector()
    analytics = AnalyticsEngine()
    
    # Test Reddit
    test_source(collector, analytics, "Reddit", 
                lambda: collector.run_reddit_scraper(subreddit='all', trend_type='hot'), 
                'include_reddit')
    
    # Test HackerNews
    test_source(collector, analytics, "HackerNews", 
                collector.run_hackernews_scraper, 
                'include_hackernews')
    
    # Test News
    test_source(collector, analytics, "News", 
                lambda: collector.run_news_scraper(query='technology'), 
                'include_news')

if __name__ == "__main__":
    main()

import sys
import os
import argparse

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from collector.trend_collector import TrendCollector
from niche.niche_discovery import NicheDiscovery

def main():
    parser = argparse.ArgumentParser(description="Standardized Niche Scraper")
    parser.add_argument("--niche", type=str, default="Survival", help="Niche name to scrape (e.g., Survival, Health, All)")
    parser.add_argument("--geo", type=str, default="US", help="Geographic region (e.g., US, Global)")
    parser.add_argument("--all", action="store_true", help="Scrape all available niches")
    
    args = parser.parse_args()
    
    collector = TrendCollector()
    niche_discovery = NicheDiscovery()
    
    if args.all:
        niches_to_scrape = niche_discovery.get_available_niches()
        # Remove "All" if it's in the list to avoid redundant loops
        if "All" in niches_to_scrape:
            niches_to_scrape.remove("All")
    else:
        niches_to_scrape = [args.niche]
    
    for niche_name in niches_to_scrape:
        keywords = niche_discovery.get_niche_keywords(niche_name)
        print(f"\n--- Starting comprehensive scrape for {niche_name} ---")
        print(f"Keywords: {keywords}")
        
        success = collector.run_niche_comprehensive_scrape(
            niche_name=niche_name,
            keywords=keywords,
            geo=args.geo
        )
        
        if success:
            print(f"Scrape for {niche_name} completed successfully.")
        else:
            print(f"Scrape for {niche_name} failed.")

if __name__ == "__main__":
    main()

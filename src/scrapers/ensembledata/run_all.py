"""
Run all ensembledata scrapers for a set of keywords.

Usage:
    python run_all.py --keywords "Survival,Health,Fitness"
    python run_all.py --keywords "AI,Machine Learning" --geo US --subreddits "artificial,MachineLearning"
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from tiktok_scraper import scrape_tiktok
from instagram_scraper import scrape_instagram
from youtube_scraper import scrape_youtube
from reddit_scraper import scrape_reddit
from threads_scraper import scrape_threads


def run_all(keywords, geo="Global", subreddits=None, tiktok_period="30",
            youtube_depth=1, youtube_period="month", reddit_sort="hot", reddit_period="day"):
    """Run all ensembledata platform scrapers."""
    print(f"=== Ensembledata scrape: keywords={keywords}, geo={geo} ===\n")

    scrape_tiktok(keywords, geo=geo, period=tiktok_period)
    scrape_instagram(keywords, geo=geo)
    scrape_youtube(keywords, geo=geo, depth=youtube_depth, period=youtube_period)
    scrape_threads(keywords, geo=geo)

    subs = subreddits or ["all"]
    scrape_reddit(subs, geo=geo, sort=reddit_sort, period=reddit_period)

    print("\n=== All ensembledata scrapers finished ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run all ensembledata scrapers")
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords")
    parser.add_argument("--geo", default="Global")
    parser.add_argument("--subreddits", default=None, help="Comma-separated subreddit names")
    parser.add_argument("--tiktok-period", default="30")
    parser.add_argument("--youtube-depth", type=int, default=1)
    parser.add_argument("--youtube-period", default="month")
    parser.add_argument("--reddit-sort", default="hot")
    parser.add_argument("--reddit-period", default="day")
    args = parser.parse_args()

    kws = [k.strip() for k in args.keywords.split(",")]
    subs = [s.strip() for s in args.subreddits.split(",")] if args.subreddits else None
    run_all(kws, geo=args.geo, subreddits=subs, tiktok_period=args.tiktok_period,
            youtube_depth=args.youtube_depth, youtube_period=args.youtube_period,
            reddit_sort=args.reddit_sort, reddit_period=args.reddit_period)

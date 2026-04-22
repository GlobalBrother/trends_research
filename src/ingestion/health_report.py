import argparse
import json

from .service import IngestionService


def main():
    parser = argparse.ArgumentParser(description="Print daily scrape health summary.")
    parser.add_argument("--source", default=None)
    parser.add_argument("--days", type=int, default=1)
    args = parser.parse_args()

    service = IngestionService()
    report = service.daily_health_report(source=args.source, days=args.days)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

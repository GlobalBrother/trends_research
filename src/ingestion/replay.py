import argparse
import json

from .service import IngestionService


def main():
    parser = argparse.ArgumentParser(description="Replay archived source payloads.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    service = IngestionService()
    rows = service.replay_archived_payloads(args.source, limit=args.limit)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()

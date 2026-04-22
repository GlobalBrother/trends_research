import json
import os
from functools import lru_cache


_CONFIG_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "sources")
)


def _config_path(name: str) -> str:
    filename = f"{name.lower().replace(' ', '_')}.json"
    return os.path.join(_CONFIG_DIR, filename)


@lru_cache(maxsize=32)
def load_source_config(name: str) -> dict:
    path = _config_path(name)
    if not os.path.exists(path):
        return {
            "source": name,
            "acquisition_mode": "api",
            "schedule": "daily",
            "backfill_window_hours": 24,
            "granularity": "day",
            "geo_matrix": ["Global"],
            "language_matrix": ["en"],
            "pagination": {"strategy": "none", "persist_cursor": False, "cursor_scope": []},
            "rate_limit": {"retry_times": 3},
        }
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def list_source_configs() -> list[str]:
    if not os.path.isdir(_CONFIG_DIR):
        return []
    return sorted(
        os.path.splitext(entry)[0]
        for entry in os.listdir(_CONFIG_DIR)
        if entry.endswith(".json")
    )

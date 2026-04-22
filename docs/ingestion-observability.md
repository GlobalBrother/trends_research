# Ingestion Observability

This repo now has a shared ingestion reliability layer under `src/ingestion/`.

## Canonical source signal

All scraper sources can persist into `canonical_trend_signals` with:

- `source`
- `entity_type`
- `entity_id`
- `label`
- `country`
- `language`
- `time_bucket_start`
- `granularity`
- metrics: `volume`, `growth_rate`, `rank`, `engagement`, `velocity`
- `sampled_content_refs`
- `retrieved_at`
- `fetch_metadata`
- `idempotency_key`

Evidence rows live in `trend_evidence`.

## Source config

Per-source specs live in `config/sources/*.json`.

These files define:

- acquisition mode
- schedule and backfill window
- geo and language matrices
- pagination/cursor strategy
- retry / quota strategy

## Raw replay

Raw responses are archived in `raw_data_archive` as wrapped JSON payloads.

Replay example:

```powershell
python -m src.ingestion.replay --source YouTube --limit 10
```

## Daily scrape health

Run a daily health summary:

```powershell
python -m src.ingestion.health_report --days 1
```

Each source summary includes:

- fetched / parsed / inserted / deduped / failed counts
- average duplicate ratio
- quota usage
- top error types
- anomaly flag

## Dead letters

Failures that exhaust retries are persisted to `scrape_dead_letters`.

Each row includes:

- source
- scrape run id
- cursor key
- archived payload reference
- error type and message
- retry count

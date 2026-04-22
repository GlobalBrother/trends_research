# Release Checklist

## Pre-Deploy

- Run backend compile check:
  - `python -m py_compile src\api\main.py src\insights\pipeline.py src\db\models.py src\db\migrate.py`
- Run targeted backend tests:
  - `pytest tests/test_insights_pipeline.py tests/test_api.py`
- Run frontend build:
  - `cd frontend && pnpm build`
- Run migration dry run if production schema changed:
  - `python -m src.db.migrate --dry`

## Deploy

- Deploy application image or App Service update.
- Run real migration:
  - `python -m src.db.migrate`
- Trigger cluster refresh:
  - `POST /clusters/refresh`

## Smoke Tests

- `GET /health`
- `GET /trends`
- `GET /clusters`
- `GET /reports/generated`
- `GET /monitoring/platform_health`
- Open frontend pages:
  - `/explorer`
  - `/reports`
  - `/my-ads`

## Post-Deploy Validation

- Confirm `trend_clusters`, `trend_signals`, `trend_insights`, `trend_ad_matches`, `insight_feedback`, `backtest_runs`, and `report_briefs` exist.
- Confirm at least one cluster and one generated report are returned.
- Confirm scraper errors and platform freshness metrics load.
- Confirm feedback submission to `/clusters/{id}/feedback` succeeds.

## Rollback

- Redeploy previous working image or App Service container tag.
- Re-run smoke tests against previous version.
- If schema rollback is required, prefer additive compatibility first; avoid destructive rollback unless a manual DBA plan exists.
- If new snapshot data is suspect, truncate only the derived tables:
  - `trend_clusters`
  - `trend_signals`
  - `trend_insights`
  - `trend_ad_matches`
  - `report_briefs`
  - `backtest_runs`
- Do not delete raw `trends`, `content`, or `ads_insight` data during rollback.

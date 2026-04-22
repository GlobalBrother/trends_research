# Insights API

## GET `/schemas/canonical`

Returns canonical schema metadata for core entities.

Example response:

```json
{
  "trend": {
    "primary_key": "trends.id",
    "fields": ["topic", "keyword", "platform_id", "growth", "geo", "extracted_at", "extra_data"]
  }
}
```

## GET `/monitoring/platform_health`

Returns reliability metrics such as duplicate counts, stale windows, recent scraper errors, API usage, freshness, and source confidence.

Example response:

```json
{
  "generated_at": "2026-04-09T10:00:00",
  "total_trends": 428,
  "duplicate_count": 12,
  "stale_platforms": ["Threads"],
  "platforms": [
    {
      "platform": "Reddit",
      "trend_count": 120,
      "freshness_score": 82.4,
      "source_confidence": 78.0,
      "scrape_error_count_7d": 1,
      "api_units_7d": 34.0
    }
  ]
}
```

## GET `/clusters`

Filters:

- `stage`
- `platform`
- `date`
- `limit`
- `force_refresh`

Example response:

```json
{
  "data": [
    {
      "id": 1,
      "cluster_key": "ai-agents",
      "title": "AI agents",
      "keywords": ["ai", "agents", "automation"],
      "platforms": ["Reddit", "YouTube"],
      "lifecycle_stage": "emerging",
      "confidence_score": 82.0,
      "trend_strength": 88.0,
      "ad_opportunity_score": 74.0
    }
  ]
}
```

## GET `/clusters/{id}`

Returns full cluster detail, structured insight fields, explanations, and feedback summary.

Example response:

```json
{
  "id": 1,
  "title": "AI agents",
  "lifecycle_stage": "emerging",
  "confidence_score": 82.0,
  "insight": {
    "ad_opportunity_score": 74.0,
    "audience_intent": "High conversion intent with active commercial messaging.",
    "creative_angle_candidates": ["Lead with automation", "Show ROI"],
    "platform_fit": [
      { "platform": "Reddit", "supporting_signals": 2, "linked_ads": 1, "fit_score": 34.0 }
    ],
    "ad_timing_window": "Test within the next 3-7 days before the market saturates."
  },
  "feedback_summary": {
    "count": 3,
    "avg_rating": 4.7,
    "useful_votes": 3
  }
}
```

## GET `/clusters/{id}/signals`

Returns supporting signal rows for the cluster.

## GET `/clusters/{id}/ads`

Returns linked ads with deterministic `match_score` and `match_reason`.

Example response:

```json
{
  "data": [
    {
      "match_score": 71.0,
      "match_reason": {
        "keyword_overlap": 0.8,
        "semantic_similarity": 0.64,
        "timing_overlap": 0.92
      },
      "ad": {
        "brand_name": "AgentCo",
        "display_format": "VIDEO",
        "cta_type": "LEARN_MORE"
      }
    }
  ]
}
```

## GET `/clusters/{id}/evidence`

Returns aggregated brands, formats, CTAs, and insight component evidence for the cluster.

## POST `/clusters/{id}/feedback`

Body:

```json
{
  "useful": true,
  "rating": 5,
  "used_in_campaign": false,
  "outcome": "optional",
  "notes": "optional"
}
```

## GET `/reports/generated`

Returns generated `weekly_digest`, `deep_dive`, and `planning_brief` records.

## POST `/reports/generate`

Forces a fresh cluster sync and regenerates report briefs.

## GET `/backtests`

Returns stored backtest runs with proxy precision, recall, and average opportunity score.

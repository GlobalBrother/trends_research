# Canonical Schemas

## trend

- Table: `trends`
- Purpose: Raw platform-level trend signal captured from any scraper.
- Required fields:
  - `id`
  - `platform_id`
  - `topic`
  - `keyword`
  - `growth`
  - `geo`
  - `extracted_at`
- Optional fields:
  - `extra_data`

## content

- Table: `content`
- Purpose: Normalized social/content object used for engagement and creative context.
- Required fields:
  - `id`
  - `platform_id`
  - `external_id`
  - `keyword`
  - `created_at`
- Optional fields:
  - `geo`
  - `text_content`
  - `media_type`
  - `url`
  - `author_id`

## ad

- Table: `ads_insight`
- Purpose: Ad-library creative and metadata used for competitor evidence and opportunity ranking.
- Required fields:
  - `id`
  - `search_keyword`
  - `platform`
  - `title` or `body`
  - `brand_name`
- High-value fields:
  - `display_format`
  - `cta_type`
  - `start_date`
  - `days_active`
  - `performance_score`
  - `performance_score_title`

## brand

- Table: `my_brands`
- Purpose: User-tracked owned or competitor brands.
- Required fields:
  - `id`
  - `brand_name`
  - `added_at`
- Optional fields:
  - `brand_external_id`
  - `brand_logo_url`
  - `brand_active_ads`

## insight

- Tables:
  - `trend_clusters`
  - `trend_signals`
  - `trend_insights`
  - `trend_ad_matches`
  - `insight_feedback`
- Purpose: Cluster-level, explainable, deterministic opportunity layer.
- Core objects:
  - `trend_clusters`: canonical cluster identity, lifecycle, confidence, freshness
  - `trend_signals`: supporting raw signals attached to a cluster
  - `trend_insights`: ranked ad opportunity and explanation payload
  - `trend_ad_matches`: linked competitor ads and scored reasons
  - `insight_feedback`: human usefulness signal and downstream outcome

## Quality Rules

- Duplicate trend rows are measured by `platform + topic + keyword + geo + extracted_at`.
- Missing geo and missing timestamps reduce quality and confidence.
- Platform freshness is based on time since last successful signal.
- Source confidence is penalized by stale windows and recent scraper errors.

## Scoring Rules

- Lifecycle stage is deterministic:
  - `surging`
  - `emerging`
  - `steady`
  - `watchlist`
  - `cooling`
- `ad_opportunity_score` is deterministic and weighted from:
  - `trend_strength`
  - `commercial_relevance`
  - `audience_signal`
  - `creative_reusability`
  - minus `saturation`
  - minus `safety_risk`

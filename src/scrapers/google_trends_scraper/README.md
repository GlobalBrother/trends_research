# Production-Grade Google Trends Scrapy Scraper

This project implements a robust, production-ready Google Trends scraper using Scrapy. It mimics the internal API calls used by the Google Trends web interface to extract data efficiently and reliably.

## Features

- **2-Step Authentication Flow**: Properly handles the `/trends/api/explore` token acquisition followed by specific widget data requests.
- **Support for All Trends**: Interest Over Time, Related Queries, and Related Topics.
- **Configurable**: Easily set keywords, geo-regions, timeframes, and categories via command line.
- **Production-Ready**:
  - Proxy rotation support.
  - Random User-Agent rotation.
  - Built-in retry logic for 429 (Rate Limit) and 5xx errors.
  - Configurable download delays.
- **Clean Architecture**: Separation of concerns using Scrapy Items, Pipelines, and Middlewares.

## Google Trends API Mechanics

Google Trends uses a token-based system:
1.  **Exploration**: A request is made to `/trends/api/explore` with the desired keywords and parameters. The response contains a list of "widgets" (Interest Over Time, Related Queries, etc.), each with a unique `token`.
2.  **Data Retrieval**: To get the actual data, a subsequent request is made to the specific widget endpoint (e.g., `/trends/api/widgetdata/multiline` for time-series) using the acquired `token` and the widget's `request` payload.

*Note: Google Trends API responses are prefixed with `)]}'\n` for security, which this scraper automatically strips.*

## Installation

Ensure you have Scrapy installed:
```bash
pip install scrapy
```

## Running the Scraper

Navigate to the `src/scrapers/google_trends_scraper` directory.

### Basic Run
```bash
scrapy crawl google_trends -a keywords="Bitcoin,Ethereum" -a geo="US" -a timeframe="today 12-m"
```

### Save to JSON Lines
The results are automatically saved to `trends_output.jsonl` via the pipeline.

### Advanced Usage
- **Categories**: Use `-a category=7` (7 is Finance).
- **Geography**: Use `-a geo="GB"` for United Kingdom.
- **Timeframes**: `today 1-m`, `now 7-d`, `today 5-y`.

## Configuration

- **Proxies**: Add your proxy list to `google_trends/settings.py` in the `PROXY_LIST` variable.
- **Database**: A placeholder `PostgreSQLPipeline` is provided in `pipelines.py` for easy extension.

## Sample Output (JSON)

```json
{
  "keyword": "Bitcoin",
  "geo": "US",
  "time_range": "today 12-m",
  "category": 0,
  "data_type": "interest_over_time",
  "results": [
    {"time": "Mar 10, 2024", "value": [65], "isPartial": false},
    {"time": "Mar 17, 2024", "value": [70], "isPartial": false}
  ],
  "extracted_at": "2026-03-09T13:30:00.000000"
}
```

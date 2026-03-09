BOT_NAME = 'google_trends'

SPIDER_MODULES = ['google_trends.spiders']
NEWSPIDER_MODULE = 'google_trends.spiders'

# Obey robots.txt rules
ROBOTSTXT_OBEY = False

# Concurrent requests and delay
CONCURRENT_REQUESTS = 16
DOWNLOAD_DELAY = 1.5
RANDOMIZE_DOWNLOAD_DELAY = True

# Cookies management (Google Trends needs cookies for some requests)
COOKIES_ENABLED = True

# Default headers
DEFAULT_REQUEST_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
}

# Middlewares
DOWNLOADER_MIDDLEWARES = {
    'google_trends.middlewares.RandomUserAgentMiddleware': 400,
    'google_trends.middlewares.ProxyMiddleware': 410,
    'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
}

# Pipelines
ITEM_PIPELINES = {
    'google_trends.pipelines.GoogleTrendsPipeline': 300,
    'google_trends.pipelines.JSONLPipeline': 400,
}

# Retry settings
RETRY_ENABLED = True
RETRY_TIMES = 5
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]

# User Agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
]

# Proxies (Example)
PROXY_LIST = []

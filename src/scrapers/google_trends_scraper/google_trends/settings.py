import os
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '.env'))

BOT_NAME = 'google_trends'

SPIDER_MODULES = ['google_trends.spiders']
NEWSPIDER_MODULE = 'google_trends.spiders'

# Obey robots.txt rules
ROBOTSTXT_OBEY = False

# Concurrent requests and delay
CONCURRENT_REQUESTS = int(os.getenv('SCRAPY_CONCURRENT_REQUESTS', 1))
DOWNLOAD_DELAY = float(os.getenv('SCRAPY_DOWNLOAD_DELAY', 12.0))
RANDOMIZE_DOWNLOAD_DELAY = True
DOWNLOAD_TIMEOUT = 30

# Cookies management
COOKIES_ENABLED = True

# Default headers
DEFAULT_REQUEST_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://trends.google.com/',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Dest': 'empty',
}

# Middlewares
DOWNLOADER_MIDDLEWARES = {
    'google_trends.middlewares.RandomUserAgentMiddleware': 400,
    'google_trends.middlewares.ProxyMiddleware': 410,
    'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
}

# AutoThrottle settings
AUTOTHROTTLE_ENABLED = os.getenv('SCRAPY_AUTOTHROTTLE_ENABLED', 'True') == 'True'
AUTOTHROTTLE_START_DELAY = 10.0
AUTOTHROTTLE_MAX_DELAY = 120.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 0.5
AUTOTHROTTLE_DEBUG = False

# Pipelines
ITEM_PIPELINES = {
    'google_trends.pipelines.GoogleTrendsPipeline': 300,
    'google_trends.pipelines.JSONLPipeline': 400,
}

# Retry settings
RETRY_ENABLED = True
RETRY_TIMES = 2
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]

# User Agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Edge/122.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15'
]

# Proxies
PROXY_LIST = [p.strip() for p in os.getenv('SCRAPY_PROXIES', '').split(',') if p.strip()]